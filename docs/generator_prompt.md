# Generator prompt (what the task-writing agent is told)

You turn an intent (e.g. "test whether agents can chain open-place-close") into one task spec,
`tasks/<name>.yaml`, that passes every gate. You never write physics or scene code inside a spec.

Photo input: `python rua/intent.py photo.jpg` turns a real tabletop photo into objects mapped to the
blocks below plus 1-2 candidate intents. Treat it as a draft: re-check every `maps_to` against
rua/spec.py (it can miss objects or mislabel them), drop "no match" objects, then proceed as for text.

## Building blocks (the only vocabulary; rua/spec.py is the source of truth)
- Shapes: box, cylinder, sphere (free); hook (free, compound, part `handle`); drawer (articulated,
  part `handle`, fields `travel`, `damping`, `start`); hole_block (fixed, field `hole`); zone (fixed, visual only).
- Scanned assets: `{shape: asset, asset: <id>}` with an `admitted: true` id from `assets/catalog.yaml`; size and
  mass come from the card (never set `size`; no `color`, they are textured). Body origin = bbox centre, so
  predicates treat it like a box of the card size. Use `graspable`/`hollow` from the card: only graspable
  ones can be picked, only hollow ones can be an `inside` container (centre within the rim, bottom below it).
- Success predicates (all must hold, graded on the final state): lifted, opened, closed, inserted,
  in_zone, inside, stacked, near_offset, unmoved.
- Placement: `x`, `y`, `yaw` ranges, sampled per seed. Keep everything reachable (x 0.3-0.8 at table height)
  and >= 5 cm inside the top camera's view (roughly x 0.0-1.0, y +-0.6; the `visible` gate checks).
  `layout_yaw: [lo, hi]` rotates the whole layout per seed so relations aren't always on the same side.
- Ranges are independent per object, so relative distances jitter by the sum of the ranges: if the task
  depends on a relation (closest, left of), sample 200 seeds with `spec.load(...).sample(seed)` and check
  the margin holds on all of them. Gates run 5 seeds by default (`SEEDS=12` for more).
- Oracle: steps `{at: object[.part], offset: [dx,dy,dz] in the object's frame, yaw: deg, gripper: open|closed}`.
  Tool yaw 0 closes the fingers along world y. Part offsets (e.g. a drawer `handle`) are for the
  closed position; add `start * travel` yourself for a drawer that starts open.
- Gripping a part can move it (closing on a drawer tab nudges the drawer ~2 cm); push with closed
  fingers when you only need to push.
- A `success` kind takes one predicate or a list (all must hold), e.g. two blocks `inside` the drawer.
  Anything else not expressible: ask for a new building block instead of faking it.

## Rules
- The prompt states every starting state ("The drawer starts closed") and nothing the grader checks
  that the agent can't know. Use world terms only where the task isn't about frames.
- Difficulty comes from smooth knobs (more steps, distractors, other reference frames, tool use),
  not from tolerances near the tool's ~1 cm accuracy. Record knobs in `knobs:`.
- If the oracle fails, fix geometry or the plan, never loosen success to pass.

## Loop
1. `python rua/gates.py <name>`: schema, settle, joints, reach, trivial, oracle, robust (free). Fix and repeat.
2. `TASK=<name> HUD_LLM_MODEL=oracle EPISODES=5 python rua/run.py`: oracle through the real tool must be 5/5.
3. `TASK=<name> HUD_LLM_MODEL=gpt-6-sol EPISODES=5 python rua/run.py`: 3/5 or more = too easy, raise a knob;
   0/5 = check traces for harness faults before calling it hard. Confirm with 20 episodes on fresh seeds (SEED0).
4. Read failed traces; any harness fault becomes a fix plus a new check in rua/checks.py or rua/gates.py.
