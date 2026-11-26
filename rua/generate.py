"""One-command task generator: intent (or photo) -> spec -> checks -> feedback -> human review.

    python rua/generate.py "test whether the agent can ..." [--image photo.jpg] [--model M] [--rounds 4] [--name NAME]
    python rua/generate.py "..." --base max_overhang  # start from an accepted task
    python rua/generate.py --approve NAME          # tasks/generated/NAME.yaml -> tasks/NAME.yaml
    python rua/generate.py --reject NAME --reason "..."
    python rua/generate.py --stats

The model only writes YAML. This script runs every check (schema, the free gates on 5 seeds, the
oracle through the real tool) and sends the exact failures back, up to --rounds model calls. A task
that passes waits in tasks/generated/ with a review sheet until a human approves or rejects it.
Every run is logged to runs/generator_log.jsonl.
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from collections import Counter
from pathlib import Path

import yaml
from dotenv import load_dotenv
from PIL import Image, ImageDraw
from pydantic import ValidationError

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "rua"))
load_dotenv(ROOT / ".env")

from hud.utils.gateway import build_gateway_client  # noqa: E402 (needs the key loaded)

import gates  # noqa: E402
import intent  # noqa: E402
import objects  # noqa: E402
import spec  # noqa: E402
from sim import Sim  # noqa: E402

GEN = spec.TASKS_DIR / "generated"
LOG = ROOT / "runs" / "generator_log.jsonl"
EXAMPLES = ("drawer_store_close", "place_relative", "bottle_in_bowl")  # articulated, frames, assets
PRICES = {"claude-opus-5-5": (4, 20)}  # $ per M tokens (in, out); other models log tokens only


def system_prompt() -> str:
    """Everything the model may use: the rules, the schema source, the blocks, admitted assets, examples."""
    cards = [{k: c[k] for k in ("id", "desc", "size", "graspable", "hollow")} for c in objects.CATALOG.values() if c["admitted"]]
    blocks = (f"free primitives {objects.PRIMITIVES}; compound {objects.COMPOUND} (part: handle); articulated "
              f"{objects.ARTICULATED} (part: handle); fixed {objects.FIXED}; asset (an admitted catalog id below)")
    examples = "\n".join((spec.TASKS_DIR / f"{n}.yaml").read_text() for n in EXAMPLES)
    return (f"{(ROOT / 'docs' / 'generator_prompt.md').read_text()}\n\n## Schema: rua/spec.py (the source of truth)\n"
            f"```python\n{(ROOT / 'rua' / 'spec.py').read_text()}```\n\n## Building blocks\n{blocks}\n\n"
            f"## Admitted catalog assets (size in m)\n{yaml.safe_dump(cards, sort_keys=False, width=200)}\n"
            f"## Example specs (each passes every gate)\n```yaml\n{examples}```\n\n"
            "Reply with exactly one complete YAML spec in a ```yaml block and nothing else. "
            "A script runs every gate on it and sends any failure back to you.")


async def _ask(model: str, system: str, history: list) -> tuple[str, dict]:
    if model.startswith("claude"):
        r = await build_gateway_client("anthropic").messages.create(
            model=model, max_tokens=16000, system=system, messages=history, output_config={"effort": "high"})
        history.append({"role": "assistant", "content": r.content})  # thinking blocks kept, unedited
        return "".join(b.text for b in r.content if b.type == "text"), {"in": r.usage.input_tokens, "out": r.usage.output_tokens}
    r = await build_gateway_client("openai").responses.create(model=model, instructions=system, input=history)
    history.append({"role": "assistant", "content": r.output_text})
    return r.output_text, {"in": r.usage.input_tokens, "out": r.usage.output_tokens}


def check(name: str) -> list[tuple[str, str]]:
    """(gate, reason) failures: schema, then the free gates (5 seeds), then the oracle through run.py."""
    task = f"generated/{name}"
    try:
        spec.load(task)
    except ValidationError as e:
        return [("schema", "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))]
    except Exception as e:  # YAML syntax, missing keys
        return [("schema", f"{type(e).__name__}: {e}")]
    try:
        fails = gates.run_gates(task, 5)
    except Exception as e:  # e.g. the scene doesn't compile
        return [("build", f"{type(e).__name__}: {e}")]
    if fails:  # one line per distinct reason, with the seeds it hit
        seeds: dict[tuple[str, str], list[int]] = {}
        for gate, seed, reason in fails:
            seeds.setdefault((gate, reason), []).append(seed)
        return [(g, r + (f" (seeds {s})" if s != [-1] else "")) for (g, r), s in seeds.items()]
    env = {**os.environ, "TASK": task, "HUD_LLM_MODEL": "oracle", "EPISODES": "3", "CONCURRENCY": "3"}
    out = subprocess.run([sys.executable, str(ROOT / "rua" / "run.py")], env=env, capture_output=True, text=True)
    m = re.search(r": (\d+)/(\d+) = .*", out.stdout)
    if not m or m[1] != m[2] or "INVALID" in m[0]:
        return [("oracle_tool", f"scripted oracle through the move_to tool: {m[0] if m else 'run.py crashed: ' + out.stderr[-400:]}"
                 " (the in-sim oracle passed, so suspect a tool limit: yaw range, ~1 cm stop accuracy)")]
    return []


def review_sheet(name: str) -> Path:
    """Start state and state after the oracle plan (seed 0), top + shoulder views, prompt as caption."""
    task, w = spec.load(f"generated/{name}"), 320
    sim = Sim(task, image_size=w)
    tiles = [sim._render(c) for c in ("top", "shoulder")]
    for pos, yaw, gripper in task.plan(0):
        sim.move_to(pos, yaw=yaw, gripper=gripper)
    tiles += [sim._render(c) for c in ("top", "shoulder")]
    sheet = Image.new("RGB", (2 * w, 2 * w + 110), "white")
    for i, t in enumerate(tiles):
        sheet.paste(Image.fromarray(t), ((i % 2) * w, (i // 2) * w))
    caption = (f"{name}: top row start, bottom row after the oracle (seed 0, success={sim.success()}); "
               f"left top camera, right shoulder\n\n" + "\n".join(textwrap.wrap(task.prompt, 100)))
    ImageDraw.Draw(sheet).text((8, 2 * w + 8), caption, fill="black")
    out = ROOT / "runs" / "review" / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def log(**record) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M"), **record}) + "\n")


def generate(text: str, model: str, rounds: int, name: str | None) -> None:
    t0, system, tokens, per_round, status = time.time(), system_prompt(), {"in": 0, "out": 0}, [], "failed"
    history = [{"role": "user", "content": f"Intent: {text}" + (f"\nUse name: {name}" if name else "")}]
    GEN.mkdir(exist_ok=True)
    for r in range(1, rounds + 1):
        reply, usage = asyncio.run(_ask(model, system, history))
        tokens = {k: tokens[k] + usage[k] for k in tokens}
        body = (m[1] if (m := re.search(r"```(?:yaml)?\n(.*?)```", reply, re.S)) else reply).strip() + "\n"
        try:
            data = yaml.safe_load(body)
            name = name or re.sub(r"\W+", "_", str(data["name"])).lower()
            body = re.sub(r"^name:.*$", f"name: {name}", body, count=1, flags=re.M)
            (GEN / f"{name}.yaml").write_text(body)
            failures = check(name)
        except Exception as e:  # unparseable reply
            failures = [("schema", f"reply is not a YAML spec with a name: {type(e).__name__}: {e}")]
        per_round.append([[g, reason.splitlines()[0][:200]] for g, reason in failures])
        print(f"round {r}: " + ("all checks pass" if not failures else "; ".join(f"{g}: {x[:120]}" for g, x in failures)), flush=True)
        if not failures:
            status = "accepted"
            break
        history.append({"role": "user", "content": "These checks failed:\n" + "\n".join(f"- {g}: {x}" for g, x in failures)
                        + "\nFix the cause (never loosen success to pass; keep the intent's objects and skill, don't swap them "
                        "for easier ones) and reply with the full corrected YAML spec."})
    price = PRICES.get(model)
    cost = round((tokens["in"] * price[0] + tokens["out"] * price[1]) / 1e6, 3) if price else None
    log(event="generate", intent=text, model=model, name=name, rounds=len(per_round), failures=per_round,
        status=status, tokens=tokens, cost=cost, wall_s=round(time.time() - t0))
    print(f"{name}: {status} after {len(per_round)} round(s); tokens {tokens}; cost ${cost}; {time.time() - t0:.0f} s")
    if status == "accepted":
        print(f"review sheet: {review_sheet(name)}\n"
              f"then: python rua/generate.py --approve {name}   or   --reject {name} --reason '...'")


def review(name: str, approve: bool, reason: str | None) -> None:
    """A human's call on a pending task. Only gate-accepted tasks can be approved."""
    src, dst = GEN / f"{name}.yaml", spec.TASKS_DIR / f"{name}.yaml"
    last = [r for r in records() if r.get("name") == name and r["event"] == "generate"][-1:]
    if not src.exists() or (approve and (not last or last[0]["status"] != "accepted")):
        sys.exit(f"{name}: no gate-accepted pending task in {GEN}")
    if approve:
        if dst.exists():
            sys.exit(f"{dst} already exists; reject or rename")
        src.rename(dst)
    else:
        src.unlink()
    log(event="review", name=name, status="approved" if approve else "rejected", reason=reason)
    print(f"{name}: {'approved -> ' + str(dst) if approve else 'rejected'}")


def records() -> list[dict]:
    return [json.loads(line) for line in LOG.read_text().splitlines()] if LOG.exists() else []


def stats() -> None:
    gens = [r for r in records() if r["event"] == "generate"]
    reviews = Counter(r["status"] for r in records() if r["event"] == "review")
    if not gens:
        sys.exit("no generator runs logged yet")
    ok = [g for g in gens if g["status"] == "accepted"]
    costs = [g["cost"] for g in gens if g.get("cost") is not None]
    print(f"runs {len(gens)} | gate-accepted {len(ok)}/{len(gens)} ({len(ok) / len(gens):.0%}) | mean rounds "
          f"{sum(g['rounds'] for g in gens) / len(gens):.1f} (accepted: {sum(g['rounds'] for g in ok) / max(len(ok), 1):.1f}) | "
          f"human: {reviews['approved']} approved, {reviews['rejected']} rejected | mean cost "
          f"${sum(costs) / max(len(costs), 1):.2f}, mean wall {sum(g['wall_s'] for g in gens) / len(gens):.0f} s")
    caught = Counter(gate for g in gens for gate in {f[0] for rnd in g["failures"] for f in rnd})
    print("\ngate          runs it caught something in")
    for gate, n in caught.most_common():
        print(f"{gate:<13} {n}/{len(gens)}")
    short = lambda f: re.sub(r"\d+(\.\d+)?", "#", f"{f[0]}: {re.split(r' \(seeds|; final state', f[1])[0]}")[:110]
    reasons = Counter(short(f) for g in gens for rnd in g["failures"] for f in rnd)
    print("\ntop failure reasons (numbers as #)")
    for reason, n in reasons.most_common(5):
        print(f"{n:>3}  {reason}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("intent", nargs="?")
    ap.add_argument("--image", help="tabletop photo; rua/intent.py turns it into the intent first")
    ap.add_argument("--model", default="claude-opus-5-5")  # strongest coding model on the gateway
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--name")
    ap.add_argument("--base", help="an accepted task to start from (bottom-up composition, as in GenSim2)")
    ap.add_argument("--approve")
    ap.add_argument("--reject")
    ap.add_argument("--reason")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.stats:
        stats()
    elif a.approve or a.reject:
        review(a.approve or a.reject, bool(a.approve), a.reason)
    else:
        text = a.intent or ""
        if a.image:  # photo -> mapped objects + candidate intents; the first intent unless one was given
            draft = yaml.safe_load(asyncio.run(intent.intent(a.image, "gpt-6-astra"))[0].strip()
                                   .removeprefix("```yaml").removesuffix("```")) or {}
            text = (text or draft["tasks"][0]["intent"]) + f"\nScene from a photo (draft mapping, re-check it): {draft.get('objects')}"
        if not text:
            ap.error("give an intent or --image")
        if a.base:  # start from a spec that already passes every gate; the model edits it instead of starting blank
            text += (f"\nStart from this accepted task, which passes every gate, and change only what the intent needs. "
                     f"Keep its working parts (layout, grasp heights, oracle structure) unless they conflict:\n"
                     f"```yaml\n{(spec.TASKS_DIR / f'{a.base}.yaml').read_text()}```")
        generate(text, a.model, a.rounds, a.name)
