"""Discriminator, free gates: run on every generated spec before any model touches it.

    python rua/gates.py lift_cube            # 5 seeds
    SEEDS=10 python rua/gates.py lift_cube

Each failure prints a reason the generator can act on. Exit code 1 if any gate fails.
The harness-level truth test (rua/checks.py) is gate 4 and runs once per harness change.
"""

import os
import sys

import mujoco
import numpy as np

import objects
import spec
from sim import Sim

SETTLE_TOL = 0.005  # metres an object may move while settling
PENETRATION_TOL = 0.002  # metres of allowed contact overlap after settling


def gate_settle(sim: Sim, seed: int) -> str | None:
    """Gate 2: objects rest where they were placed, without overlapping."""
    for name, (pos, _) in sim.task.sample(seed).items():
        moved = np.linalg.norm(sim.body_pos(name) - pos)
        if moved > SETTLE_TOL:
            return f"{name} moved {moved * 100:.1f} cm while settling (overlap, falling, or off the table)"
    for c in sim.data.contact[: sim.data.ncon]:
        if c.dist < -PENETRATION_TOL:
            pair = [mujoco.mj_id2name(sim.model, mujoco.mjtObj.mjOBJ_GEOM, g) or "unnamed" for g in (c.geom1, c.geom2)]
            return f"geoms {pair} overlap by {-c.dist * 1000:.0f} mm"
    return None


def gate_joints(sim: Sim, seed: int) -> str | None:
    """Articulated parts move freely: a 10 N pull for 1 s opens each drawer at least halfway.
    (Caught a drawer jammed against its own cabinet: 20 N moved it 1.5 cm.)"""
    for o in sim.task.objects:
        if o.shape not in objects.ARTICULATED:
            continue
        yaw = sim.task.sample(seed)[o.name][1]
        body = sim.model.body(f"{o.name}_drawer").id
        sim.data.xfrc_applied[body, :3] = [-10 * np.cos(yaw), -10 * np.sin(yaw), 0]
        sim._run(1.0)
        sim.data.xfrc_applied[body] = 0
        if (frac := objects.joint_fraction(sim.model, sim.data, o.name)[0]) < 0.5:
            return f"{o.name} opened only {frac:.0%} under a 10 N pull (jammed or too stiff)"
    return None


def gate_reach(sim: Sim, seed: int) -> str | None:
    """The open gripper can come down onto every object/part the oracle targets without hitting
    anything. (Caught a bar handle the Panda's wide hand couldn't reach past the cabinet.)"""
    for (pos, yaw, _), step in zip(sim.task.plan(seed), sim.task.oracle):
        if step.offset != (0, 0, 0):
            continue
        sim.reset(seed)
        sim.move_to(pos + [0, 0, 0.12], yaw=yaw, gripper=1)
        if (err := sim.move_to(pos, yaw=yaw, gripper=1)) > 0.015:
            return f"open gripper stopped {err * 100:.1f} cm short of {step.at} (collision on the way down?)"
    return None


def gate_robust(sim: Sim, seed: int, error: float = 0.005) -> str | None:
    """The oracle still succeeds with its placements 5 mm off (the tool only stops within ~1 cm, and
    agents localise worse). Caught peg_in_hole at 7 mm clearance: 8/16 at 5 mm off, so sol's 0/10
    measured the harness, not the model. Shifts the second half of the plan in 4 directions; 3/4 must pass."""
    plan, passed = sim.task.plan(seed), 0
    for k in range(4):
        sim.reset(seed)
        shift = error * np.array([np.cos(k * np.pi / 2 + 0.4), np.sin(k * np.pi / 2 + 0.4), 0])
        for i, (pos, yaw, gripper) in enumerate(plan):
            sim.move_to(pos + (shift if i >= len(plan) // 2 else 0), yaw=yaw, gripper=gripper)
        passed += sim.success()
    return None if passed >= 3 else f"oracle fails with 5 mm placement error ({passed}/4): precision tighter than the tool allows"


def gate_visible(sim: Sim, seed: int, margin: float = 0.05) -> str | None:
    """Every object starts at least 5 cm inside the top camera's view. (Hook cube spawned at the
    view's edge, so a small nudge lost it from view in 4/8 reviewed failures.)"""
    for name in sim.task.sample(seed):
        c = sim.body_pos(name)
        for dx, dy in ((margin, 0), (-margin, 0), (0, margin), (0, -margin)):
            u, v = sim.pixel("top", c + [dx, dy, 0])
            if not (0 <= u < 256 and 0 <= v < 256):
                return f"{name} is within {margin * 100:.0f} cm of the top camera's edge"
    return None


def gate_trivial(sim: Sim, seed: int, rng: np.random.Generator) -> str | None:
    """Gate 3: not already solved, and doing nothing or acting randomly doesn't solve it."""
    if sim.success():
        return "already solved at reset"
    sim.move_to(sim.data.site_xpos[sim.tcp])  # do nothing for a while
    sim._run(3.0)
    if sim.success():
        return "solved by doing nothing"
    sim.reset(seed)
    for _ in range(15):
        target = rng.uniform([0.2, -0.4, 0.02], [0.75, 0.4, 0.4])
        sim.move_to(target, yaw=rng.uniform(-np.pi, np.pi), gripper=float(rng.random() < 0.5))
        if sim.success():
            return "solved by random actions"
    return None


def gate_oracle(sim: Sim, seed: int) -> str | None:
    """Gate 5: the spec's scripted solution succeeds (in-process; rua/run.py checks the tool path)."""
    for i, (pos, yaw, gripper) in enumerate(sim.task.plan(seed)):
        err = sim.move_to(pos, yaw=yaw, gripper=gripper)
        if err > 0.02:
            return f"oracle step {i} stopped {err * 100:.1f} cm short (unreachable?)"
    return None if sim.success() else "oracle plan finished but the success check is false"


def run_gates(name: str, seeds: int) -> list[tuple[str, int, str]]:
    """Gate 1 (schema) is spec.load raising. Returns (gate, seed, reason) failures."""
    task = spec.load(name)
    sim, rng, failures = Sim(task), np.random.default_rng(0), []
    for seed in range(seeds):
        for gate, fn in (("settle", lambda: gate_settle(sim, seed)),
                         ("joints", lambda: gate_joints(sim, seed)),
                         ("reach", lambda: gate_reach(sim, seed)),
                         ("visible", lambda: gate_visible(sim, seed)),
                         ("trivial", lambda: gate_trivial(sim, seed, rng)),
                         ("oracle", lambda: gate_oracle(sim, seed)),
                         ("robust", lambda: gate_robust(sim, seed))):
            sim.reset(seed)
            if reason := fn():
                failures.append((gate, seed, reason))
    return failures


if __name__ == "__main__":
    name, seeds = sys.argv[1], int(os.environ.get("SEEDS", "5"))
    failures = run_gates(name, seeds)
    for gate, seed, reason in failures:
        print(f"FAIL {gate} seed={seed}: {reason}")
    print(f"{name}: {'PASS' if not failures else 'FAIL'} ({seeds} seeds, gates: schema, settle, joints, reach, visible, trivial, oracle, robust)")
    sys.exit(1 if failures else 0)
