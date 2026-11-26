# 3. Performance, bottlenecks, and what scale needs

## Cost per rollout

Keeping rollouts cheap shaped most of the design. The brief warns that a careless Astra rollout runs 150+ steps and about $60. Ours cost under a dollar.

| | Cost | Settings |
|---|---|---|
| Astra episode | about $0.73 | 60 steps, two 256 px cameras, medium effort |
| sol episode | about $0.13 | 40 steps |
| luna episode | about $0.015 | 40 steps |
| Generating one task | $0.15 to $1.15 | 1 to 5 rounds |
| Every check, the scripted solution, every replay | $0 | Runs locally on a laptop CPU |

These are estimates from our run log. Exact figures are on HUD's Usage page.

How the cost stayed down:

- **Cheap models first.** luna and sol found the harness bugs. All eight of luna's first failures turned out to be our fault, and finding that cost cents.
- **Free checks before any paid run.** A task has to pass about ten checks and a scripted solution before a model sees it.
- **Small screens.** Three to five Astra episodes show whether a task is worth more. Only tasks that survive get a larger run.
- **Short episodes.** A 60-step cap, two small images per step, five episodes in parallel.
- **Replays in place of reruns.** Checking whether a failure was ours meant replaying the recorded moves locally, which is free.

What a bigger budget would buy:

- **More episodes.** Five episodes cannot tell 10% from 40%. Placing a task in a band takes 20 to 30, roughly $15 to $20 per task on Astra.
- **More steps.** The balance tasks end at calls 43 to 57 of 60. A longer budget would show how much of that failure is running out of room.
- **A side camera.** Astra misjudged an overhang by 5 mm from the top view, and height is hard to read from above. I did not test a third camera.
- **Larger images and higher effort.** I tried both on one task (480 px, high effort) and saw no clear change, 6/8 against 9/15. I would not spend here first.

## The main lesson: most low scores were our fault

Six tasks looked hard for Astra. Three did not survive checking.

The literature warned me, and I still underestimated it. JustRUA moved a benchmark score from 29.7 to 50.3 by changing only the harness, which is as much as a model generation. OpenAI found flawed tests in 59% of the SWE-bench Verified problems its model kept failing. I built the truth test early for that reason, and it caught the early bugs. It did not catch the ones below, because they only appear when an agent does something the scripted solution never does.

| What we saw | What it was | After the fix |
|---|---|---|
| Astra says the drawer is closed and it isn't | The drawer slide had no friction and drifted open | 3/15 became 9/10 |
| Many failures "hit the step cap" | Our counter also counted tool results as steps | Almost none did |
| loose_drawer 0/8 | The prompt never said the heavy block was there to use | 5/10 |
| hidden_weight 1/10 | A wrist turn ran a joint into its stop and the arm stayed stuck | Unknown, between 10% and 60% |
| plate_to_edge 0/5 | My fix for the jam jerked the arm during normal grasps | Reverted. 7/10 on clean episodes |

The last row is my own bug, and replay is how I caught it. Recorded episodes replay exactly: I ran 106 of them again on today's code. All 88 recorded on the current harness matched line for line, and the 18 that differed were exactly the ones my bad fix had touched.

That gave me two free tools:

- **A regression test for the harness.** Before paying for a model after any change, replay episodes that used to succeed. Three of five plate_to_edge successes failed, and that is how the bad fix showed up.
- **A way to sort episodes** into clean and contaminated, so results can be reported on the clean ones.

Warning signs that would have saved time: a score below what guessing would get (hidden_weight's 10% against a 25% floor), failures bunched at the end of the step budget, and two moves in a row stopping 10 cm short.

What also helped: a second model read the traces with no context and found the wrist jam. And for each hard task I made a simpler version (told the trick, or asked for less) to see whether the failure was the idea or the execution.

## Bottlenecks

- **The world stands still between moves.** The sim only advances while the arm is moving, so nothing fast or reactive can be tested. This is the biggest gap. My lab teammate named dynamic manipulation as where agents are weakest.
- **Scripted solutions know too much.** They know the hidden masses. They prove the physics works, not that the task can be solved from what the agent can see. I wrote one closed-loop solution, which sorts the cubes from the balance's tilt alone, 5/5. Every hidden-property task needs one.
- **One robot.** Franka only, one arm, a parallel gripper. The brief asks for embodiments as an input, and this pipeline does not have that yet. Adding one means a second arm in the scene builder and re-tuning every grasp check.
- **Rigid objects only.** No bags, zippers, screw threads, or two-handed grips. That rules out most of Robocurve's six tasks.
- **The wrist.** Tilted grasps stall, and the jam is flagged, not fixed.
- **Pass or fail grading.** Robocurve scores partial progress by milestone. Ours gives no credit for a stack that stood 5 mm short.
- **Sim and real disagree in places.** Standing an object upright is 0/20 for Astra on real robots and 5/5 here.
- **Small samples.** Two of the five tasks have five episodes.

## What scale needs

1. Run generate, check, calibrate, flag, and replay as one loop with no hand steps.
2. Make "replay recorded successes" and "scripted solution through the real tool" standard checks.
3. Recalibrate on each new model release. Tasks tuned to 15-30% for sol are 40-100% for Astra.
4. A real-time mode in the harness, so dynamic tasks become possible.
5. A second embodiment, with every check rerun per robot.
6. Milestone grading, and an LLM judge for trace review with human spot checks.

## Open questions

- **Why a 5-30% band?** The papers I found on difficulty filtering argue for about 50%, where a pass/fail result carries the most signal (Online Difficulty Filtering, DAPO, No Regrets). A task at 5% carries about a fifth of the signal of one at 50%. HUD's own guide says a task is "often" hard at 50% or less. I kept the brief's band and would like to understand the reason for it.
- **Which model defines the band?** I tuned for sol first, then had to start over for Astra.

## Sources

- JustRUA, [arXiv 2611.16009](https://arxiv.org/abs/2611.16009)
- OpenAI on [SWE-bench Verified](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)
- Online Difficulty Filtering, [arXiv 2504.03380](https://arxiv.org/html/2504.03380v2). DAPO, [arXiv 2503.14476](https://arxiv.org/pdf/2503.14476v2). No Regrets, [arXiv 2408.15099](https://arxiv.org/pdf/2408.15099)
- HUD, [What is a good task](https://www.hud.ai/research/what-is-a-good-task)
- Robocurve, [Six Easy Tasks](https://robocurve.org/blog/six-easy-tasks/)
- Longer notes: `reports/RUA harness failure factors.md`
