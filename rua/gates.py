"""Discriminator, free gates: run on every generated spec before any model touches it.

    python rua/gates.py lift_cube            # 5 seeds
    SEEDS=10 python rua/gates.py lift_cube
    python rua/gates.py --asset mug          # library admission checks for one catalog asset

Each failure prints a reason the generator can act on. Exit code 1 if any gate fails.
The harness-level truth test (rua/checks.py) is gate 4 and runs once per harness change.
"""

import os
import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

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


def asset_checks(asset: str, render_dir: Path) -> list[tuple[str, str | None]]:
    """Admission checks, run once per library asset (not per task): (check, failure or None).
    Each catches a known scanned-mesh failure: wrong scale, bad inertia, hulls that tunnel,
    one hull filling a cavity, a shape the gripper can't hold."""
    card, out = objects.CATALOG[asset], []
    objs = [spec.Obj(name="obj", shape="asset", asset=asset, x=(0.5, 0.5), y=(0, 0)),
            spec.Obj(name="probe", shape="sphere", size=[0.02], color="red", mass=0.01, x=(0.5, 0.5), y=(-0.4, -0.4))]
    try:  # (a) compiles with the robot scene
        sim = Sim(spec.TaskSpec.model_construct(name=asset, prompt="", objects=objs, success={}, oracle=[]), image_size=480)
    except Exception as e:
        return [("compile", f"{type(e).__name__}: {e}")]
    out.append(("compile", None))
    size, card_size = objects.measure(asset)[1], np.array(card["size"])  # (b)
    err = np.abs(size - card_size) / card_size
    out.append(("size", None if err.max() < 0.15 else f"bbox {np.round(size, 3)} vs card {card_size} ({err.max():.0%} off)"))
    spawn, half = sim.task.sample(0)["obj"][0], card_size / 2

    def tilt() -> float:  # degrees between the body's z axis and world z
        return float(np.degrees(np.arccos(np.clip(sim.data.body("obj").xmat[8], -1, 1))))

    def overlap() -> float:  # deepest contact on the object (m)
        body = sim.model.body("obj").id
        return max([-c.dist for c in sim.data.contact[: sim.data.ncon]
                    if body in (sim.model.geom_bodyid[c.geom1], sim.model.geom_bodyid[c.geom2])], default=0.0)

    sim._run(2.0)  # (c) rest in the spawn pose (reset already settled it once)
    drift = np.linalg.norm(sim.body_pos("obj") - spawn)
    out.append(("rest", None if drift < 0.01 and overlap() < PENETRATION_TOL else
                f"drifted {drift * 100:.1f} cm, tilt {tilt():.0f} deg, overlap {overlap() * 1000:.0f} mm"))
    for c in ("top", "shoulder"):  # (g) for a human glance
        Image.fromarray(sim._render(c)).save(render_dir / f"{asset}_{c}.png")
    sim.reset(0)  # (d) 5 cm drop
    adr = sim.model.jnt_qposadr[sim.model.body("obj").jntadr[0]]
    sim.data.qpos[adr + 2] += 0.05
    sim._run(2.0)
    z, speed = sim.body_pos("obj")[2], objects.free_speed(sim.data, "obj")
    out.append(("drop", None if speed < 0.02 and z > 0 and overlap() < PENETRATION_TOL else
                f"after 2 s: speed {speed:.2f} m/s, centre z {z * 100:.1f} cm, tilt {tilt():.0f} deg, overlap {overlap() * 1000:.0f} mm"))
    if card["hollow"]:  # (e) a 2 cm sphere dropped over the centre must end up in the cavity
        sim.reset(0)
        padr = sim.model.jnt_qposadr[sim.model.body("probe").jntadr[0]]
        sim.data.qpos[padr:padr + 3] = spawn + [0, 0, half[2] + 0.03]
        sim._run(2.0)
        p = sim.body_pos("probe") - sim.body_pos("obj")
        inside = np.linalg.norm(p[:2]) < min(half[:2]) and p[2] < half[2] - 0.01
        out.append(("cavity", None if inside else f"probe ended {np.round(p * 100, 1)} cm from the centre (cavity filled?)"))
    if card["graspable"]:  # (f) top-down grasp over the centre of mass, across the narrow side, lift 10 cm, hold 1 s
        sim.reset(0)
        yaw = 0.0 if half[1] <= half[0] else np.pi / 2  # tool yaw 0 closes the fingers along world y
        # Fingertips 3 cm below the surface under the COM (a bbox centre can be air: a mallet's
        # handle lies far below its head's top), and at least 1.5 cm up so they clear the table.
        com = sim.data.body("obj").xipos.copy()
        top = 1.0 - mujoco.mj_ray(sim.model, sim.data, np.array([*com[:2], 1.0]), np.array([0, 0, -1.0]),
                                  np.array([0, 0, 0, 1, 0, 0], np.uint8), 1, -1, np.zeros(1, np.int32))
        grip = np.array([*com[:2], max(top - 0.03, 0.015)])
        sim.move_to(grip + [0, 0, 0.15], yaw=yaw)
        sim.move_to(grip, yaw=yaw)
        sim.move_to(grip, yaw=yaw, gripper=0)
        sim.move_to(grip + [0, 0, 0.10], yaw=yaw, gripper=0)
        sim._run(1.0)
        rise = sim.body_pos("obj")[2] - spawn[2]
        held = rise > 0.08 and objects.touching_robot(sim.model, sim.data, "obj")
        out.append(("grasp", None if held else f"rose {rise * 100:.1f} cm after a 10 cm lift"))
    return out


if __name__ == "__main__":
    if sys.argv[1] == "--asset":
        render_dir = Path(os.environ.get("RENDER_DIR", Path(__file__).parents[1] / "runs" / "asset_renders"))
        render_dir.mkdir(parents=True, exist_ok=True)
        results = asset_checks(sys.argv[2], render_dir)
        for check, reason in results:
            print(f"{'FAIL' if reason else 'ok  '} {check}{': ' + reason if reason else ''}")
        ok = not any(r for _, r in results)
        print(f"{sys.argv[2]}: {'ADMIT' if ok else 'REJECT'} (renders in {render_dir})")
        sys.exit(0 if ok else 1)
    name, seeds = sys.argv[1], int(os.environ.get("SEEDS", "5"))
    failures = run_gates(name, seeds)
    for gate, seed, reason in failures:
        print(f"FAIL {gate} seed={seed}: {reason}")
    print(f"{name}: {'PASS' if not failures else 'FAIL'} ({seeds} seeds, gates: schema, settle, joints, reach, visible, trivial, oracle, robust)")
    sys.exit(1 if failures else 0)
