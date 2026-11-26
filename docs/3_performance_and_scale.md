# Performance and bottlenecks

## Cost per attempt

Keeping attempts cheap shaped most of the design. The brief warns that a careless Astra attempt can run 150+ moves and cost about $60. Mine cost under a dollar each.

| What | Cost | Settings |
|---|---|---|
| One Astra attempt | about $0.73 | 60 moves, two small camera images per move, medium effort |
| One sol attempt | about $0.13 | 40 moves |
| One luna attempt | about $0.015 | 40 moves |
| Generating one task | $0.15 to $1.15 | 1 to 5 tries |
| Every check, scripted solution and replay | free | Runs on a laptop |

These are estimates from my own log. The exact figures are on HUD's usage page.

How I kept it down:

- **Cheap models first.** luna and sol found the bugs in my setup. All eight of luna's first failures turned out to be my fault, and finding that out cost a few cents.
- **Free checks before any paid run.** A task has to pass about ten checks, including a working scripted solution, before a model ever sees it.
- **Small screens.** Three to five Astra attempts show whether a task is worth more. Only tasks that hold up get a bigger run.
- **Short attempts.** A limit of 60 moves, two small images per move, five attempts running at once.
- **Replays instead of reruns.** To check whether a failure was my fault, I replay the moves the model recorded, on my own machine, for free.

What a bigger budget would buy:

- **More attempts per task.** Five attempts can't tell 10% from 40%. A reliable success rate needs 20 to 30, roughly $15 to $20 per task on Astra.
- **More moves.** In the balance tasks, attempts end after 43 to 57 of the 60 moves. A higher limit would show how much of that failure is just running out of room.
- **A side camera.** Astra misjudged an overhang by half a centimetre, and height is hard to see from above. I didn't test a third camera.
- **Bigger images and higher effort.** I tried both on one task and saw no clear change (6 of 8 against 9 of 15). I wouldn't spend here first.

## The main lesson: most low scores were my fault

Six tasks looked hard for Astra. Three of them stopped looking hard once I checked.

The literature had warned me, and I still underestimated it. JustRUA moved a benchmark score from 29.7 to 50.3 by changing only the setup around the model, which is as big a jump as a new model generation. OpenAI found broken tests in 59% of the SWE-bench Verified problems its model kept failing. I built the truth test early for this reason, and it caught the first bugs. It couldn't catch the ones below, because they only show up when a model does something my scripted solution never does.

| What I saw | What it actually was | After the fix |
|---|---|---|
| Astra says a drawer is closed when it isn't | My simulated drawer had no friction and slid back open | 3 of 15 became 9 of 10 |
| Many failures seemed to run out of moves | My counter was counting the tool's replies as moves too | Almost none did |
| loose_drawer, 0 of 8 | The instructions never mentioned the heavy block the robot could use | 5 of 10 |
| hidden_weight, 1 of 10 | A large wrist turn ran a joint into its limit and the arm got stuck | Unknown, somewhere between 10% and 60% |
| plate_to_edge, 0 of 5 | My own fix for that arm jam jerked the arm during normal grasps | Fix undone. 7 of 10 on attempts without a jam |

The last row was my own bug, and replaying is how I caught it. A recorded attempt replays exactly the same way every time. I replayed 106 of them on my latest code. All 88 recorded on the current setup matched line for line, and the 18 that didn't were exactly the ones my bad fix had touched.

That gave me two free tools:

- **A safety check for any change to the setup.** Before paying for a model run, replay attempts that used to succeed. Three of five plate_to_edge successes failed on replay, and that is how the bad fix showed up.
- **A way to separate clean attempts from spoiled ones**, so results can be reported on the clean ones only.

Signs that would have saved me time: a score lower than guessing would get (hidden_weight scored 10% where guessing gets 25%), failures bunched right at the move limit, and two moves in a row stopping 10 cm short of where they were told to go.

Two other things helped. A second model read the recordings with no context and spotted the arm jam. And for each hard task I built a simpler version, either telling the model the trick or asking for less, to see whether it was missing the idea or the execution.

## Bottlenecks

- **The world stands still between moves.** The simulation only runs while the arm is moving, so nothing fast or reactive can be tested, like catching a rolling ball. This is the biggest gap. My lab teammate named fast, reactive manipulation as where these agents are weakest.
- **The scripted solutions know too much.** They know the hidden weights. That proves the physics works, not that the task can be solved from what the agent can see. I wrote one solution that has to find the answer itself (it sorts the cubes using only the seesaw's tilt, 5 of 5). Every hidden-property task needs one.
- **One robot.** Only the Franka arm, with one two-finger gripper. The brief says the pipeline should take robots as an input, and mine doesn't yet. Adding one means a second arm in the scene builder and re-tuning every grasp check.
- **Solid objects only.** No bags, zips, screw threads, or tasks needing two hands. That rules out most of Robocurve's six tasks.
- **The wrist.** Grasps with a tilted gripper often stall, and the arm jam is flagged in every run, not fixed.
- **Pass or fail grading.** Robocurve gives partial credit for each step reached. Mine gives nothing to a stack that stood half a centimetre short.
- **Simulation and real robots disagree in places.** Standing a lying object upright is 0 of 20 for Astra on real robots and 5 of 5 in mine.
- **Small samples.** Several tasks have only five attempts.

## What it would take to scale

1. Run the whole loop (generate, check, measure on the model, flag problems, replay) with no manual steps.
2. Make "replay old successes" and "scripted solution through the real tool" standard checks.
3. Re-measure every task when a new model comes out. Tasks I tuned to 15-30% for sol are 40-100% for Astra.
4. A real-time mode in the simulation, so fast tasks become possible.
5. A second robot, with every check rerun for it.
6. Partial-credit grading, and a model that reads the recordings first, with a person spot-checking.

## References

- JustRUA, [arXiv 2611.16009](https://arxiv.org/abs/2611.16009)
- OpenAI on [SWE-bench Verified](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)
- Robocurve, [Six Easy Tasks](https://robocurve.org/blog/six-easy-tasks/)
- Longer notes: `reports/RUA harness failure factors.md`
