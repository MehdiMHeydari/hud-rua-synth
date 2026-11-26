"""Run an LLM agent on tabletop tasks through the HUD gateway, env served locally.

    python rua/run.py                                            # 1 episode of lift_cube on luna
    EPISODES=20 CONCURRENCY=5 HUD_LLM_MODEL=gpt-6-sol python rua/run.py
    HUD_LLM_MODEL=oracle python rua/run.py                       # scripted solver, no LLM cost

Settings (all recorded in the job name): STEPS (40), EFFORT (medium), CAMERAS (top,wrist), IMAGE (256 px).
SEED0 (0) offsets the seeds, so confirmation runs can use fresh object placements.
Every run is appended to runs/log.jsonl with its settings, result, job id and estimated cost
(exact per-trace cost is on hud.ai; the SDK doesn't expose it).

HUD_API_KEY and HUD_LLM_MODEL come from the environment or .env.
"""

import asyncio
import json
import math
import os
import re
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

from hud.agents import create_agent  # noqa: E402 (needs the key loaded)
from hud.eval import SubprocessRuntime, Task, Taskset  # noqa: E402

MODEL = os.environ.get("HUD_LLM_MODEL", "gpt-6-luna")
TASK = os.environ.get("TASK", "lift_cube")
STEPS = int(os.environ.get("STEPS", "40"))  # sol 40; Astra 60 (Lukass: design for the top model, <=150 turns)
EFFORT = os.environ.get("EFFORT", "medium")  # reasoning effort swings scores a lot: pin and record it
EPISODES = int(os.environ.get("EPISODES", "1"))
SEED0 = int(os.environ.get("SEED0", "0"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "1"))
IMAGE = int(os.environ.get("IMAGE", "256"))  # read by tabletop.py; here only to record it

SYSTEM_PROMPT = (
    "You control a Franka Panda robot arm on a table through the move_to tool. Each call moves "
    "the arm until it reaches the target or stops, then returns the camera image and the pose it "
    "ended on. Check the returned image after every move. Reply without a tool call when the task "
    f"is done or cannot be done. You have {STEPS} tool calls."
)


def _jammed(run) -> bool:
    row = worst = 0
    for s in run.trace.steps:
        if s.source != "tool":
            continue
        text = " ".join(getattr(b, "text", "") or "" for b in (getattr(getattr(s, "result", None), "content", None) or []))
        m = re.search(r"stopped ([\d.]+) cm short", text)
        row = row + 1 if m and float(m.group(1)) >= 10 else 0
        worst = max(worst, row)
    return worst >= 2


async def main() -> None:
    tasks = [Task(env="tabletop", id="episode", args={"task": TASK, "seed": SEED0 + i}) for i in range(EPISODES)]
    if MODEL == "oracle":  # scripted solver: checks the harness, no LLM cost
        from oracle import Oracle

        agent = Oracle()
    else:
        agent = create_agent(MODEL, system_prompt=SYSTEM_PROMPT, max_steps=STEPS, reasoning={"effort": EFFORT})
    runtime = SubprocessRuntime(Path(__file__).with_name("env.py"))
    name = f"{MODEL} x {TASK} | effort={EFFORT} steps={STEPS} cams={os.environ.get('CAMERAS', 'top,wrist')} img={IMAGE}"
    job = await Taskset(name, tasks).run(agent, runtime=runtime, max_concurrent=CONCURRENCY)
    for run in job.runs:
        print(f"reward={run.reward} trace={run.trace_id}")
    print(f"job={job.id}")
    k, n = sum((r.reward or 0) >= 1 for r in job.runs), len(job.runs)
    errors = sum(bool(r.trace.is_error) for r in job.runs)  # crashed rollouts are not model failures
    # Episodes that used the whole step budget: a high count means "needs more steps", not "can't do it".
    # (Counted from the stop reason: trace.steps also holds tool results and setup, which inflated it.)
    capped = sum(r.trace.stop_reason == "max_steps" for r in job.runs if (r.reward or 0) < 1)
    # Context health: history is never trimmed, so failures with a small peak are not context loss.
    peak = max((max((getattr(s.usage, "prompt_tokens", 0) or 0 for s in r.trace.steps if s.source == "agent"), default=0)
                for r in job.runs), default=0)
    ends = dict(Counter(r.trace.stop_reason or "error" for r in job.runs if (r.reward or 0) < 1))
    # Harness flags, so a low score is not read as capability before these are zero:
    # jammed = failures with 2+ moves in a row ending 10+ cm short (the arm stuck at a joint limit, e.g. a
    # wrist turn through yaw -2.0: 10 of 17 hidden_weight failures); near_budget = failures that stopped in
    # the last 10% of the step budget (the model knows its budget and quits before the cap).
    jammed = sum(_jammed(r) for r in job.runs if (r.reward or 0) < 1)
    near = sum(sum(s.source == "tool" for s in r.trace.steps) >= 0.9 * STEPS for r in job.runs if (r.reward or 0) < 1)
    lo, hi = wilson(k, n)
    verdict = "too easy" if lo > 0.30 else "too hard" if hi < 0.05 else "in band" if 0.05 <= k / n <= 0.30 else "unclear"
    if errors:
        verdict = f"INVALID: {errors}/{n} rollouts errored (harness/spec bug, not model failures)"
    cost = n * COST_PER_EPISODE.get(MODEL, 0.0)
    print(f"{TASK}: {k}/{n} = {k / n:.0%} (90% CI {lo:.0%}-{hi:.0%}) -> {verdict}; "
          f"{capped} failures hit the {STEPS}-step cap, {jammed} jammed, {near} near budget; failures ended by {ends}; peak context {peak} tokens; "
          f"est cost ${cost:.2f}")
    save_traces(job)
    log = Path(__file__).parents[1] / "runs" / "log.jsonl"
    log.parent.mkdir(exist_ok=True)
    with log.open("a") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M"), "task": TASK, "model": MODEL, "steps": STEPS,
                            "effort": EFFORT, "cameras": os.environ.get("CAMERAS", "top,wrist"), "seed0": SEED0,
                            "image": IMAGE, "peak_tokens": peak, "fail_ends": ends, "k": k, "n": n, "errors": errors, "capped": capped, "jammed": jammed, "near_budget": near, "job": job.id, "est_cost": round(cost, 3)}) + "\n")


def save_traces(job) -> None:
    """Each episode's steps to runs/traces/<job>/<trace>.json (images dropped), so trace review
    doesn't depend on the browser."""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items()}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return f"<{len(x)} chars omitted>" if isinstance(x, str) and len(x) > 4000 else x

    out = Path(__file__).parents[1] / "runs" / "traces" / str(job.id)
    out.mkdir(parents=True, exist_ok=True)
    for r in job.runs:
        record = {"reward": r.reward, "trace": strip(r.trace.model_dump(mode="json"))}
        (out / f"{r.trace_id or id(r)}.json").write_text(json.dumps(record, indent=1))


# $/episode at 40 steps, from hud.ai trace pages (sol $0.13-0.16); exact cost is on each trace.
COST_PER_EPISODE = {"gpt-6-luna": 0.015, "gpt-6-sol": 0.145, "gpt-6-astra": 0.73, "oracle": 0.0}


def wilson(k: int, n: int, z: float = 1.645) -> tuple[float, float]:
    """90% Wilson interval for a pass rate: at n=10, 2/10 is roughly 6-48%, so read it as a range."""
    if n == 0:
        return 0.0, 1.0
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


if __name__ == "__main__":
    asyncio.run(main())
