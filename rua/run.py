"""Run an LLM agent on tabletop tasks through the HUD gateway, env served locally.

    python rua/run.py                                            # 1 episode of lift_cube on luna
    EPISODES=20 CONCURRENCY=5 HUD_LLM_MODEL=gpt-6-sol python rua/run.py
    HUD_LLM_MODEL=oracle python rua/run.py                       # scripted solver, no LLM cost

Settings (all recorded in the job name): STEPS (40), EFFORT (medium), CAMERAS (top,wrist).

HUD_API_KEY and HUD_LLM_MODEL come from the environment or .env.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

from hud.agents import create_agent  # noqa: E402 (needs the key loaded)
from hud.eval import SubprocessRuntime, Task, Taskset  # noqa: E402

MODEL = os.environ.get("HUD_LLM_MODEL", "gpt-6-luna")
TASK = os.environ.get("TASK", "lift_cube")
STEPS = int(os.environ.get("STEPS", "40"))  # literature uses 40-100; ~10x the oracle's 4 moves
EFFORT = os.environ.get("EFFORT", "medium")  # reasoning effort swings scores a lot: pin and record it
EPISODES = int(os.environ.get("EPISODES", "1"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "1"))

SYSTEM_PROMPT = (
    "You control a Franka Panda robot arm on a table through the move_to tool. Each call moves "
    "the arm until it reaches the target or stops, then returns the camera image and the pose it "
    "ended on. Check the returned image after every move. Reply without a tool call when the task "
    f"is done or cannot be done. You have {STEPS} tool calls."
)


async def main() -> None:
    tasks = [Task(env="tabletop", id="episode", args={"task": TASK, "seed": i}) for i in range(EPISODES)]
    if MODEL == "oracle":  # scripted solver: checks the harness, no LLM cost
        from oracle import Oracle

        agent = Oracle()
    else:
        agent = create_agent(MODEL, system_prompt=SYSTEM_PROMPT, max_steps=STEPS, reasoning={"effort": EFFORT})
    runtime = SubprocessRuntime(Path(__file__).with_name("env.py"))
    name = f"{MODEL} x {TASK} | effort={EFFORT} steps={STEPS} cams={os.environ.get('CAMERAS', 'top,wrist')}"
    job = await Taskset(name, tasks).run(agent, runtime=runtime, max_concurrent=CONCURRENCY)
    for run in job.runs:
        print(f"reward={run.reward} trace={run.trace_id}")
    print(f"job={job.id}")


if __name__ == "__main__":
    asyncio.run(main())
