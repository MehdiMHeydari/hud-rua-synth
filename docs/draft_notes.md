# Draft notes for the three deliverables (bullets only; Mehdi writes the prose)

Evidence: docs/findings.md (results and 5 corrections), docs/decisions.md (every choice, why, rejected),
reports/ (literature), runs/log.jsonl (every run). State: end of Nov 25.

Story in three lines:
- Built: intent -> generator (LLM writes a YAML spec) -> free gates -> calibration on the target model -> trace review and replay -> task library.
- Found: GPT-6 Astra knows the physics and fails on execution margin.
- Lesson: most low scores were our harness, not the model; replaying recorded episodes is the free check that separates them.

## 1. Capability profile of RUAs + task groups

### What Astra does well (60 steps, top + wrist cameras)
- Everything calibrated for sol: precision insert, tool use, drawers, other-person frames, ordered stacking (40-100%).
- Perception tricks: fake_cubes 5/5, match_photo 5/5, world_changes (notices a change), heavy_cube (finds it by pushing).
- Self-verification: failures are reported honestly. (Earlier "false done" headline RETRACTED: it was a frictionless drawer slide.)
- Bracing when the stop is visible: loose_lid 3/3. Counterweighting: counterweight 3/5.
- Reorienting a bar: stand_up 5/5 (real robots: 0/20, so a sim-vs-real gap, see section 3).
- Knows statics exactly: on impossible overhang seeds it answers "14/2 + 14/4 = 10.5 cm < 11.5" in 1-2 calls, 2/2.

### Where Astra fails for a real reason (clean episodes only)
| task | Astra | sol | failure |
|---|---|---|---|
| max_overhang | 5/18 = 28% | 2/10 | stack tips on release; aims past the target, no margin left |
| balance_sort | 1/12 = 8% | 0/10 | reads the balance right, loses cubes on the tilting plank |
| balance_pick | 1/5 = 20% | - | names the heaviest in 3/4 failures, drops it retrieving it (luck floor 1/3) |
| weighted_overhang | 0/12 | - | supports tip while stacking off-centre blocks |
| overhang_or_impossible | 3/5 (impossible 2/2, feasible 1/3) | - | knowledge complete; one stack 5 mm short, called "about 12 cm" |
- Supported claim: "has the physical idea, loses on execution margin" (thin stability margins, off-centre loads, unstable surfaces, reading 5 mm from 256 px).
- NOT supported (do not write): "can't reason about balance", "never braces", "can't self-verify", "hidden_weight is hard".
- Also seen: gives up on doable work when offered an exit (maybe_impossible feasible 3/5).

### sol profile (Nov 22-24, 40 steps, n>=20; still valid for sol)
- open_drawer 20%, drawer_store_close 15%, drawer_blind_store 25%, stack_ordered 16%, place_relative 28%, peg_in_hole 25%, hook_retrieve 20%. luna 0-10%.
- Difficulty is relative to the model: these are 40-100% for Astra.

### Suggested task groups (each with a knob)
- Statics / centre of mass (overhang distance, block count).
- Hidden properties found by interaction (mass ratio, lead offset).
- Instrument use on unstable surfaces (plank length, damping).
- Feasibility judgment (share of impossible seeds).
- Not worth generating for Astra: selection, frames, plain pick-and-place, visible-stop bracing.

### Sources (one per idea)
- Robocurve Six Easy Tasks (Nov 25 2026): Astra and Fable 0/36 each on real robots. RoboDojo-RC Tier 1 (Sep 23): stand up bottles 0/20, pour 0/20, stack bowls 3/20. Notes: `research_notes/Hard tasks for RUAs/community_failures.md`.
- Lab teammate: agents fail at high-frequency, non-prehensile, locomotion.
- Harmonic (book) stacking for the overhang bound; balance-scale sorting from classic physical-reasoning puzzles.
- Literature notes: `reports/`, `research_notes/` (AnyTask, GenSim for spec-not-code; RoboARCade for false claims).

## 2. Pipeline design

- Input: one-line text intent, or a tabletop photo (`rua/intent.py` maps it to our building blocks).
- Generator (`rua/generate.py`): LLM writes YAML only; fixed code builds the MuJoCo scene. Gets the exact gate failures back, up to 5 rounds. Passes wait in `tasks/generated/` for human approval.
  - Why a spec, not code: LLM task code runs but is often wrong (AnyTask, GenSim).
  - Vocabulary: primitives, hook, drawer, hole_block, platform, seesaw, lidbox, zone, scanned assets with admission checks; fields weight, loose, priority, friction; 13 predicates; variants / impossible seeds; goal images.
- Discriminator, cheapest first:
  - Free gates (`rua/gates.py`): schema, prompt lint, settle, joints, reach, visible, trivial, oracle, robust (5 mm), then the oracle through the real tool.
  - Truth test (`rua/checks.py`, 15 checks): everything the agent is told is true.
  - Asset admission: compile, size, rest, drop, cavity, grasp, release, vision.
  - Paid: calibrate on the target model; flags on every run (step cap, jammed, near budget); trace review; replay.
- Harness: HUD DirectControl `move_to` (the SDK serves one motion tool per env; `move_joints` is a launch switch we scoped, not built), top + wrist cameras, grasp line, stall line, binary gripper, final-state grading per condition.
- Generator record (`runs/generator_log.jsonl`): 8 of 12 intents accepted, 1-5 rounds. Final five: all hand-written first; the generator then rebuilt four from a one-line intent (max_overhang, balance_sort, balance_pick, overhang_or_impossible) and failed on weighted_overhang after 5 rounds.
- Diagram: `docs/pipeline_diagram.md`.

### The five tasks and their rollouts (Astra, 60 steps; traces on hud.ai by job id, local copies in runs/traces/)
| task | spec | clean result | jobs |
|---|---|---|---|
| max_overhang | tasks/max_overhang.yaml | 5/18 | 193ec7c2, 1652b36b, 423adafa |
| balance_sort | tasks/balance_sort.yaml | 1/12 | 6ca5c260, 71b00f9d, 7aea5806 |
| weighted_overhang | tasks/weighted_overhang.yaml | 0/12 | 3a19fb37, 2f29cee8, d941c18f, 522e6996 |
| balance_pick | tasks/balance_pick.yaml | 1/5 | 8b16fde4 |
| overhang_or_impossible | tasks/overhang_or_impossible.yaml | 3/5 | fec57776 |
- "Clean" = episodes with no arm jam and where the reverted IK retry never fired (docs/findings.md, CORRECTION 5).
- Every one passes all free gates and the scripted oracle 5/5 through the real move_to tool.

## 3. Performance, bottlenecks, scale

### Time and volume
- Episodes run: Astra 326, sol 285, luna 60, scripted oracle 212.
- Batch of 5 parallel episodes: 3-4 min. Free gates: ~1 min per task.

### Harness faults that looked like difficulty (the main lesson)
1. Frictionless drawer slide: "false done" on drawer tasks. Fixed, Astra blind store 3/15 -> 9/10.
2. Step-cap count inflated by counting tool results as steps.
3. Unfair prompt: loose_drawer 0/8 -> 5/10 once the prompt named the heavy block.
4. Wrist jam: yaw through about -2.0 rad runs joint 7 into its stop; arm stays stuck. hidden_weight 1/10 was mostly this (below its own 25% luck floor).
5. My own fix for 4 (IK retry) jerked the arm in normal tilted grasps: 3 of 5 recorded plate_to_edge successes failed on replay. Reverted.
- 3 of 6 "hard" results did not survive (plate_to_edge, loose_drawer, hidden_weight).

### The method that came out of it (all free)
- Replays of recorded tool calls are exactly deterministic: of 106 episodes replayed on the restored harness, all 88 recorded on it reproduce with 0 differing lines; the 18 that differ are exactly those where the bad fix had fired.
- Use 1: regression-test any harness change against recorded successes before paying for a model.
- Use 2: classify every episode clean vs contaminated; report clean numbers.
- Alarms: score below the task's luck floor; failures bunched at the step budget; 2+ moves in a row 10 cm short.
- Ladder per hard task: bare / told the trick / smaller version (hidden_weight_hint, balance_pick, overhang_or_impossible) to locate the failure.
- Independent review by a second model read the traces cold and found the jam.

### Bottlenecks
- World is frozen between moves: no dynamic or reactive tasks (teammate's top suggestion). Needs a real-time mode.
- Oracles are open-loop and privileged (know masses, lead end): they prove the physics, not that the task is solvable from observations. Only balance_sort got a closed-loop oracle (weighs 5/5).
- Gates run the oracle through `Sim.move_to`; the agent's tool path interpolates differently. Oracle-through-tool is now run, should be a gate.
- Statistics: n=5 cannot separate 10% from 40%; a band needs ~20-30 episodes per task per model.
- One embodiment (Franka), one arm, parallel gripper, rigid bodies: no threading, bags, zippers, two-handed grips (most of Robocurve's six).
- Wrist: tilted grasps stall; the yaw jam is documented and flagged, not fixed.
- Sim-vs-real: stand_up is trivial here (bar swings freely in the grip), 0/20 on real robots.
- Precision knobs are cliffs (peg 11 mm 0/10, 12 mm 7/20); thresholds within 1 cm are a lottery at 256 px.
- Pass/fail grading only; Robocurve uses milestone rubrics.
- Difficulty tuned by hand constants (150 g cabinet, friction 0.25) reads as tuned-to-fail; each needs a real-world reference.

### To scale
- Automate generate -> gate -> calibrate -> flag -> replay; recalibrate per model release.
- Make replay regression and oracle-through-tool standard gates.
- Closed-loop, observation-only oracles for hidden-state tasks.
- Second embodiment via the scene builder; gates rerun per robot.
- Milestone grading; LLM judge for trace review with spot checks.

## Open items before submitting

- balance_pick and overhang_or_impossible have n=5.
- hidden_weight true rate unknown (between 1/10 and 6/10).
- `docs/findings.md` keeps retracted claims in place with CORRECTION notes; `docs/decisions.md` is long (44 KB).
- Pending approval in `tasks/generated/`: lift_pill_bottle, drawer_tower_close (fails robust), g_* tasks.
- Questions for Lukass: 5-30% vs ~50% optimum; which model defines the band.
