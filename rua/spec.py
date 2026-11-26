"""Task spec: the generator's output. A YAML file validated by this schema; fixed code builds it.

Spec -> sample(seed) gives object poses -> Sim places them -> is_success() grades the final state.
The oracle plan is resolved against the same sampled poses, so it never reads the sim.
"""

from pathlib import Path
from typing import Literal, Union

import re

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
    size: list[float]  # metres, full lengths. box/drawer/hole_block/platform: [x, y, z]; cylinder: [diameter, height]; sphere: [diameter]
    # zone: [diameter] (circle) or [x, y] (rectangle)
    # hook: [handle length, crossbar length, thickness]; lidbox: [x, y, z] incl. its lid (slides out toward -x, part: handle); asset: filled from its catalog card (bbox), never set
    color: Literal[tuple(COLORS)] | None = None  # required except for assets (textured)
    mass: float = 0.1  # asset: defaults to its card's mass
    friction: float = 1.0  # primitives and platforms only (MuJoCo uses the larger of two touching geoms', so it also sets grip)
    # primitives only: in a contact the higher priority's friction wins (table 0), so `friction` below 1 can make
    # an object slippery on the table; equal priorities use the larger of the two
    priority: int = 0
    asset: str | None = None  # asset only: a catalog id (assets/catalog.yaml)
    x: tuple[float, float]  # placement range on the table, sampled per seed
    y: tuple[float, float]
    yaw: tuple[float, float] = (0, 0)  # degrees
    z: float = 0.0  # height of the surface it starts on (e.g. a platform's height); 0 = the table
    weight: float = 0.0  # box only: hidden lead (kg) at the object's own +x end, invisible; looks uniform
    pivot: float = 0.05  # seesaw only: hinge height above the table (m); size is the plank [length, width, thickness]
    stiction: float = 2.0  # lidbox only: static friction holding the lid in its grooves (N)
    travel: float = 0.2  # drawer only: how far it slides out (m)
    damping: float = 2.0  # drawer: resistance to sliding (N*s/m), a difficulty knob; seesaw: to swinging (N*m*s/rad)
    loose: bool = False  # drawer only: cabinet not fixed but a light free body on slippery feet (pulling drags it)
    start: float = 0.0  # drawer only: how far open at reset, as a fraction of travel
    hole: float = 0.04  # hole_block only: side of the square hole (m); minus the peg width = clearance
    only: list[str] | None = None  # exists only in these variants (see TaskSpec.variants); parked out of sight otherwise
    # Goal pose for `at_goal` tasks, sampled per seed (separate draw, so start poses don't change).
    # Unset = the goal is where it starts. The agent sees it as a goal image, never as numbers.
    goal_x: tuple[float, float] | None = None
    goal_y: tuple[float, float] | None = None


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


class Clear(BaseModel):
    zone: str
    objects: list[str]  # none of these has its centre over the zone's marking; all at rest on the table


class Tipped(BaseModel):
    object: str
    angle: float = 70  # degrees between the object's own up axis and world up, at least; at rest, released


class AtGoal(BaseModel):
    objects: list[str]
    radius: float = 0.03  # each centre within this (xy) of its goal pose, resting on the table


class Overhang(BaseModel):
    object: str
    platform: str
    beyond: float  # metres the object's farthest corner reaches past the platform's +x face; released, at rest, above its top


class Unmoved(BaseModel):
    objects: list[str]
    tol: float = 0.03  # metres each may end up from where it started


PREDICATES = {"lifted": Lifted, "opened": Opened, "inserted": Inserted, "in_zone": InZone, "closed": Closed,
              "inside": Inside, "stacked": Stacked, "near_offset": NearOffset, "unmoved": Unmoved, "clear": Clear, "tipped": Tipped,
              "at_goal": AtGoal, "overhang": Overhang}
REFS = ("object", "target", "zone", "container", "anchor", "order", "objects", "platform")  # predicate fields naming objects


class Step(BaseModel):
    """One oracle waypoint: gripper straight down at an object or part, plus an offset in the
    object's own frame (so "pull out" follows a rotated drawer)."""
    at: str  # "object" or "object.part", e.g. "cabinet.handle"
    offset: tuple[float, float, float] = (0, 0, 0)
    yaw: float = 0  # degrees added to the object's yaw
    toward: str | None = None  # pushes: offset x points from the object toward this one (replaces its yaw)
    gripper: Literal["open", "closed"]
    # Side grasps: world-frame tool (roll, pitch, yaw) in degrees, replacing straight-down + yaw.
    # E.g. [-90, 0, -90] points the fingers along +x, closing vertically; [-135, 0, -90] the same tilted 45 deg down.
    tool: tuple[float, float, float] | None = None
    goal: bool = False  # aim at the object's goal pose (Obj.goal_x/goal_y) instead of where it starts


class Perturb(BaseModel):
    """An unannounced change: the first time the task is solved, `object` is moved by `offset`
    (world xy, m) once. Tests whether the agent checks the final state instead of assuming it holds."""
    object: str
    offset: tuple[float, float]


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
    # Groups of same-shaped objects that swap poses per seed, so a hidden property (mass, a locked
    # drawer) is never at the same spot; success and oracle name the object, so they follow it.
    shuffle: list[list[str]] = []
    perturb: Perturb | None = None
    # Seed s plays variants[s % len] (a cycle, so any run of len seeds has the exact mix). Variants
    # listed in `impossible` can't be done: they are graded on the reply ending in IMPOSSIBLE alone,
    # and a feasible one also fails if the reply claims IMPOSSIBLE (so always declining doesn't pay).
    variants: list[str] = []
    impossible: list[str] = []
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
            for field, ref in p:  # (shuffle/perturb names are checked below)
                for r in ([ref] if isinstance(ref, str) else ref) if field in REFS else ():
                    if r not in by_name:
                        raise ValueError(f"success references unknown object {r!r}")
        for name in [n for g in self.shuffle for n in g] + ([self.perturb.object] if self.perturb else []):
            if name not in by_name:
                raise ValueError(f"shuffle/perturb references unknown object {name!r}")
        names = {n for o in self.objects for n in o.only or []}
        if not names | set(self.impossible) <= set(self.variants):
            raise ValueError(f"`only`/`impossible` name variants not in variants: {sorted(names | set(self.impossible))}")
        if self.variants and set(self.variants) <= set(self.impossible):
            raise ValueError("every variant is impossible: add a feasible one")
        for g in self.shuffle:  # same footprint, so a flat decal can stand in for a cube (fake_cubes)
            if len({tuple(by_name[n].size[:2]) for n in g}) > 1:
                raise ValueError(f"shuffle group {g} must share a footprint (they swap xy and yaw)")
        return self

    def _predicates(self, kind: str) -> list:
        p = self.success.get(kind, [])
        return p if isinstance(p, list) else [p]

    def obj(self, name: str) -> Obj:
        return next(o for o in self.objects if o.name == name)

    def variant(self, seed: int) -> str | None:
        return self.variants[seed % len(self.variants)] if self.variants else None

    def feasible(self, seed: int) -> bool:
        return self.variant(seed) not in self.impossible

    def present(self, o: Obj, seed: int) -> bool:
        return o.only is None or self.variant(seed) in o.only

    def oracle_answer(self, seed: int) -> str:
        """The oracle's final reply: it knows the variant from the seed."""
        return "done" if self.feasible(seed) else f"IMPOSSIBLE: this seed is the {self.variant(seed)!r} variant"

    def answer_conditions(self, seed: int, answer: str | None) -> dict[str, bool]:
        """The predicates read from the agent's final reply (only for tasks with impossible variants)."""
        if not self.impossible:
            return {}
        claimed = bool(re.search(r"\bIMPOSSIBLE\b", str(answer or "")))
        return {"claimed_impossible": claimed} if not self.feasible(seed) else {"no_impossible_claim": not claimed}

    def sample(self, seed: int) -> dict[str, tuple[np.ndarray, float]]:
        """Object name -> (origin position, yaw radians) for this seed, objects absent from this
        seed's variant left out (Sim parks them). Deterministic."""
        rng = np.random.default_rng(seed)
        poses = {o.name: (np.array([rng.uniform(*o.x), rng.uniform(*o.y), objects.base_z(o.shape, o.size) + o.z]),
                          np.radians(rng.uniform(*o.yaw))) for o in self.objects}
        for g in self.shuffle:  # drawn only when used, so existing tasks keep their seeds
            # xy and yaw swap, height stays each object's own (a decal stays on the table)
            for name, (pos, yaw) in zip(g, [(poses[n][0].copy(), poses[n][1]) for n in rng.permutation(g)]):
                poses[name] = (np.array([*pos[:2], poses[name][0][2]]), yaw)
        if self.layout_yaw == (0, 0):  # no extra draw, so existing tasks keep their seeds
            return {n: p for n, p in poses.items() if self.present(self.obj(n), seed)}
        a = np.radians(rng.uniform(*self.layout_yaw))
        pivot = np.mean([[np.mean(o.x), np.mean(o.y)] for o in self.objects], axis=0)
        rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        for name, (pos, yaw) in poses.items():
            pos[:2] = pivot + rot @ (pos[:2] - pivot)
            poses[name] = (pos, yaw + a)
        return {n: p for n, p in poses.items() if self.present(self.obj(n), seed)}

    def goals(self, seed: int) -> dict[str, tuple[np.ndarray, float]]:
        """Object name -> goal (position, yaw) for this seed: the start pose unless goal_x/goal_y are set."""
        poses, rng = self.sample(seed), np.random.default_rng([seed, 1])  # own stream: start poses unchanged
        for o in self.objects:
            if o.goal_x and o.goal_y:
                poses[o.name] = (np.array([rng.uniform(*o.goal_x), rng.uniform(*o.goal_y), poses[o.name][0][2]]),
                                 poses[o.name][1])
        return poses

    def plan(self, seed: int) -> list[tuple[np.ndarray, float | tuple, float]]:
        """Oracle waypoints for this seed: (tcp position, tool yaw or (roll, pitch, yaw) radians,
        gripper 1 open / 0 closed). Empty on an impossible variant: the oracle just replies."""
        poses, goals, out = self.sample(seed), self.goals(seed), []
        if not self.feasible(seed):
            return out
        for s in self.oracle:
            name, _, part = s.at.partition(".")
            o, (pos, yaw) = self.obj(name), (goals if s.goal else poses)[name]
            if s.toward:
                d = poses[s.toward][0] - pos
                yaw = np.arctan2(d[1], d[0])
            c, si = np.cos(yaw), np.sin(yaw)
            local = objects.part_offset(o.shape, o.size, part or None) + s.offset
            world = pos + [c * local[0] - si * local[1], si * local[0] + c * local[1], local[2]]
            tool_yaw = (yaw + np.radians(s.yaw) + np.pi) % (2 * np.pi) - np.pi  # the tool takes [-pi, pi]
            if s.tool:
                tool_yaw = tuple(np.radians(s.tool))
            out.append((world, tool_yaw, float(s.gripper == "open")))
        return out

    def conditions(self, sim, answer: str | None = "") -> dict[str, bool]:
        """Each success predicate separately, so a 0 score says which part failed.
        sim gives body_pos(name), model, data, seed. Plain bools: numpy bools break HUD's JSON grading.
        An impossible variant skips `success` and checks nothing was knocked off the table instead."""
        if not self.feasible(sim.seed):
            free = [o.name for o in self.objects if self.present(o, sim.seed) and o.shape not in objects.ARTICULATED + objects.FIXED]
            out = {"on_table": all(bool(sim.body_pos(n)[2] > 0) for n in free)}
        else:
            out = {kind: all(bool(self._holds(kind, q, sim)) for q in (p if isinstance(p, list) else [p]))
                   for kind, p in self.success.items()}
        return {**out, **self.answer_conditions(sim.seed, answer)}

    def final_state(self, sim) -> dict:
        """Numbers behind the grade for trace review: object positions (mm), drawer open fraction,
        and what the arm still touches. Review agents couldn't tell "drawer 6% open" from "never opened"."""
        out = {"variant": self.variant(sim.seed), "feasible": self.feasible(sim.seed)} if self.variants else {}
        for o in (o for o in self.objects if self.present(o, sim.seed)):
            pos = [round(float(v) * 1000) for v in sim.body_pos(o.name)]
            out[o.name] = {"pos_mm": pos, "held": bool(objects.touching_robot(sim.model, sim.data, o.name))}
            if o.shape in objects.ARTICULATED + ("lidbox",):
                out[o.name]["open"] = round(objects.joint_fraction(sim.model, sim.data, o.name)[0], 3)
            if o.shape == "seesaw":
                out[o.name]["tilt_deg"] = round(objects.seesaw_tilt(sim.model, sim.data, o.name), 1)
        return out

    def is_success(self, sim, answer: str | None = "") -> bool:
        return all(self.conditions(sim, answer).values())

    def _holds(self, kind: str, p, sim):
        if kind == "stacked":  # each centred on the one below and one block-height up, the bottom on the table
            on = all(np.linalg.norm(sim.body_pos(b)[:2] - sim.body_pos(a)[:2]) < self.obj(a).size[0] / 2 and
                     abs(sim.body_pos(b)[2] - sim.body_pos(a)[2] - self.obj(a).size[2]) < 0.01
                     for a, b in zip(p.order, p.order[1:]))
            return on and self._resting(sim, p.order[0]) and all(self._released(sim, n) for n in p.order)
        if kind == "clear":  # centres off the marking (circle or rectangle, in the zone's frame), on the table
            z, zone = sim.data.body(p.zone), self.obj(p.zone)
            half = np.array(zone.size[:2]) / 2
            for n in p.objects:
                local = (z.xmat.reshape(3, 3).T @ (sim.body_pos(n) - z.xpos))[:2]
                over = np.linalg.norm(local) < half[0] if len(zone.size) == 1 else all(abs(local) < half)
                if over or sim.body_pos(n)[2] < 0 or not self._released(sim, n):
                    return False
            return True
        if kind == "at_goal":
            goals = self.goals(sim.seed)
            return all(np.linalg.norm(sim.body_pos(n)[:2] - goals[n][0][:2]) < p.radius and self._resting(sim, n)
                       for n in p.objects)
        if kind == "unmoved":
            start = self.sample(sim.seed)
            return all(np.linalg.norm(sim.body_pos(n) - start[n][0]) < p.tol for n in p.objects)
        o, pos = self.obj(p.object), sim.body_pos(p.object)
        if kind == "tipped":
            up = sim.data.body(p.object).xmat[8]  # z component of the body's z axis
            return np.degrees(np.arccos(np.clip(up, -1, 1))) >= p.angle and self._released(sim, p.object)
        if kind == "overhang":  # box corners along the platform's +x, past its face; held up, not fallen
            plat, size = sim.data.body(p.platform), self.obj(p.platform).size
            rot, axis = sim.data.body(p.object).xmat.reshape(3, 3), plat.xmat.reshape(3, 3)[:, 0]
            reach = (pos - plat.xpos) @ axis + np.abs(axis @ rot) @ (np.array(o.size) / 2) - size[0] / 2
            return reach >= p.beyond and pos[2] > plat.xpos[2] + size[2] and self._released(sim, p.object)
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
