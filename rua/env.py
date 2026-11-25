"""HUD environment: serves the tabletop sim to an LLM as a `move_to` tool.

    python -m hud.environment.server rua/env.py
"""

import numpy as np
from mcp.types import TextContent

from hud.environment import Environment
from hud.environment.robot import DirectControl
import spec
from tabletop import CAMERAS, DIMS, FPS, TabletopBridge, make_env

CAMERA_NOTES = {
    "top": "The top image looks straight down: image up is +x, image left is +y.",
    "wrist": "The wrist camera is mounted on the wrist, tilted down at the fingers: the two fingertips "
    "are at the bottom of the wrist image, and an object between them in that image is between the fingers.",
    "shoulder": "The shoulder image looks over the robot's left shoulder toward +x.",
}
GRIPPER = DIMS.index("gripper")


def grasp_sentence(opening: float, close_commanded: bool) -> str:
    """Name what the finger opening means (HUD's libero grasp line). 0.62 open = holding the 5 cm cube."""
    if close_commanded:
        return "fingers met; nothing between them" if opening < 0.025 else "fingers did not meet"
    # Commanded open but held partly shut means something is in the way; say so (7 sol episodes got
    # no line at all here and couldn't tell anything was wrong).
    return "open" if opening > 0.75 else "fingers blocked from opening"


class GraspControl(DirectControl):
    """Stock move_to, plus one line on the result saying whether the fingers hold something."""

    def _render(self, obs, played, proprio, *, timed_out, goal):
        content = super()._render(obs, played, proprio, timed_out=timed_out, goal=goal)
        opening = float(np.asarray(obs["data"]["state"]).reshape(-1)[GRIPPER])
        closing = self._command is not None and self._command[GRIPPER] < 0.5
        stall = stall_sentence(obs, goal)
        if stall and self._command is not None:
            # After a stall, later moves start from where the hand really is, not the unreached
            # target (otherwise a z-only move keeps dragging x toward the old target).
            self._command[:3] = np.asarray(obs["data"]["state"]).reshape(-1)[:3]
        lines = [grasp_sentence(opening, closing), stall]
        extra = "\n".join(line for line in lines if line)
        if extra:
            content[0] = TextContent(type="text", text=f"{content[0].text}\n{extra}")
        return content


def stall_sentence(obs, goal) -> str | None:
    """Say plainly when the hand stopped short, instead of leaving only a numeric 'off' residual."""
    if goal is None:
        return None
    state = np.asarray(obs["data"]["state"]).reshape(-1)
    gap = float(np.linalg.norm(state[:3] - np.asarray(goal)[:3]))
    if gap > 0.02:
        return f"stopped {gap * 100:.1f} cm short of the target: blocked or out of reach"
    return None


env = Environment(name="tabletop")
sim = env.gym(make_env, fps=FPS, bridge=TabletopBridge)

GraspControl(
    max_step={"gripper": 2.0},  # gripper switches in one tick
    speed=0.25,
    timeout=20.0,
    notes=(
        "Positions are world-frame meters of the point between the fingertips. The robot base "
        "is at the origin on the table top (z=0). +x is forward from the base, +y is the robot's "
        "left, +z up. Gripper straight down is roll=pi (same as -pi), pitch=0; roll=0 points it up. "
        "positive yaw turns the gripper counter-clockwise seen from above. At yaw 0 the fingers "
        "close along y (left-right); at yaw +-pi/2 they close along x (forward-back). gripper: 1 open, 0 closed (values >= 0.5 open, "
        "below close fully); "
        "the state's gripper value is how open the fingers are (1 open, 0 shut). "
        + " ".join(CAMERA_NOTES[c] for c in CAMERAS)
    ),
).attach(sim)


@env.template()
async def episode(task: str = "lift_cube", seed: int = 0):
    ep = await sim.reset(task=task, seed=seed)
    answer = yield {"prompt": ep["prompt"]}
    # The sim process never sees the reply, so predicates on it (IMPOSSIBLE claims) are added here.
    res = await sim.result()
    conditions = {**res["conditions"], **spec.load(task).answer_conditions(seed, answer)}
    ok = all(conditions.values())
    yield {**res, "score": float(ok), "success": ok, "conditions": conditions}
