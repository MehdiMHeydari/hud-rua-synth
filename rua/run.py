"""Run an LLM agent on tabletop tasks through the HUD gateway, env served locally.

    python rua/run.py                                            # 1 episode of lift_cube on luna
    EPISODES=20 CONCURRENCY=5 HUD_LLM_MODEL=gpt-6-sol python rua/run.py
    HUD_LLM_MODEL=oracle python rua/run.py                       # scripted solver, no LLM cost

Settings (all recorded in the job name): STEPS (40), EFFORT (medium), CAMERAS (top,wrist).
SEED0 (0) offsets the seeds, so confirmation runs can use fresh object placements.
Every run is appended to runs/log.jsonl with its settings, result, job id and estimated cost
(exact per-trace cost is on hud.ai; the SDK doesn't expose it).

HUD_API_KEY and HUD_LLM_MODEL come from the environment or .env.
"""

import asyncio
import json
import math
import os
import time
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
SEED0 = int(os.environ.get("SEED0", "0"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "1"))

SYSTEM_PROMPT = (
    "You control a Franka Panda robot arm on a table through the move_to tool. Each call moves "
    "the arm until it reaches the target or stops, then returns the camera image and the pose it "
    "ended on. Check the returned image after every move. Reply without a tool call when the task "
    f"is done or cannot be done. You have {STEPS} tool calls."
)


async def main() -> None:
    tasks = [Task(env="tabletop", id="episode", args={"task": TASK, "seed": SEED0 + i}) for i in range(EPISODES)]
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
    k, n = sum((r.reward or 0) >= 1 for r in job.runs), len(job.runs)
    errors = sum(bool(r.trace.is_error) for r in job.runs)  # crashed rollouts are not model failures
    lo, hi = wilson(k, n)
    verdict = "too easy" if lo > 0.30 else "too hard" if hi < 0.05 else "in band" if 0.05 <= k / n <= 0.30 else "unclear"
    if errors:
        verdict = f"INVALID: {errors}/{n} rollouts errored (harness/spec bug, not model failures)"
    cost = n * COST_PER_EPISODE.get(MODEL, 0.0)
    print(f"{TASK}: {k}/{n} = {k / n:.0%} (90% CI {lo:.0%}-{hi:.0%}) -> {verdict}; est cost ${cost:.2f}")
    log = Path(__file__).parents[1] / "runs" / "log.jsonl"
    log.parent.mkdir(exist_ok=True)
    with log.open("a") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M"), "task": TASK, "model": MODEL, "steps": STEPS,
                            "effort": EFFORT, "cameras": os.environ.get("CAMERAS", "top,wrist"), "seed0": SEED0,
                            "k": k, "n": n, "errors": errors, "job": job.id, "est_cost": round(cost, 3)}) + "\n")


# Rough $/episode at 40 steps, from hud.ai trace pages; exact cost is on each trace.
COST_PER_EPISODE = {"gpt-6-luna": 0.015, "gpt-6-sol": 0.12, "oracle": 0.0}


def wilson(k: int, n: int, z: float = 1.645) -> tuple[float, float]:
    """90% Wilson interval for a pass rate: at n=10, 2/10 is roughly 6-48%, so read it as a range."""
    if n == 0:
        return 0.0, 1.0
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


if __name__ == "__main__":
    asyncio.run(main())
