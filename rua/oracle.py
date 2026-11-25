"""Scripted solver that follows a task spec's oracle plan through the real `move_to` tool.

If it doesn't score 100%, the task or the harness is broken, not the model. It knows object
poses from the spec's per-seed sampler, never from the sim.
"""

import numpy as np

import spec
from hud.agents.base import Agent
from hud.eval.run import Run


def move_args(pos, yaw: float | tuple, gripper: float) -> dict:
    """move_to arguments for a straight-down gripper at pos with the given yaw, or a (roll, pitch, yaw) tuple."""
    names = ["tcp.y", "tcp.z", "tcp.roll", "tcp.pitch", "tcp.yaw", "gripper"]
    values = [pos[1], pos[2], *(yaw if isinstance(yaw, tuple) else (np.pi, 0.0, yaw)), gripper]
    return {"target": {"name": "tcp.x", "value": float(pos[0])},
            "others": [{"name": n, "value": float(v)} for n, v in zip(names, values)],
            "note": "oracle"}


class Oracle(Agent):
    async def __call__(self, run: Run) -> None:
        args = run._args  # task + seed; the SDK has no public accessor
        task = spec.load(args.get("task", "lift_cube"))
        client = await run.client.open("control")
        for pos, yaw, gripper in task.plan(args.get("seed", 0)):
            await client.call_tool("move_to", move_args(pos, yaw, gripper))
        run.trace.content = task.oracle_answer(args.get("seed", 0))  # the final reply, graded on impossible variants
