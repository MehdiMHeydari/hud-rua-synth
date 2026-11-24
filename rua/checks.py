"""Truth test: is everything we tell the agent actually true? Runs before any model, $0.

    python rua/checks.py

Each check sets up a known situation and compares it with what the agent would be told
(tool notes, grasp line, stall line, camera layout). One check per harness failure mode found.
"""

import asyncio
from pathlib import Path

import numpy as np

from env import grasp_sentence
from hud.agents.base import Agent
from hud.environment.robot.orientation import euler_to_xyzw
from hud.eval import SubprocessRuntime, Task, Taskset
import spec
from sim import TABLE_Z, Sim

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, bool(ok), detail))


def tool_quat(roll, pitch, yaw):
    """The wxyz quaternion the sim receives when the agent sends roll/pitch/yaw (via HUD's own conversion)."""
    x, y, z, w = euler_to_xyzw(roll, pitch, yaw)
    return [w, x, y, z]


def hold(sim: Sim, pos, rpy, gripper=1.0, seconds=2.0):
    for _ in range(int(seconds / 0.05)):
        sim.track(pos, tool_quat(*rpy), gripper, 0.05)


def pixel(sim: Sim, camera: str, point, size=256):
    """Where a world point lands in a camera image (u right, v down)."""
    cam = sim.model.camera(camera).id
    R = sim.data.cam_xmat[cam].reshape(3, 3)
    p = R.T @ (np.asarray(point) - sim.data.cam_xpos[cam])
    f = (size / 2) / np.tan(np.radians(sim.model.cam_fovy[cam]) / 2)
    return np.array([size / 2 + f * p[0] / -p[2], size / 2 - f * p[1] / -p[2]])


def sim_checks() -> None:
    s = Sim(spec.load("lift_cube"))
    cube = s.body_pos("cube")
    above = [cube[0], cube[1], 0.25]

    # Notes: "straight down is roll=pi, pitch=0".
    hold(s, above, (np.pi, 0, 0))
    finger_dir = s.data.site_xmat[s.tcp].reshape(3, 3)[:, 2]
    check("roll=pi points the gripper down", finger_dir[2] < -0.99, f"finger axis {finger_dir.round(2)}")

    # Notes: "positive yaw turns the gripper counter-clockwise seen from above".
    axis0 = s.data.site_xmat[s.tcp].reshape(3, 3)[:2, 1].copy()
    hold(s, above, (np.pi, 0, 0.5))
    axis1 = s.data.site_xmat[s.tcp].reshape(3, 3)[:2, 1]
    turn = np.degrees(np.arctan2(axis0[0] * axis1[1] - axis0[1] * axis1[0], axis0 @ axis1))
    check("yaw +0.5 turns counter-clockwise seen from above", 20 < turn < 35, f"turned {turn:+.0f} deg (ccw positive)")

    # Notes: "at yaw 0 the fingers close along y; at yaw +-pi/2 along x". 3 sol drawer episodes
    # wasted steps finding this out when the notes didn't say it.
    hold(s, above, (np.pi, 0, 0))
    y_axis = abs(s.data.site_xmat[s.tcp].reshape(3, 3)[:, 1])
    hold(s, above, (np.pi, 0, np.pi / 2))
    x_axis = abs(s.data.site_xmat[s.tcp].reshape(3, 3)[:, 1])
    check("fingers close along y at yaw 0, along x at yaw pi/2", y_axis[1] > 0.99 and x_axis[0] > 0.99,
          f"closing axis {y_axis.round(2)} then {x_axis.round(2)}")

    # Notes: "top image: image up is +x, image left is +y".
    u0, v0 = pixel(s, "top", [0.5, 0, 0])
    u1, v1 = pixel(s, "top", [0.6, 0, 0])
    u2, _ = pixel(s, "top", [0.5, 0.1, 0])
    check("top image: +x is up, +y is left", v1 < v0 - 5 and u2 < u0 - 5, f"+x moves v {v1 - v0:+.0f}px, +y moves u {u2 - u0:+.0f}px")

    # Notes: "an object between the fingertips in the wrist image is between the fingers".
    hold(s, [cube[0], cube[1], 0.03], (np.pi, 0, 0))
    u, _ = pixel(s, "wrist", cube)
    check("wrist image: aligned cube is centred between fingertips", abs(u - 128) < 15, f"cube at u={u:.0f} (centre 128)")
    hold(s, [cube[0], cube[1] + 0.07, 0.03], (np.pi, 0, 0))
    u_off, _ = pixel(s, "wrist", cube)
    check("wrist image: 7 cm misalignment is visible", abs(u_off - 128) > 40, f"cube at u={u_off:.0f}")

    # Grasp line on real physics: closing on nothing vs on the cube.
    s.reset(0)
    hold(s, [cube[0], cube[1] + 0.15, 0.03], (np.pi, 0, 0))
    hold(s, [cube[0], cube[1] + 0.15, 0.03], (np.pi, 0, 0), gripper=0, seconds=1)
    said = grasp_sentence(s.observe(())["gripper_opening"], True)
    check("grasp line: empty close", said == "fingers met; nothing between them", said)
    s.reset(0)
    hold(s, [cube[0], cube[1], 0.1], (np.pi, 0, 0))
    hold(s, [cube[0], cube[1], 0.025], (np.pi, 0, 0))
    hold(s, [cube[0], cube[1], 0.025], (np.pi, 0, 0), gripper=0, seconds=1)
    said = grasp_sentence(s.observe(())["gripper_opening"], True)
    check("grasp line: close on cube", said == "fingers did not meet", said)
    hold(s, [cube[0], cube[1], 0.2], (np.pi, 0, 0), gripper=0)
    check("closed grasp holds the cube on lift", s.body_pos("cube")[2] > TABLE_Z + 0.1, f"cube z={s.body_pos('cube')[2]:.3f}")

    check("grasp line: open command blocked", grasp_sentence(0.5, False) == "fingers blocked from opening",
          grasp_sentence(0.5, False))

    # Every reported number stays in range: random moves with contact, gripper reading in [0, 1].
    rng, readings = np.random.default_rng(0), []
    s.reset(0)
    for _ in range(12):
        s.move_to(rng.uniform([0.3, -0.2, 0.0], [0.7, 0.2, 0.2]), yaw=rng.uniform(-3, 3), gripper=float(rng.random() < 0.5))
        readings.append(s.observe(())["gripper_opening"])
    check("gripper reading stays in [0, 1]", 0 <= min(readings) and max(readings) <= 1, f"range {min(readings):.2f}..{max(readings):.2f}")

    # An extreme wrist tilt near the base is hard to reach (fair, reported by the stall line), but
    # the arm must recover once gripper-down is asked again (one sol episode looked "stuck" after it).
    s.reset(0)
    hold(s, [0.30, 0, 0.15], (np.pi, -1.57, 0), seconds=3)
    hold(s, [0.5, 0, 0.2], (np.pi, 0, 0), seconds=3)
    back = np.linalg.norm(s.data.site_xpos[s.tcp] - [0.5, 0, 0.2])
    check("arm recovers after an extreme wrist tilt", back < 0.015, f"{back * 100:.1f} cm off after returning")


def _move(note, **dims):
    (name, value), *rest = dims.items()
    full = lambda k: k if k == "gripper" else f"tcp.{k}"
    return {"target": {"name": full(name), "value": value},
            "others": [{"name": full(k), "value": v} for k, v in rest], "note": note}


def _state(text: str) -> dict:
    line = next(l for l in text.splitlines() if l.startswith("state:"))
    return {k.split(".")[-1]: float(v) for k, v in (p.split("=") for p in line[6:].replace(",", " ").split())}


class ToolChecks(Agent):
    """Checks that only show up through HUD's real move_to tool."""

    async def __call__(self, run) -> None:
        client = await run.client.open("control")

        async def move(**dims):
            r = await client.call_tool("move_to", _move("check", **dims))
            return next(b.text for b in r.content if getattr(b, "type", None) == "text")

        # Pressing an open finger onto the cube's edge: the hand is blocked, so the move must end
        # when it stops, not run to the 20 s timeout (contact jitter used to keep it "moving").
        cube = spec.load("lift_cube").sample(0)["cube"][0]
        await move(x=cube[0], y=cube[1] + 0.04, z=0.15, yaw=0.0, gripper=1.0)  # one open finger over the cube's edge
        text = await move(z=0.0)
        played = int(text.split("Played ")[1].split()[0]) if "Played " in text else 0
        check("pressing on an object ends promptly", 0 < played <= 60, f"played {played} ticks (20/s); timeout is 400")
        await move(z=0.3)

        out = await move(x=0.89, y=0.0, z=0.6)  # in the box, out of the arm's reach
        check("stall: unreachable target is reported", "short of the target" in out, out.splitlines()[-1])
        before = _state(out)
        out = await move(z=0.3)  # names only z: x should come from where the hand is, not the old target
        after = _state(out)
        check("no stale target after a stall", "short of the target" not in out,
              f"x went {before['x']:.2f} -> {after['x']:.2f}; {out.splitlines()[-1]}")
        run.trace.content = "tool checks"


def main() -> None:
    sim_checks()
    task = Task(env="tabletop", id="episode", args={"task": "lift_cube", "seed": 0})
    runtime = SubprocessRuntime(Path(__file__).with_name("env.py"))
    asyncio.run(Taskset("truth test (tool path)", [task]).run(ToolChecks(), runtime=runtime))
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    print(f"{sum(ok for _, ok, _ in RESULTS)}/{len(RESULTS)} passed")


if __name__ == "__main__":
    main()
