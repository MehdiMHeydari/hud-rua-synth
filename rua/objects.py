"""Object types a spec can use: primitives, compound tools (boxes in one free body), articulated
templates (boxes + a joint), and fixed templates (boxes or a visual marker, no joint).

Each type knows how to build itself in MjSpec, where its base sits, and where its named parts
are (e.g. a drawer's handle), so oracle plans can target parts without reading the sim.
"""

import mujoco
import numpy as np

GEOMS = {"box": mujoco.mjtGeom.mjGEOM_BOX, "cylinder": mujoco.mjtGeom.mjGEOM_CYLINDER,
         "sphere": mujoco.mjtGeom.mjGEOM_SPHERE}
PRIMITIVES = tuple(GEOMS)
COMPOUND = ("hook",)  # free bodies made of several boxes
ARTICULATED = ("drawer",)
FIXED = ("hole_block", "zone")

WALL = 0.01  # cabinet wall thickness (m)
HANDLE_OUT = 0.06  # pull tab length out of the drawer face
HOOK_GRIP = 0.05  # hook: grasp point's distance from the handle's free end


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
    if shape == "hook" and part == "handle":
        return np.array([-size[0] / 2 + HOOK_GRIP, 0.0, 0.0])
    raise ValueError(f"{shape} has no part {part!r}")


def add(spec: mujoco.MjSpec, name: str, shape: str, size: list[float], rgba, mass: float,
        travel: float = 0.2, damping: float = 2.0, hole: float = 0.04) -> None:
    """Add one object to the scene. Primitives and compounds are free bodies; templates are fixed to the table."""
    if shape in PRIMITIVES:
        body = spec.worldbody.add_body(name=name)
        body.add_freejoint()
        # Spec sizes are full lengths; MuJoCo wants halves (cylinder: radius, half-height).
        # condim=4 adds twisting friction so grasped objects don't pivot about the finger axis.
        body.add_geom(type=GEOMS[shape], size=[v / 2 for v in size], rgba=rgba, mass=mass, condim=4)
    elif shape == "hook":
        _add_hook(spec, name, size, rgba, mass)
    elif shape == "drawer":
        _add_drawer(spec, name, size, rgba, mass, travel, damping)
    elif shape == "hole_block":
        _add_hole_block(spec, name, size, rgba, hole)
    elif shape == "zone":
        # Paint on the table: contype/conaffinity 0 so it is seen but never touched.
        spec.worldbody.add_body(name=name).add_geom(type=GEOMS["cylinder"], size=[size[0] / 2, 0.0005],
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


def _add_drawer(spec, name, size, rgba, mass, travel, damping) -> None:
    """Open-front cabinet (front faces -x, toward the robot) with a drawer on a slide joint."""
    d, w, h = size
    box = mujoco.mjtGeom.mjGEOM_BOX
    grey = [0.75, 0.75, 0.75, 1]
    cab = spec.worldbody.add_body(name=name)  # fixed: no joint
    for pos, half in (([0, 0, WALL / 2], [d / 2, w / 2, WALL / 2]),  # bottom
                      ([0, 0, h - WALL / 2], [d / 2, w / 2, WALL / 2]),  # top
                      ([0, w / 2 - WALL / 2, h / 2], [d / 2, WALL / 2, h / 2]),  # sides
                      ([0, -w / 2 + WALL / 2, h / 2], [d / 2, WALL / 2, h / 2]),
                      ([d / 2 - WALL / 2, 0, h / 2], [WALL / 2, w / 2, h / 2])):  # back
        cab.add_geom(type=box, pos=pos, size=half, rgba=grey)
    drawer = cab.add_body(name=f"{name}_drawer")
    # The drawer rides on its joint like on rails: no rubbing against its own cabinet (a fixed
    # cabinet counts as world, so MuJoCo's parent-child exclusion doesn't apply and it jams).
    spec.add_exclude(bodyname1=name, bodyname2=f"{name}_drawer")
    drawer.add_joint(name=f"{name}_slide", type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[-1, 0, 0],
                     range=[0, travel], damping=damping)
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
