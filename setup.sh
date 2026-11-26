#!/usr/bin/env bash
# One-time setup. Run from inside the hud-rua-synth folder.
set -e

git init -q 2>/dev/null || true
PY="${PY:-$HOME/miniforge3/envs/hud312/bin/python}"
"$PY" -c 'import sys,platform; assert (3,11)<=sys.version_info[:2]<(3,13) and platform.machine()=="arm64", f"need native arm64 Python 3.11 or 3.12, got {sys.version.split()[0]} {platform.machine()}"'
"$PY" -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q mujoco numpy pillow python-dotenv mink robot_descriptions
pip install -q "hud[robot] @ git+https://github.com/hud-evals/hud-python.git@a44cf9c85e3912cecd86dffa1ce5005160450943"

# reference repo (read-only, outside this project)
if [ ! -d ../rua-envs ]; then
  git clone -q https://github.com/hud-evals/rua-envs.git ../rua-envs || echo "rua-envs clone failed: check GitHub auth"
fi

[ -f .env ] || cp .env.example .env
echo "Done. Put your HUD_API_KEY in .env, then run: source .venv/bin/activate"
