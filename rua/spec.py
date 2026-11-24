"""Task spec: the generator's output. A YAML file validated by this schema; fixed code builds it.

Spec -> sample(seed) gives object poses -> Sim places them -> is_success() grades the final state.
The oracle plan is resolved against the same sampled poses, so it never reads the sim.
"""

from pathlib import Path
from typing import Literal, Union

import numpy as np
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

import objects

TASKS_DIR = Path(__file__).parents[1] / "tasks"
COLORS = {"red": [0.8, 0.1, 0.1, 1], "green": [0.1, 0.6, 0.2, 1], "blue": [0.1, 0.3, 0.8, 1],
          "yellow": [0.9, 0.8, 0.1, 1], "orange": [0.9, 0.5, 0.1, 1], "purple": [0.5, 0.2, 0.7, 1],
          "white": [0.9, 0.9, 0.9, 1], "black": [0.1, 0.1, 0.1, 1], "wood": [0.55, 0.4, 0.25, 1]}


class Obj(BaseModel):
    name: str
    shape: Literal[objects.PRIMITIVES + objects.COMPOUND + objects.ARTICULATED + objects.FIXED + objects.ASSET]
    size: list[float]  # metres, full lengths. box/drawer/hole_block: [x, y, z]; cylinder: [diameter, height]; sphere/zone: [diameter]
    # hook: [handle length, crossbar length, thickness]; asset: filled from its catalog card (bbox), never set
    color: Literal[tuple(COLORS)] | None = None  # required except for assets (textured)
    mass: float = 0.1  # asset: defaults to its card's mass
    asset: str | None = None  # asset only: a catalog id (assets/catalog.yaml)
    x: tuple[float, float]  # placement range on the table, sampled per seed
    y: tuple[float, float]
    yaw: tuple[float, float] = (0, 0)  # degrees
    travel: float = 0.2  # drawer only: how far it slides out (m)
    damping: float = 2.0  # drawer only: resistance to sliding (N*s/m), a difficulty knob
    start: float = 0.0  # drawer only: how far open at reset, as a fraction of travel
    hole: float = 0.04  # hole_block only: side of the square hole (m); minus the peg width = clearance


    @model_validator(mode="before")
    @classmethod
    def _asset_card(cls, v):
        if v.get("shape") != "asset":
            if v.get("color") is None:
                raise ValueError(f"{v.get('name')}: color is required")
            return v
        if v.get("asset") not in objects.CATALOG:
            raise ValueError(f"{v.get('name')}: unknown asset {v.get('asset')!r}; use an id from assets/catalog.yaml")
        if "size" in v:
            raise ValueError(f"{v.get('name')}: an asset's size comes from its catalog card; don't set it")
        card = objects.CATALOG[v["asset"]]
        return {"mass": card["mass"], **v, "size": card["size"]}


class Lifted(BaseModel):
    object: str
    height: float  # metres of the object's bottom above the table


class Opened(BaseModel):
    object: str
    fraction: float = 0.9  # of the drawer's travel; it must also be at rest


class Inserted(BaseModel):
    object: str
    target: str  # a hole_block
    depth: float = 0.02  # metres of the object's bottom below the block's top, centre inside the hole


class InZone(BaseModel):
    object: str
    zone: str
    radius: float = 0.05  # object centre within this of the zone centre (xy), and at rest


class Closed(BaseModel):
    object: str
    fraction: float = 0.05  # of the drawer's travel, at most; it must also be at rest


class Inside(BaseModel):
    object: str
    container: str  # a drawer: object centre within its tray and under the cabinet top, at rest;
    # or a hollow asset: object centre within its rim (60% of the half-width) and bottom below the rim, at rest


class Stacked(BaseModel):
    order: list[str] = Field(min_length=2)  # bottom to top


class NearOffset(BaseModel):
    object: str
    anchor: str
    offset: tuple[float, float]  # world-frame xy from the anchor's centre (m)
    radius: float = 0.03  # object centre within this of anchor + offset, resting on the table


class Unmoved(BaseModel):
    objects: list[str]
    tol: float = 0.03  # metres each may end up from where it started


PREDICATES = {"lifted": Lifted, "opened": Opened, "inserted": Inserted, "in_zone": InZone, "closed": Closed,
              "inside": Inside, "stacked": Stacked, "near_offset": NearOffset, "unmoved": Unmoved}
REFS = ("object", "target", "zone", "container", "anchor", "order", "objects")  # predicate fields naming objects


class Step(BaseModel):
    """One oracle waypoint: gripper straight down at an object or part, plus an offset in the
    object's own frame (so "pull out" follows a rotated drawer)."""
    at: str  # "object" or "object.part", e.g. "cabinet.handle"
    offset: tuple[float, float, float] = (0, 0, 0)
    yaw: float = 0  # degrees added to the object's yaw
    toward: str | None = None  # pushes: offset x points from the object toward this one (replaces its yaw)
    gripper: Literal["open", "closed"]


class TaskSpec(BaseModel):
    name: str
    prompt: str
    objects: list[Obj] = Field(min_length=1)
    # All must hold. A kind may take a list (e.g. two blocks `inside`), each entry checked.
    success: dict[Literal[tuple(PREDICATES)], Union[tuple(PREDICATES.values())] | list[Union[tuple(PREDICATES.values())]]]
    oracle: list[Step] = Field(min_length=1)
    # Rotate the whole layout (positions and yaws) about its centre by a per-seed angle, degrees.
    # Per-object ranges alone keep relations (target always on the same side) fixed across seeds.
    layout_yaw: tuple[float, float] = (0, 0)
    knobs: dict[str, float | str] = {}
    # Success thresholds deliberately not stated in the prompt, "kind.field" -> why (the `prompt` gate
    # requires every other one to be stated: OpenRUA traced 79/413 failures to unstated thresholds).
    hidden: dict[str, str] = {}

    @field_validator("success", mode="before")
    @classmethod
    def _parse_by_kind(cls, v):  # the key picks the model; a plain union would guess from the fields
        parse = lambda k, p: [parse(k, q) for q in p] if isinstance(p, list) else PREDICATES[k].model_validate(p)
        return {k: parse(k, p) if k in PREDICATES else p for k, p in v.items()}

    @model_validator(mode="after")
    def _references_exist(self):
        by_name = {o.name: o for o in self.objects}
        for o in self.objects:
            if o.asset and not objects.CATALOG[o.asset]["admitted"]:
                raise ValueError(f"asset {o.asset!r} failed admission: {objects.CATALOG[o.asset]['notes']}")
        for p in self._predicates("inside"):
            c = by_name.get(p.container)
            if c and c.shape == "asset" and not objects.CATALOG[c.asset]["hollow"]:
                raise ValueError(f"inside: asset {c.asset!r} is not a container (hollow: false)")
        # A closed cabinet's top looked like an open drawer to sol (2/5 drawer_store_close runs), so a
        # prompt must state the starting state of every movable part.
        if any(o.shape in objects.ARTICULATED for o in self.objects) and not any(
                w in self.prompt.lower() for w in ("starts closed", "starts open", "starts partly open")):
            raise ValueError("prompt must say whether the drawer starts closed or open")
        for s in self.oracle:
            obj, _, part = s.at.partition(".")
            if obj not in by_name or s.toward not in (None, *by_name):
                raise ValueError(f"oracle step references unknown object {obj!r} / {s.toward!r}")
            objects.part_offset(by_name[obj].shape, by_name[obj].size, part or None)  # raises if no such part
        for p in (q for ps in self.success.values() for q in (ps if isinstance(ps, list) else [ps])):
            for field, ref in p:
                for r in ([ref] if isinstance(ref, str) else ref) if field in REFS else ():
                    if r not in by_name:
                        raise ValueError(f"success references unknown object {r!r}")
        return self

    def _predicates(self, kind: str) -> list:
        p = self.success.get(kind, [])
        return p if isinstance(p, list) else [p]

    def obj(self, name: str) -> Obj:
        return next(o for o in self.objects if o.name == name)

    def sample(self, seed: int) -> dict[str, tuple[np.ndarray, float]]:
        """Object name -> (origin position, yaw radians) for this seed. Deterministic."""
        rng = np.random.default_rng(seed)
        poses = {o.name: (np.array([rng.uniform(*o.x), rng.uniform(*o.y), objects.base_z(o.shape, o.size)]),
                          np.radians(rng.uniform(*o.yaw))) for o in self.objects}
        if self.layout_yaw == (0, 0):  # no extra draw, so existing tasks keep their seeds
            return poses
        a = np.radians(rng.uniform(*self.layout_yaw))
        pivot = np.mean([[np.mean(o.x), np.mean(o.y)] for o in self.objects], axis=0)
        rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        for name, (pos, yaw) in poses.items():
            pos[:2] = pivot + rot @ (pos[:2] - pivot)
            poses[name] = (pos, yaw + a)
        return poses

    def plan(self, seed: int) -> list[tuple[np.ndarray, float, float]]:
        """Oracle waypoints for this seed: (tcp position, tool yaw, gripper 1 open / 0 closed)."""
        poses, out = self.sample(seed), []
        for s in self.oracle:
            name, _, part = s.at.partition(".")
            o, (pos, yaw) = self.obj(name), poses[name]
            if s.toward:
                d = poses[s.toward][0] - pos
                yaw = np.arctan2(d[1], d[0])
            c, si = np.cos(yaw), np.sin(yaw)
            local = objects.part_offset(o.shape, o.size, part or None) + s.offset
            world = pos + [c * local[0] - si * local[1], si * local[0] + c * local[1], local[2]]
            tool_yaw = (yaw + np.radians(s.yaw) + np.pi) % (2 * np.pi) - np.pi  # the tool takes [-pi, pi]
            out.append((world, tool_yaw, float(s.gripper == "open")))
        return out

    def conditions(self, sim) -> dict[str, bool]:
        """Each success predicate separately, so a 0 score says which part failed.
        sim gives body_pos(name), model, data, seed. Plain bools: numpy bools break HUD's JSON grading."""
        return {kind: all(bool(self._holds(kind, q, sim)) for q in (p if isinstance(p, list) else [p]))
                for kind, p in self.success.items()}

    def final_state(self, sim) -> dict:
        """Numbers behind the grade for trace review: object positions (mm), drawer open fraction,
        and what the arm still touches. Review agents couldn't tell "drawer 6% open" from "never opened"."""
        out = {}
        for o in self.objects:
            pos = [round(float(v) * 1000) for v in sim.body_pos(o.name)]
            out[o.name] = {"pos_mm": pos, "held": bool(objects.touching_robot(sim.model, sim.data, o.name))}
            if o.shape in objects.ARTICULATED:
                out[o.name]["open"] = round(objects.joint_fraction(sim.model, sim.data, o.name)[0], 3)
        return out

    def is_success(self, sim) -> bool:
        return all(self.conditions(sim).values())

    def _holds(self, kind: str, p, sim):
        if kind == "stacked":  # each centred on the one below and one block-height up, the bottom on the table
            on = all(np.linalg.norm(sim.body_pos(b)[:2] - sim.body_pos(a)[:2]) < self.obj(a).size[0] / 2 and
                     abs(sim.body_pos(b)[2] - sim.body_pos(a)[2] - self.obj(a).size[2]) < 0.01
                     for a, b in zip(p.order, p.order[1:]))
            return on and self._resting(sim, p.order[0]) and all(self._released(sim, n) for n in p.order)
        if kind == "unmoved":
            start = self.sample(sim.seed)
            return all(np.linalg.norm(sim.body_pos(n) - start[n][0]) < p.tol for n in p.objects)
        o, pos = self.obj(p.object), sim.body_pos(p.object)
        if kind == "lifted":
            return pos[2] - objects.base_z(o.shape, o.size) > p.height
        if kind in ("opened", "closed"):
            frac, speed = objects.joint_fraction(sim.model, sim.data, p.object)
            return (frac >= p.fraction if kind == "opened" else frac <= p.fraction) and speed < 0.05
        if kind == "inserted":
            block, t = sim.data.body(p.target), self.obj(p.target)
            local = block.xmat.reshape(3, 3).T @ (pos - block.xpos)  # object centre in the block's frame
            return max(abs(local[:2])) < t.hole / 2 and local[2] - o.size[-1] / 2 < t.size[2] - p.depth
        if kind == "inside":
            c = self.obj(p.container)
            if c.shape == "asset":
                cpos = sim.body_pos(p.container)
                within = (np.linalg.norm(pos[:2] - cpos[:2]) < 0.6 * min(c.size[:2]) / 2
                          and pos[2] - o.size[-1] / 2 < cpos[2] + c.size[2] / 2)
            else:
                within = objects.in_drawer(sim.data, p.container, c.size, pos)
            return within and self._released(sim, p.object)
        if kind == "near_offset":
            target = sim.body_pos(p.anchor)[:2] + p.offset
            return np.linalg.norm(pos[:2] - target) < p.radius and self._resting(sim, p.object)
        near = np.linalg.norm(pos[:2] - sim.body_pos(p.zone)[:2]) < p.radius
        return near and objects.free_speed(sim.data, p.object) < 0.05

    def _released(self, sim, name: str) -> bool:
        """At rest and not touching the arm (so not still held)."""
        return objects.free_speed(sim.data, name) < 0.05 and not objects.touching_robot(sim.model, sim.data, name)

    def _resting(self, sim, name: str) -> bool:
        """Released and on the table (bottom within 1 cm of it)."""
        o = self.obj(name)
        return sim.body_pos(name)[2] - objects.base_z(o.shape, o.size) < 0.01 and self._released(sim, name)

def load(name: str) -> TaskSpec:
    return TaskSpec.model_validate(yaml.safe_load((TASKS_DIR / f"{name}.yaml").read_text()))
