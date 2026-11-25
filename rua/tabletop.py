"""Gym wrapper around Sim, plus the grading bridge. HUD's gym path serves this.

Action and state share one layout:
    tcp.x, tcp.y, tcp.z, tcp_quat.qx/qy/qz/qw, gripper   (gripper: 1 open, 0 closed)

CAMERAS (launch-time, default "top,wrist") picks the views: top, wrist, shoulder. It changes
what images the agent gets, so it is fixed per env process, not per task.
"""

import os

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from hud.environment.robot import GymBridge
import spec
from sim import Sim

FPS = 20
IMAGE = int(os.environ.get("IMAGE", 256))  # px per camera, launch-time like CAMERAS
CAMERAS = tuple(os.environ.get("CAMERAS", "top,wrist").split(","))
DIMS = ["tcp.x", "tcp.y", "tcp.z", "tcp_quat.qx", "tcp_quat.qy", "tcp_quat.qz", "tcp_quat.qw", "gripper"]
CONTRACT = {
    "control_rate": FPS,
    "features": {
        **{c: {"role": "observation", "type": "rgb", "shape": [IMAGE, IMAGE, 3]} for c in CAMERAS},
        "state": {"role": "observation", "type": "ee_abs", "names": DIMS},
        "action": {
            "role": "action",
            "type": "ee_abs",
            "names": DIMS,
            "limits": {"min": [-0.2, -0.7, 0.0, -1, -1, -1, -1, 0], "max": [0.9, 0.7, 0.8, 1, 1, 1, 1, 1]},
        },
    },
}

class TabletopEnv(gym.Env):
    metadata = {"render_fps": FPS}

    def __init__(self, task: str = "lift_cube"):
        self.spec = spec.load(task)  # tasks/<task>.yaml
        self.task_description = self.spec.prompt
        self.sim = Sim(self.spec, IMAGE)
        self.action_space = spaces.Box(-np.inf, np.inf, shape=(8,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.sim.reset(seed or 0)  # seed picks the object placement
        return self._obs(), {}

    def step(self, action):
        a = np.asarray(action, dtype=np.float64)
        qx, qy, qz, qw = a[3:7]
        # Binary gripper (as in HUD's libero env): an in-between command like 0.62 would hold the
        # fingers at that width with no squeeze and drop the object.
        self.sim.track(a[:3], [qw, qx, qy, qz], float(a[7] >= 0.5), 1.0 / FPS)
        # Never terminate early: the episode is graded on the final state (see TabletopBridge).
        return self._obs(), 0.0, False, False, {}

    def success(self) -> bool:
        return self.sim.success()

    def _obs(self):
        o = self.sim.observe(CAMERAS)
        w, x, y, z = o["tcp_quat_wxyz"]
        # Rounded to 1 mm / 0.001: contact jitter while squeezing an object otherwise stays above
        # DirectControl's "stopped moving" threshold (1e-4), so every grasp ran to the 20 s timeout.
        state = np.round([*o["tcp_pos"], x, y, z, w, o["gripper_opening"]], 3).astype(np.float32)
        return {**o["images"], "state": state}


def make_env(task: str = "lift_cube") -> TabletopEnv:
    return TabletopEnv(task)


class TabletopBridge(GymBridge):
    """Grade the state the agent leaves the scene in, not the first frame the goal flickers true."""

    def __init__(self, *args, **kwargs):
        kwargs.pop("contract", None)
        super().__init__(*args, contract=None, **kwargs)
        self.contract = CONTRACT  # in code, next to the observation it describes

    def result_slots(self):
        conditions = self.env.spec.conditions(self.env.sim)  # logged with the grade for trace review
        ok = all(conditions.values())
        return [{"score": float(ok), "success": ok, "conditions": conditions,
                 "final_state": self.env.spec.final_state(self.env.sim)}]
