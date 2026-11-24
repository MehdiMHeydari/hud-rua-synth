# Draft notes for the three deliverables (bullets only; Mehdi writes the prose)

Evidence links: docs/findings.md (results), docs/decisions.md (design log), reports/ (literature).

## 1. Capability profile of RUAs + task groups

What gpt-6-sol does well (top+wrist cams, grasp line, 40 steps):
- Reaching, top-down grasping, lifting: lift_cube 85%.
- Matching gripper yaw to an object: rotated bar 100%, even with 1 cm spare in the gripper.
- Simple pushing to a goal: 60-80% (saturates; tightening precision just hits the tool's ~1 cm limit).

Final calibrated set (sol, n>=20 each, all passing every gate): open_drawer 20%, drawer_store_close 15%,
drawer_blind_store 25% (written by the generator agent from a one-line intent), stack_ordered 16%,
place_relative 28%, peg_in_hole 25%, hook_retrieve 20%. Luna 0-10% on all (same ranking).
Failure evidence from trace reviews: false "done" claims dominate peg (6/8 failures) and place_relative
(6/7); place_relative errors are frame flips ("their left is toward the robot"), never camera-left/right.

Where it fails (in the 5-30% band) and why:
- Multi-step chains: drawer_store_close 20%. Undoes its own progress (pushes drawer shut early), misreads state (closed cabinet top read as open drawer before the prompt said "starts closed").
- Articulated objects: open_drawer 20%. Grasps above the tab or with a tilted wrist; shoves the drawer back while regrasping.
- Stacking: stack_ordered 27%. Releases blocks ~1 cm too low so they slide off; the top camera can't show height.
- Other-person reference frames: place_relative 27% (person at the robot's side = 90 deg rotation; 5 distractors).
- Tool use: hook_retrieve 33%. Hook slips off the cube; abandons the hook to grab the out-of-reach cube.
- Self-verification: false "done" claims (2/4 peg failures; drawer run ignored "stopped 3 cm short"). Literature: sol false-claims in 63% of unsolved non-timeout episodes (RoboARCade).
- Cheap vs mid model: luna 25% vs sol 85% on lift_cube, so cheap models are screeners, not calibrators.
- Selection vs action contrast: picking "the red cube closest to the blue cylinder" among 4 identical
  cubes at a 2 cm margin = 100% (25/25), but placing relative to another person's left = 28%. The gap is
  acting in a non-camera frame and verifying the result, not seeing.

Non-obvious lesson: most early "failures" were the harness, not the model.
- All 8 luna failures traced to harness faults (offset wrist cam, continuous gripper "echo", roll=0 trap, mislabelled grasp line).
- Physics confounds found by gates before any model run: weak Menagerie grip (~2.5 N), objects pivoting/sliding in the grip, IK posture swinging the wrist mid-lift, drawer jamming on its own cabinet.
- Precision cliffs: peg at 7 mm clearance and push at 1 cm were unsolvable at the tool's accuracy; sol's 0-1/10 measured the harness.

Suggested task groups (each has a smooth knob): multi-step chains (steps), articulated objects (damping, handle size), stacking (block count), reference frames (frame type, distractors), tool use (distance, tool shape), self-verification (success not visible from top camera).

## 2. Pipeline design

- Generator: a coding agent (Claude Code) writes a YAML task spec from an intent; fixed code builds the MuJoCo scene. Spec = objects (closed set: primitives + templates), placement ranges (randomised per seed), success predicates, oracle plan, knobs.
  - Why spec not code: LLM task code runs but is often wrong; placement bugs dominate (AnyTask, GenSim).
  - Assets: closed, pre-checked set (primitives; drawer/hole-block/zone/hook templates; later a curated scanned-object catalog with cards). No deformables.
- Discriminator: gates cheapest-first; any failure goes back to the generator with a reason.
  - Free: schema (+ prompt lint), settle, joints, reach, trivial (reset/do-nothing/random), oracle in sim, robust (5 mm noise), oracle through the real tool, truth test (15 checks on everything the agent is told).
  - Paid: strong model on easy setting (harness fair?), calibrate knob on sol into 5-30%, trace review (harness vs model), each new harness fault becomes a new free check.
- Harness (what the agent sees/does): DirectControl move_to, top-down + wrist (lab-style tilted) cameras, grasp line, stall line, binary gripper, state rounded to 1 mm, final-state grading with per-condition report.
- Diagram idea: intent -> generator -> spec -> [free gates] -> [paid gates] -> task library; failure arrows back with reasons.

## 3. Performance, bottlenecks, scale

- Cost: sol $0.13-0.16/episode (40 steps, from trace pages), luna ~$0.015; ~$50 total model spend for 7 calibrated tasks; free gates cost nothing and caught most problems.
- Calibration statistics are the real bottleneck: n=10 gives a ~40-point-wide interval (2/10 -> 7-46%), and real batches swung 2/10 -> 6/10 on fresh seeds; 5-30% needs ~20-30 episodes per task (~$3).
- Precision knobs are cliffs: peg clearance 11 mm 0/10, 11.5 mm 5/20, 12 mm 7/20, 15 mm 8/10. Smooth knobs (steps, distance, frames) were easier to land.
- Precision knobs cliff instead of scaling (success flat, then 0% once below tool + agent error); prefer smooth knobs (steps, distractors, frames).
- Harness faults masquerade as difficulty; the truth test + robust gate + trace review are what make a difficulty number trustworthy.
- Wall time: ~3-4 min per batch of 5 parallel episodes; sim is ms-scale, model latency dominates.
- To scale: automate the generate -> gate -> calibrate loop; LLM-judge trace review with spot checks; recalibrate when models change; human glance at one render per new template/asset.
- Open questions for Lukass: why 5-30% vs the ~50% learnability optimum; which model defines the band (we used sol).
