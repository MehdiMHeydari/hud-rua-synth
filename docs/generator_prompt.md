# Generator prompt (what the task-writing agent is told)

You turn an intent (e.g. "test whether agents can chain open-place-close") into one task spec,
`tasks/<name>.yaml`, that passes every gate. You never write physics or scene code inside a spec.

Photo input: `python rua/intent.py photo.jpg` turns a real tabletop photo into objects mapped to the
blocks below plus 1-2 candidate intents. Treat it as a draft: re-check every `maps_to` against
rua/spec.py (it can miss objects or mislabel them), drop "no match" objects, then proceed as for text.

## Building blocks (the only vocabulary; rua/spec.py is the source of truth)
- Shapes: box, cylinder, sphere (free); hook (free, compound, part `handle`); drawer (articulated,
  part `handle`, fields `travel`, `damping`, `start`); hole_block (fixed, field `hole`); platform (fixed solid box, e.g. a ledge); seesaw (fixed fulcrum, plank `size` [length, width, thickness] on a
  hinge `pivot` m up, `damping`; starts level, the table stops its ends); zone (fixed, visual only; size `[d]` circle or `[x, y]` rectangle).
  Primitives take `friction` (default 1; it also sets grip, MuJoCo uses the larger of the two).
  Hidden-property fields (for tasks where the agent must find something out by interacting): box `weight`
  (kg of invisible lead at its +x end; a random `yaw` hides which end), primitive `priority: 1` (its `friction`
  wins over the table's, so < 1 makes it slippery), drawer `loose: true` (light free cabinet that slides when
  the handle is pulled unless braced or weighted down), platform `friction`. lidbox (free, light box with a
  sliding lid, part `handle`, field `stiction`; graded with `opened`).
- Scanned assets: `{shape: asset, asset: <id>}` with an `admitted: true` id from `assets/catalog.yaml`; size and
  mass come from the card (never set `size`; no `color`, they are textured). Body origin = bbox centre, so
  predicates treat it like a box of the card size. Use `graspable`/`hollow` from the card: only graspable
  ones can be picked, only hollow ones can be an `inside` container (centre within the rim, bottom below it).
- Success predicates (all must hold, graded on the final state): lifted, opened, closed, inserted,
  in_zone, inside, stacked, near_offset, unmoved, clear (no listed object's centre over a zone, all at rest on the table), tipped (tilted >= `angle` deg),
  at_goal (each centre within `radius` of its goal pose, resting; the agent sees the goals only as a goal image).
  overhang (a box's farthest corner >= `beyond` m past a platform's +x face, released, above its top).
- `z` on an object: height of the surface it starts on (e.g. on a platform); offsets are from its centre.
- Placement: `x`, `y`, `yaw` ranges, sampled per seed. Keep everything reachable (x 0.3-0.8 at table height)
  and >= 5 cm inside the top camera's view (roughly x 0.0-1.0, y +-0.6; the `visible` gate checks).
  `layout_yaw: [lo, hi]` rotates the whole layout per seed so relations aren't always on the same side.
  `goal_x`/`goal_y` ranges on an object give it a per-seed goal pose (unset = where it starts); the goal image
  (top view of the goal arrangement) is returned with every move. Oracle steps reach it with `goal: true`.
  `shuffle: [[a, b, c]]` swaps the xy and yaw of same-footprint objects per seed (a red `zone` decal can stand in for a cube), so a hidden property (mass,
  a locked drawer) moves around; success and oracle name the object, so they follow it.
- `variants: [ok, blocked, ...]` (seed s plays variants[s % len]) + `impossible: [blocked]` + `only: [...]` on objects:
  an impossible variant is graded on the reply containing IMPOSSIBLE (the prompt must ask for it); a feasible one fails if it does.
- `perturb: {object, offset: [dx, dy]}`: the first time the task is solved, the object is moved by the
  offset once, unannounced. The oracle must place it again (it lands at its first drop + offset).
- Ranges are independent per object, so relative distances jitter by the sum of the ranges: if the task
  depends on a relation (closest, left of), sample 200 seeds with `spec.load(...).sample(seed)` and check
  the margin holds on all of them. Gates run 5 seeds by default (`SEEDS=12` for more).
- Oracle: steps `{at: object[.part], offset: [dx,dy,dz] in the object's frame, yaw: deg, gripper: open|closed}`.
  Tool yaw 0 closes the fingers along world y. `tool: [roll, pitch, yaw]` (deg, world) replaces
  straight-down for side pinches; [-135, 0, -90] = fingers forward and 45 deg down, closing across a thin edge. Part offsets (e.g. a drawer `handle`) are for the
  closed position; add `start * travel` yourself for a drawer that starts open.
- Gripping a part can move it (closing on a drawer tab nudges the drawer ~2 cm); push with closed
  fingers when you only need to push.
- A `success` kind takes one predicate or a list (all must hold), e.g. two blocks `inside` the drawer.
  Anything else not expressible: ask for a new building block instead of faking it.

## Rules
- The prompt states every starting state ("The drawer starts closed") and nothing the grader checks
  that the agent can't know. Use world terms only where the task isn't about frames.
- Every numeric threshold the grader uses (lifted height, near_offset offset and radius, opened/closed
  fraction, inserted depth, in_zone radius) appears in the prompt in cm/mm/%, or as a phrase that means it
  ("fully open" >= 90%, "fully closed" <= 5%, "all the way in" for depth, "entirely inside the circle" when
  the circle's radius = success radius + object radius). Hiding one on purpose needs a `hidden:` entry with
  the reason. The `prompt` gate checks this.
- Difficulty comes from smooth knobs (more steps, distractors, other reference frames, tool use),
  not from tolerances near the tool's ~1 cm accuracy. Record knobs in `knobs:`.
- If the oracle fails, fix geometry or the plan, never loosen success to pass.

## Loop
One command runs it: `python rua/generate.py "intent"` (or `--image photo.jpg`). The model writes the YAML;
the script runs schema, the free gates (prompt, settle, joints, reach, visible, trivial, oracle, robust; 5 seeds)
and the oracle through the real tool (3 episodes), and sends any failure back, up to 4 rounds. A passing task waits
in tasks/generated/ with a review sheet (runs/review/<name>.png) until a human runs `--approve` or `--reject`.

After approval (by hand, costs money):
1. `TASK=<name> HUD_LLM_MODEL=gpt-6-sol EPISODES=5 python rua/run.py`: 3/5 or more = too easy, raise a knob;
   0/5 = check traces for harness faults before calling it hard. Confirm with 20 episodes on fresh seeds (SEED0).
2. Read failed traces; any harness fault becomes a fix plus a new check in rua/checks.py or rua/gates.py.
