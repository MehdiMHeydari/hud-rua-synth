"""Image-to-intent: a photo of a real tabletop becomes a short intent for the task generator.

    python rua/intent.py photo.jpg [--model gpt-6-astra]   # ~$0.15-0.25 per image on Astra

One vision call through the HUD gateway. The model may only map objects to our building blocks
(and catalog assets); anything else is "no match". It also gets our capability profile and the
existing task list, so it proposes tasks aimed at known weaknesses instead of easy duplicates.
"""

import argparse
import asyncio
import base64
import io
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "rua"))
load_dotenv(ROOT / ".env")

from hud.utils.gateway import build_gateway_client  # noqa: E402 (needs the key loaded)

import objects  # noqa: E402

SHAPES = objects.PRIMITIVES + objects.COMPOUND + objects.ARTICULATED + objects.FIXED


def vocabulary() -> str:
    cards = getattr(objects, "CATALOG", {}).values()  # scanned assets; only admitted ones pass the schema
    assets = [f"- {c['id']}: {c['desc']}, {[round(v * 100) for v in c['size']]} cm"
              f"{'' if c.get('admitted') else ' (not admitted yet)'}" for c in cards]
    return f"Building blocks: {', '.join(SHAPES)}.\nCatalog assets:\n" + ("\n".join(assets) or "none")


def context() -> str:
    """What we know: the capability profile (docs/draft_notes.md section 1) and existing tasks."""
    notes = (ROOT / "docs" / "draft_notes.md").read_text()
    profile = notes.split("## 1.")[1].split("## 2.")[0].strip()
    tasks = [yaml.safe_load(f.read_text()) for f in sorted((ROOT / "tasks").glob("*.yaml"))]
    existing = "\n".join(f"- {t['name']}: {t['prompt']}" for t in tasks)
    return f"What frontier robot agents can and can't do (our findings):\n{profile}\n\nTasks we already have:\n{existing}"


PROMPT = """{context}

You see a tabletop scene. A robot arm stands at the near edge (front), facing away.
Our simulator can only build these, nothing else:
{vocab}
(box/cylinder/sphere are free primitives with a size and one plain colour; hook is an L-shaped tool;
drawer is a cabinet with one sliding drawer; hole_block is a fixed block with a square hole; zone is a
flat target marker.)
Reply with YAML only, keys:
objects: list of {{name, approx_size_cm, position (left/centre/right + front/middle/back), maps_to}}
  where maps_to is one building block or catalog asset with a short reason, or "no match". Never invent assets.
tasks: 2-3 items of {{intent: "test whether the agent can ...", hard_because: ..., targets_weakness: ...,
  knob: ...}}, grounded in this scene, buildable from the mapped objects only, aimed at weaknesses that
  survive model scale (chaining, self-verification when success is hidden, irreversible steps), and not
  a duplicate of an existing task. Avoid difficulty that comes from tolerances near 1 cm."""


def encode(path: str, max_px: int = 512) -> str:
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


async def intent(path: str, model: str) -> tuple[str, object]:
    client = build_gateway_client("openai")
    r = await client.responses.create(model=model, input=[{"role": "user", "content": [  # luna: responses route only
        {"type": "input_text", "text": PROMPT.format(context=context(), vocab=vocabulary())},
        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encode(path)}"}]}])
    return r.output_text, r.usage


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--model", default="gpt-6-astra")  # proposals need the strongest reasoner; luna proposed easy tasks
    a = ap.parse_args()
    text, usage = asyncio.run(intent(a.image, a.model))
    text = text.strip().removeprefix("```yaml").removesuffix("```").strip()
    print(text)
    known = set(SHAPES) | set(getattr(objects, "CATALOG", {})) | {"no"}
    for o in (yaml.safe_load(text) or {}).get("objects", []):  # the prompt can't enforce "never invent"
        if (m := str(o.get("maps_to", "")).split()[0].strip('"')) not in known:
            print(f"# WARNING: {o.get('name')} maps to unknown '{m}'", file=sys.stderr)
    if usage:
        print(f"# tokens: in {usage.input_tokens}, out {usage.output_tokens}", file=sys.stderr)
