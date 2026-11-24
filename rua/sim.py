"""MuJoCo tabletop with a Franka Panda: build the scene, move the end effector, observe.

No HUD or LLM code here. The HUD bridge wraps this later.
"""

import mink
import mujoco
import numpy as np
from robot_descriptions import panda_mj_description

from hud.environment.robot.orientation import euler_to_xyzw
import objects
from spec import COLORS, TaskSpec

TABLE_Z = 0.0  # robot base sits on the table top
PARK = (0.25, 0.0, 0.55)  # start pose: hand pulled back so the top camera sees the table
OPEN, CLOSED = 255.0, 0.0  # Menagerie gripper actuator range
DT_MOVE = 2.0  # seconds per metre-ish of travel; slow moves keep grasps (see docs/decisions.md)


def build_spec(task: TaskSpec) -> mujoco.MjSpec:
    spec = mujoco.MjSpec.from_file(panda_mj_description.MJCF_PATH)
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 640, 480
    # Menagerie has no end-effector site; put one between the fingertips.
    # Menagerie's gripper squeezes only ~2.5 N on a 5 cm object (force grows with how far the
    # fingers are from shut), so cubes slid out depending on wrist angle. 10x stiffer gives ~25 N,
    # still under a real Franka's ~70 N.
    grip = spec.actuator("actuator8")
    grip.gainprm[0] *= 10
    grip.biasprm[1] *= 10
    grip.biasprm[2] *= 10
    # Menagerie's implicitfast integrator damps the arm in a way the contact solver doesn't see,
    # so grasped objects crept ~2 cm along the pads per lift (3 cm pegs fell out). RK4 at 1 ms
    # holds them (<3 mm); at 2 ms the stiff gripper chattered and drawer tabs slipped; Euler
    # lost 2-4 cm of arm tracking. Costs ~3x sim time.
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_RK4
    spec.option.timestep = 0.001
    hand = spec.body("hand")
    # Invisible: a visible marker would act as an aiming crosshair (a deliberate knob, not a default).
    hand.add_site(name="tcp", pos=[0, 0, 0.1034], rgba=[0, 0, 0, 0])
    # Wrist camera as mounted on real arms: on the wrist above the hand, tilted to look at the
    # fingertips, which sit at the bottom of the image (hand frame: +z points down the fingers).
    hand.add_camera(name="wrist", pos=[0.15, 0, 0], xyaxes=look_at([0.15, 0, 0], [0, 0, 0.2], up=(1, 0, 0)), fovy=65)
    w = spec.worldbody
    w.add_light(pos=[-0.5, 1.0, 2.0], dir=[0.5, -0.5, -1], diffuse=[0.6, 0.6, 0.6])
    w.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[3, 3, 0.1], pos=[0, 0, -0.75], rgba=[0.3, 0.3, 0.3, 1])
    # Runs to x=1.15, past the arm's reach (tcp x <= ~0.90 at table height even with a tilted
    # wrist), so tasks can place objects that only a tool can bring back.
    w.add_geom(name="table", type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.7, 0.8, 0.375],
               pos=[0.45, 0, TABLE_Z - 0.375], rgba=[0.6, 0.45, 0.3, 1])
    for o in task.objects:  # placed per seed in Sim.reset
        objects.add(spec, o.name, o.shape, o.size, COLORS[o.color], o.mass, o.travel, o.damping, o.hole)
    # Over the robot's left shoulder: roughly image up = robot forward, image left = robot
    # left (no accidental mirroring), offset sideways so the arm doesn't hide the workspace.
    w.add_camera(name="shoulder", pos=[-0.3, 0.45, 1.2], xyaxes=look_at([-0.3, 0.45, 1.2], [0.5, 0, 0]), fovy=60)
    # Straight down over the workspace: image up = +x (forward), image left = +y (robot left).
    # Table position maps directly to image position, so no depth guessing for x/y.
    w.add_camera(name="top", pos=[0.45, 0, 1.5], xyaxes=[0, -1, 0, 1, 0, 0], fovy=45)
    return spec


def down_quat(yaw: float) -> list[float]:
    """wxyz for a straight-down gripper, via HUD's roll/pitch/yaw conversion (what the agent sends)."""
    x, y, z, w = euler_to_xyzw(np.pi, 0.0, yaw)
    return [w, x, y, z]


def look_at(pos, target, up=(0, 0, 1)) -> list:
    """Camera xyaxes (image right, image up) for a camera at pos looking at target."""
    f = np.subtract(target, pos) / np.linalg.norm(np.subtract(target, pos))
    right = np.cross(f, up)
    right /= np.linalg.norm(right)
    return [*right, *np.cross(right, f)]


class Sim:
    def __init__(self, task: TaskSpec, image_size: int = 256):
        self.task = task
        self.model = build_spec(task).compile()
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, image_size, image_size)
        self.ik = mink.Configuration(self.model)
        self.tcp = self.model.site("tcp").id
        self.home = self.model.key_qpos[0].copy()  # IK prefers this posture (see _solve_ik)
        self.reset(0)

    def reset(self, seed: int) -> None:
        """Arm to the parked pose, objects to this seed's sampled poses, then let everything settle."""
        self.seed = seed  # success checks may compare against the start poses
        mujoco.mj_resetDataKeyframe(self.model, self.data, 0)  # Menagerie "home"
        for name, (pos, yaw) in self.task.sample(seed).items():
            body, quat = self.model.body(name), [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
            if body.jntnum[0] and self.model.jnt_type[body.jntadr[0]] == mujoco.mjtJoint.mjJNT_FREE:
                adr = self.model.jnt_qposadr[body.jntadr[0]]
                self.data.qpos[adr:adr + 7] = [*pos, *quat]
            else:  # fixed to the table (templates): move the body itself
                self.model.body_pos[body.id], self.model.body_quat[body.id] = pos, quat
        for o in self.task.objects:
            if o.shape == "drawer":
                self.data.qpos[self.model.joint(f"{o.name}_slide").qposadr[0]] = o.start * o.travel
        mujoco.mj_forward(self.model, self.data)  # refresh poses before reading them
        self.move_to(PARK)  # also lets the objects settle

    def track(self, pos, quat_wxyz, gripper: float, seconds: float) -> None:
        """One control tick: IK toward a TCP pose, set the gripper (1 open, 0 closed), run physics.

        The caller must move targets gradually (DirectControl does): a single far jump
        drops grasped objects.
        """
        target = mink.SE3.from_rotation_and_translation(mink.SO3(np.asarray(quat_wxyz, float)), np.asarray(pos, float))
        self.data.ctrl[:7] = self._solve_ik(target)
        self.data.ctrl[7] = OPEN * float(np.clip(gripper, 0, 1))
        self._run(seconds)

    def move_to(self, pos, yaw: float | None = None, gripper: float = 1.0) -> float:
        """Scripted move for tests and oracles: interpolate, then settle. Returns end error in m.

        yaw: gripper straight down with this tool yaw (same convention the agent's tool uses);
        None keeps the current hand orientation.
        """
        start = self.data.site_xpos[self.tcp].copy()
        current = mink.SO3.from_matrix(self.data.site_xmat[self.tcp].reshape(3, 3))
        quat = current.wxyz if yaw is None else down_quat(yaw)
        ticks = max(10, int(20 * DT_MOVE * np.linalg.norm(start - pos)))
        for k in range(1, ticks + 1):
            self.track(start + (np.asarray(pos) - start) * k / ticks, quat, gripper, 0.05)
        self._run(0.5)
        return float(np.linalg.norm(self.data.site_xpos[self.tcp] - pos))

    def observe(self, cameras=("shoulder",)) -> dict:
        """Images are rendered only for the cameras asked for; each extra view costs tokens."""
        return {
            "images": {c: self._render(c) for c in cameras},
            "tcp_pos": self.data.site_xpos[self.tcp].copy(),
            "tcp_quat_wxyz": mink.SO3.from_matrix(self.data.site_xmat[self.tcp].reshape(3, 3)).wxyz,
            # 1 open, 0 shut; clipped because contact can push the fingers past their limits (read 1.3)
            "gripper_opening": float(np.clip((self.data.qpos[7] + self.data.qpos[8]) / 0.08, 0, 1)),
        }

    def body_pos(self, name: str) -> np.ndarray:
        return self.data.body(name).xpos.copy()

    def success(self) -> bool:
        return self.task.is_success(self)

    def _solve_ik(self, target: mink.SE3) -> np.ndarray:
        self.ik.update(self.data.qpos)
        task = mink.FrameTask("tcp", "site", position_cost=1.0, orientation_cost=0.5)
        task.set_target(target)
        # Anchor the arm's spare freedom to a fixed pose; anchoring to "wherever it is now" let the
        # wrist swing ~16 deg mid-lift and fling grasped objects.
        posture = mink.PostureTask(self.model, cost=1e-2)
        posture.set_target(self.home)
        for _ in range(50):
            v = mink.solve_ik(self.ik, [task, posture], 0.02, "daqp", damping=1e-3,
                              limits=[mink.ConfigurationLimit(self.model)])
            self.ik.integrate_inplace(v, 0.02)
            if np.linalg.norm(task.compute_error(self.ik)[:3]) < 1e-3:
                break
        return self.ik.q[:7].copy()

    def _render(self, camera: str) -> np.ndarray:
        self.renderer.update_scene(self.data, camera=camera)
        return self.renderer.render()

    def _run(self, seconds: float) -> None:
        for _ in range(int(seconds / self.model.opt.timestep)):
            mujoco.mj_step(self.model, self.data)
