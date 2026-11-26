# Synthetic task pipeline for robot-use agents

HUD work trial, Mehdi Heydari, November 2026.

A pipeline that turns a one-line intent into a checked MuJoCo task for an LLM driving a robot arm through `move_to`. It comes with a profile of where frontier agents fail, and five tasks with rollouts.

## Read these

1. [What robot-use agents can and can't do](docs/1_capability_profile.md)
2. [Pipeline design](docs/2_pipeline.md), including the five tasks and links to their rollouts
3. [Performance, bottlenecks, and what scale needs](docs/3_performance_and_scale.md)

## Run it

```bash
./setup.sh                      # Apple-silicon Mac, Python 3.11 or 3.12; installs MuJoCo and the HUD SDK
# put HUD_API_KEY in .env

python rua/checks.py            # truth test: is everything we tell the agent true?
python rua/gates.py max_overhang                      # free checks on one task
HUD_LLM_MODEL=oracle TASK=max_overhang python rua/run.py   # scripted solution, no model cost
TASK=max_overhang HUD_LLM_MODEL=gpt-6-astra STEPS=60 EPISODES=5 python rua/run.py

python rua/generate.py "test whether the agent can ..."    # generate a new task
python rua/generate.py --approve NAME                      # accept it into tasks/
```

## What is where

| Path | What it is |
|---|---|
| `tasks/` | Task specs, one YAML each. `tasks/generated/` holds generator output waiting for approval |
| `rua/generate.py`, `rua/intent.py` | Generator: text or photo in, spec out |
| `rua/gates.py`, `rua/checks.py` | Discriminator: free checks and the truth test |
| `rua/spec.py`, `rua/objects.py`, `rua/sim.py` | Spec schema, building blocks, scene builder |
| `rua/env.py`, `rua/tabletop.py`, `rua/run.py` | The HUD environment and the runner |
| `assets/` | Scanned objects and their admission cards |
| `docs/generator_prompt.md` | What the generator model is told |

## Working notes

These are the lab notebook, kept for the record. They are long and not polished.

- `docs/findings.md`: every result in the order it happened, including five corrections where an earlier claim turned out wrong.
- `docs/decisions.md`: every design decision with its reason and what was rejected.
- `reports/`: literature reviews behind the design.
