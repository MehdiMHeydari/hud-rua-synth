# Synthetic task pipeline for robot-use agents

Mehdi Heydari, HUD work trial, November 2026.

You give this pipeline one sentence, like "test whether the agent can stack blocks out past a ledge". It writes a MuJoCo task for an LLM that drives a Franka arm with `move_to`, and then checks the task before any model is paid to try it.

I used it to find out where GPT-6 Astra fails, and ended up with five tasks it finds hard for real reasons.

## Start here

There are three short docs. They are the deliverables.

1. [What robot-use agents can and can't do](docs/1_capability_profile.md)
2. [How the pipeline works](docs/2_pipeline.md). The five tasks and their rollouts are linked from here.
3. [Cost, what went wrong, and what it would take to scale](docs/3_performance_and_scale.md)

## Running it

Setup needs an Apple-silicon Mac with Python 3.11 or 3.12.

```bash
./setup.sh
# then put your HUD_API_KEY in .env
```

Everything below except the Astra line is free.

```bash
# Is everything we tell the agent true?
python rua/checks.py

# Run the free checks on one task
python rua/gates.py max_overhang

# Watch the scripted solution do the task
HUD_LLM_MODEL=oracle TASK=max_overhang python rua/run.py

# Run Astra on it, 5 episodes
TASK=max_overhang HUD_LLM_MODEL=gpt-6-astra STEPS=60 EPISODES=5 python rua/run.py

# Make a new task from one sentence, then accept it
python rua/generate.py "test whether the agent can ..."
python rua/generate.py --approve NAME
```

## Where things are

- `tasks/` has one YAML file per task. `tasks/generated/` holds what the generator wrote and I haven't approved yet.
- `rua/generate.py` and `rua/intent.py` are the generator. Text or a photo goes in, a task spec comes out.
- `rua/gates.py` and `rua/checks.py` are the checks.
- `rua/spec.py`, `rua/objects.py` and `rua/sim.py` define what a task can contain and build the scene.
- `rua/env.py`, `rua/tabletop.py` and `rua/run.py` are the HUD environment and the runner.
- `assets/` has the scanned household objects.

## My working notes

These two files are my lab notebook. They are long and unpolished, and I left them in on purpose.

- `docs/findings.md` has every result in the order it happened. Five times an earlier claim turned out to be wrong, and the corrections are marked.
- `docs/decisions.md` has every design decision, why I made it, and what I turned down.

The literature reviews behind the design are in `reports/`.
