"""Object types a spec can use: primitives, compound tools (boxes in one free body), articulated
templates (boxes + a joint), fixed templates (boxes or a visual marker, no joint), and scanned
assets from the curated library (assets/catalog.yaml).

Each type knows how to build itself in MjSpec, where its base sits, and where its named parts
are (e.g. a drawer's handle), so oracle plans can target parts without reading the sim.
"""

from functools import lru_cache
from pathlib import Path

import mujoco
import numpy as np
import yaml

GEOMS = {"box": mujoco.mjtGeom.mjGEOM_BOX, "cylinder": mujoco.mjtGeom.mjGEOM_CYLINDER,
         "sphere": mujoco.mjtGeom.mjGEOM_SPHERE}
PRIMITIVES = tuple(GEOMS)
COMPOUND = ("hook", "lidbox")  # free bodies made of several boxes (lidbox: plus a sliding lid)
ARTICULATED = ("drawer",)
FIXED = ("hole_block", "zone", "platform", "seesaw")  # seesaw: fixed fulcrum, its plank tilts on a hinge
ASSET = ("asset",)  # a free body from the library; size and mass come from its catalog card

ASSET_DIR = Path(__file__).parents[1] / "assets"
CATALOG = {c["id"]: c for c in yaml.safe_load((ASSET_DIR / "catalog.yaml").read_text())["assets"]}

WALL = 0.01  # cabinet wall thickness (m)
HANDLE_OUT = 0.06  # pull tab length out of the drawer face
HOOK_GRIP = 0.05  # hook: grasp point's distance from the handle's free end
LID = 0.015  # lidbox: lid thickness (m)


def base_z(shape: str, size: list[float]) -> float:
    """Height of the body origin above the table: centre for primitives, floor for templates."""
    return 0.0 if shape in ARTICULATED + FIXED else (size[0] if shape == "sphere" else size[-1]) / 2


def part_offset(shape: str, size: list[float], part: str | None) -> np.ndarray:
    """Part position in the object's own frame (before yaw). part=None is the object origin."""
    if part is None:
        return np.zeros(3)
    if shape == "drawer" and part == "handle":
        depth, _, height = size
        return np.array([-depth / 2 - 0.75 * HANDLE_OUT, 0.0, height / 2])  # near the tab's outer end
    if shape == "lidbox" and part == "handle":  # the lid's pull tab, pinched from the sides
        return np.array([-size[0] / 2 - 0.75 * HANDLE_OUT, 0.0, size[2] / 2 - LID / 2])
    if shape == "hook" and part == "handle":
        return np.array([-size[0] / 2 + HOOK_GRIP, 0.0, 0.0])
    raise ValueError(f"{shape} has no part {part!r}")


def add(spec: mujoco.MjSpec, name: str, shape: str, size: list[float], rgba, mass: float,
        travel: float = 0.2, damping: float = 2.0, hole: float = 0.04, asset: str | None = None,
        friction: float = 1.0, pivot: float = 0.05, weight: float = 0.0, loose: bool = False,
        stiction: float = 2.0, priority: int = 0) -> None:
    """Add one object to the scene. Primitives and compounds are free bodies; templates are fixed to the table."""
    if shape in PRIMITIVES:
        body = spec.worldbody.add_body(name=name)
        body.add_freejoint()
        # Spec sizes are full lengths; MuJoCo wants halves (cylinder: radius, half-height).
        # condim=4 adds twisting friction so grasped objects don't pivot about the finger axis.
        body.add_geom(type=GEOMS[shape], size=[v / 2 for v in size], rgba=rgba, mass=mass, condim=4,
                      friction=[friction, 0.005, 0.0001], priority=priority)
        if weight:  # hidden lead near the +x end: no contact, invisible, shifts the centre of mass only
            body.add_geom(type=GEOMS["sphere"], size=[0.005], pos=[size[0] / 2 - 0.01, 0, 0], mass=weight,
                          contype=0, conaffinity=0, rgba=[0, 0, 0, 0], group=3)
    elif shape == "hook":
        _add_hook(spec, name, size, rgba, mass)
    elif shape == "lidbox":
        _add_lidbox(spec, name, size, rgba, mass, friction, damping, stiction)
    elif shape == "drawer":
        _add_drawer(spec, name, size, rgba, mass, travel, damping, loose)
    elif shape == "hole_block":
        _add_hole_block(spec, name, size, rgba, hole)
    elif shape == "asset":
        centre, _, mass_at_1000 = measure(asset)
        _add_asset(spec, name, asset, density=1000 * mass / mass_at_1000, offset=-centre)
    elif shape == "seesaw":
        _add_seesaw(spec, name, size, rgba, mass, pivot, damping)
    elif shape == "platform":  # a solid fixed box, e.g. a ledge to slide things over
        spec.worldbody.add_body(name=name).add_geom(type=GEOMS["box"], size=[v / 2 for v in size],
                                                    pos=[0, 0, size[2] / 2], rgba=rgba,
                                                    friction=[friction, 0.005, 0.0001])  # MuJoCo's default at 1
    elif shape == "zone":
        # Paint on the table: contype/conaffinity 0 so it is seen but never touched. [d] circle, [x, y] rectangle.
        kind, half = ("cylinder", [size[0] / 2]) if len(size) == 1 else ("box", [size[0] / 2, size[1] / 2])
        spec.worldbody.add_body(name=name).add_geom(type=GEOMS[kind], size=[*half, 0.0005],
                                                    pos=[0, 0, 0.0005], rgba=rgba, contype=0, conaffinity=0)
    else:
        raise ValueError(f"unknown shape {shape!r}")


def _add_hook(spec, name, size, rgba, mass) -> None:
    """L-shaped tool: a handle along x, and a crossbar at its far (+x) end reaching out to +y."""
    length, reach, t = size
    body = spec.worldbody.add_body(name=name)
    body.add_freejoint()
    # MuJoCo's torsional friction is soft: at the default 0.005 a hook gripped near its end pivoted
    # about the finger axis until it lay on the table, whatever its mass. 0.1 holds a 50 g hook within ~1 deg.
    for pos, half in (([0, 0, 0], [length / 2, t / 2, t / 2]),
                      ([length / 2 - t / 2, reach / 2, 0], [t / 2, reach / 2, t / 2])):
        body.add_geom(type=GEOMS["box"], pos=pos, size=half, rgba=rgba, mass=mass / 2, condim=4,
                      friction=[1, 0.1, 0.0001])


def _add_lidbox(spec, name, size, rgba, mass, friction, damping, stiction) -> None:
    """Free box (origin at its centre) with a lid that slides out toward -x on a joint `<name>_slide`
    (range: its own length, so fully open = clear of the box). `stiction` (N) holds the lid in its
    grooves; `friction` is the box's on the table and wins over it (priority), so a light,
    slippery box rides along with a pulled lid unless something stops it."""
    d, w, h = size
    box = mujoco.mjtGeom.mjGEOM_BOX
    body = spec.worldbody.add_body(name=name)
    body.add_freejoint()
    body.add_geom(type=box, pos=[0, 0, -LID / 2], size=[d / 2, w / 2, (h - LID) / 2], rgba=[0.75, 0.75, 0.75, 1],
                  mass=mass * 0.8, condim=4, priority=1, friction=[friction, 0.005, 0.0001])
    lid = body.add_body(name=f"{name}_lid", pos=[0, 0, h / 2 - LID / 2])
    spec.add_exclude(bodyname1=name, bodyname2=f"{name}_lid")  # rides in its grooves, not on the box
    lid.add_joint(name=f"{name}_slide", type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[-1, 0, 0], range=[0, d],
                  damping=damping, frictionloss=stiction,
                  # MuJoCo's friction loss is soft: at the default solref a 0.9 N drag crept the lid 11% open per
                  # 20 cm pull, so repeated unbraced pulls would open it. Stiffest stable (2 x timestep): 2.5%.
                  solref_friction=[0.002, 1], solimp_friction=[0.99, 0.999, 0.001, 0.5, 2])
    lid.add_geom(type=box, size=[d / 2, w / 2, LID / 2], rgba=rgba, mass=mass * 0.15)
    # Same pull tab as the drawer's, at lid height: torsional friction 0.1 (hook) so a box lifted
    # by it doesn't swing about the finger axis.
    lid.add_geom(type=box, pos=[-d / 2 - HANDLE_OUT / 2, 0, 0], size=[HANDLE_OUT / 2, 0.01, 0.0125],
                 rgba=rgba, mass=mass * 0.05, condim=4, friction=[1, 0.1, 0.0001])


# Static friction on the slide (N). Without it, pulling the hand back after pushing the drawer shut
# dragged it 1-7 mm open again, so Astra's "drawer is closed" read as false (Nov 24 trace review).
# 1 N stops that and is lighter than any real drawer.
DRAWER_FRICTION = 0.5


def _add_drawer(spec, name, size, rgba, mass, travel, damping, loose=False) -> None:
    """Open-front cabinet (front faces -x, toward the robot) with a drawer on a slide joint."""
    d, w, h = size
    box = mujoco.mjtGeom.mjGEOM_BOX
    grey = [0.75, 0.75, 0.75, 1]
    cab = spec.worldbody.add_body(name=name)  # fixed: no joint
    # Loose: a free 0.15 kg cabinet on low-friction walls, so the slide's resistance exceeds its grip
    # on the table and pulling the handle drags the whole cabinet (Robocurve SET, Nov 2026: agents
    # never brace the object they act on; the backpack slid instead of unzipping).
    extra = {"mass": 0.15 / 5, "friction": [0.25, 0.005, 0.0001], "priority": 1} if loose else {}  # priority: its friction wins over the table's
    if loose:
        cab.add_freejoint()
    for pos, half in (([0, 0, WALL / 2], [d / 2, w / 2, WALL / 2]),  # bottom
                      ([0, 0, h - WALL / 2], [d / 2, w / 2, WALL / 2]),  # top
                      ([0, w / 2 - WALL / 2, h / 2], [d / 2, WALL / 2, h / 2]),  # sides
                      ([0, -w / 2 + WALL / 2, h / 2], [d / 2, WALL / 2, h / 2]),
                      ([d / 2 - WALL / 2, 0, h / 2], [WALL / 2, w / 2, h / 2])):  # back
        cab.add_geom(type=box, pos=pos, size=half, rgba=grey, **extra)
    drawer = cab.add_body(name=f"{name}_drawer")
    # The drawer rides on its joint like on rails: no rubbing against its own cabinet (a fixed
    # cabinet counts as world, so MuJoCo's parent-child exclusion doesn't apply and it jams).
    spec.add_exclude(bodyname1=name, bodyname2=f"{name}_drawer")
    drawer.add_joint(name=f"{name}_slide", type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[-1, 0, 0],
                     range=[0, travel], damping=damping, frictionloss=DRAWER_FRICTION)
    inner_w, inner_h, floor = w / 2 - 1.5 * WALL, (h - 3 * WALL) / 2, 1.5 * WALL
    for pos, half in (([0, 0, floor], [d / 2 - WALL, inner_w, WALL / 2]),  # tray floor
                      ([-d / 2 + WALL / 2, 0, floor + inner_h], [WALL / 2, inner_w, inner_h]),  # front face
                      ([0, inner_w - WALL / 2, floor + inner_h / 2], [d / 2 - WALL, WALL / 2, inner_h / 2]),
                      ([0, -inner_w + WALL / 2, floor + inner_h / 2], [d / 2 - WALL, WALL / 2, inner_h / 2])):
        drawer.add_geom(type=box, pos=pos, size=half, rgba=rgba, mass=mass / 5)
    # Handle: a pull tab sticking straight out of the face. Pinched from the sides, so the Panda's
    # 20 cm-wide hand stays clear of the cabinet (a bar handle would make it hit the cabinet top).
    drawer.add_geom(type=box, pos=[-d / 2 - HANDLE_OUT / 2, 0, h / 2], size=[HANDLE_OUT / 2, 0.01, 0.015],
                    rgba=grey, mass=mass / 10, condim=4)


def _add_seesaw(spec, name, size, rgba, mass, pivot, damping) -> None:
    """A plank (size [length along x, width, thickness]) on a hinge about its centre's y axis, `pivot`
    m above the table, on a fixed fulcrum block. Starts level; the table stops each end. `damping`
    (N*m*s/rad) slows the swing. Plank body `<name>_plank`, joint `<name>_hinge`."""
    length, width, t = size
    box = mujoco.mjtGeom.mjGEOM_BOX
    base = spec.worldbody.add_body(name=name)
    base.add_geom(type=box, size=[0.015, width / 2, (pivot - t / 2) / 2], pos=[0, 0, (pivot - t / 2) / 2],
                  rgba=[0.75, 0.75, 0.75, 1])
    plank = base.add_body(name=f"{name}_plank", pos=[0, 0, pivot])
    spec.add_exclude(bodyname1=name, bodyname2=f"{name}_plank")  # rides on the hinge, not on the block
    plank.add_joint(name=f"{name}_hinge", type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 1, 0], damping=damping)
    plank.add_geom(type=box, size=[length / 2, width / 2, t / 2], rgba=rgba, mass=mass, condim=4)
    # A short dark mark across each end, so tilt and ends read in the top image.
    for sx in (-1, 1):
        plank.add_geom(type=box, size=[0.005, width / 2, 0.001], pos=[sx * (length / 2 - 0.005), 0, t / 2 + 0.001],
                       rgba=[0.1, 0.1, 0.1, 1], contype=0, conaffinity=0, mass=0)


def seesaw_tilt(model: mujoco.MjModel, data: mujoco.MjData, name: str) -> float:
    """Plank angle in degrees (positive: the +x end down)."""
    return float(np.degrees(data.qpos[model.joint(f"{name}_hinge").qposadr[0]]))


def _add_hole_block(spec, name, size, rgba, hole) -> None:
    """Fixed block with a square through-hole (side `hole`) in its centre: four walls, open top,
    the table is the floor."""
    d, w, h = size
    tx, ty = (d - hole) / 4, (w - hole) / 4  # half-thicknesses of the walls in x and y
    body = spec.worldbody.add_body(name=name)
    for pos, half in (([0, (w / 2 - ty), h / 2], [d / 2, ty, h / 2]),  # left/right walls, full depth
                      ([0, -(w / 2 - ty), h / 2], [d / 2, ty, h / 2]),
                      ([d / 2 - tx, 0, h / 2], [tx, hole / 2, h / 2]),  # back/front walls, between them
                      ([-(d / 2 - tx), 0, h / 2], [tx, hole / 2, h / 2])):
        body.add_geom(type=GEOMS["box"], pos=pos, size=half, rgba=rgba)


def _add_asset(spec, name, asset, density, offset) -> None:
    """Copy a library object's meshes and geoms (as its model.xml defines them) into one free body.
    Only reads the downloaded XML/meshes. The visual mesh is massless; the convex collision hulls
    carry the mass at `density`. `offset` puts the body origin at the collision bbox centre, so the
    asset behaves like a box of its card size for placement and every predicate."""
    folder = ASSET_DIR / "gso" / "models" / CATALOG[asset]["source"]
    if not (folder / "model.xml").exists():
        raise FileNotFoundError(f"{folder} missing: fetch it with the command at the top of assets/catalog.yaml")
    src = mujoco.MjSpec.from_file(str(folder / "model.xml"))
    for t in src.textures:
        spec.add_texture(name=f"{name}_{t.name}", type=t.type, file=str(folder / t.file))
    for m in src.materials:
        mat = spec.add_material(name=f"{name}_{m.name}", specular=m.specular, shininess=m.shininess)
        mat.textures = [f"{name}_{t}" if t else "" for t in m.textures]
    for m in src.meshes:
        spec.add_mesh(name=f"{name}_{m.name}", file=str(folder / m.file))
    body = spec.worldbody.add_body(name=name)
    body.add_freejoint()
    friction = CATALOG[asset]["friction"]
    for g in src.worldbody.find_all(mujoco.mjtObj.mjOBJ_GEOM):
        collide = g.contype or g.conaffinity
        body.add_geom(type=g.type, meshname=f"{name}_{g.meshname}", pos=offset, group=g.group,
                      contype=g.contype, conaffinity=g.conaffinity, density=density if collide else 0,
                      material=f"{name}_{g.material}" if g.material else "", condim=4,
                      friction=[friction, 0.005, 0.0001])


@lru_cache
def measure(asset: str) -> tuple[np.ndarray, np.ndarray, float]:
    """Collision bbox centre and size in the mesh frame (m), and the mass at density 1000.
    Compiled once per asset in an empty scene."""
    spec = mujoco.MjSpec()
    _add_asset(spec, "a", asset, density=1000, offset=[0, 0, 0])
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    pts = []
    for g in range(model.ngeom):
        if model.geom_contype[g] or model.geom_conaffinity[g]:
            mesh = model.geom_dataid[g]
            v = model.mesh_vert[model.mesh_vertadr[mesh]: model.mesh_vertadr[mesh] + model.mesh_vertnum[mesh]]
            pts.append(v @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g])
    lo, hi = np.vstack(pts).min(0), np.vstack(pts).max(0)
    return (lo + hi) / 2, hi - lo, float(model.body_mass[1])


def free_speed(data: mujoco.MjData, name: str) -> float:
    """Linear speed (m/s) of a free body."""
    return float(np.linalg.norm(data.body(name).cvel[3:]))


def touching_robot(model: mujoco.MjModel, data: mujoco.MjData, name: str) -> bool:
    """Whether the arm or gripper touches this body (e.g. still holding it)."""
    body, arm = model.body(name).id, model.body("link0").id
    for c in data.contact[: data.ncon]:
        b1, b2 = model.geom_bodyid[c.geom1], model.geom_bodyid[c.geom2]
        if body in (b1, b2) and arm in (model.body_rootid[b1], model.body_rootid[b2]):
            return True
    return False


def in_drawer(data: mujoco.MjData, name: str, size: list[float], point) -> bool:
    """Whether a point is within the drawer tray's walls and under the cabinet top."""
    tray = data.body(f"{name}_drawer")
    x, y, z = tray.xmat.reshape(3, 3).T @ (np.asarray(point) - tray.xpos)
    d, w, h = size
    return abs(x) < d / 2 - WALL and abs(y) < w / 2 - 2.5 * WALL and z < h


def joint_fraction(model: mujoco.MjModel, data: mujoco.MjData, name: str) -> tuple[float, float]:
    """Drawer opening as a fraction of its travel, and its speed (m/s)."""
    j = model.joint(f"{name}_slide")
    return float(data.qpos[j.qposadr[0]] / j.range[1]), float(abs(data.qvel[j.dofadr[0]]))
