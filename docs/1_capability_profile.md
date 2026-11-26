# Capability profile

Setup for every number here: a Franka arm in MuJoCo, driven by an LLM through HUD's `move_to` tool. The agent gets a top camera and a wrist camera (256 px), 60 steps, and medium reasoning effort. The main model is GPT-6 Astra. GPT-6 sol and luna are the cheaper comparisons.

## Summary

Astra understands the physics of these tasks. What it can't do reliably is carry out its own plan when there is little room for error.

One task shows this clearly. The robot has to stack blocks on a ledge so the top block sticks out 11.5 cm past the edge. With two blocks that is impossible, and Astra says so on its first move without touching anything: "14/2 + 14/4 = 10.5 cm, short of the required 11.5 cm." With four blocks it is possible. Astra starts the right kind of stack, and it falls over about three times in four.

## How I chose the tasks

**I started from what the literature says agents get wrong.** Recent studies put frontier models at 40-50% on standard manipulation suites: Astra scores 44% on LIBERO-10 (at high effort) and 49.8% on RoboARCade. They name the same weak spots: precise placement, multi-step tasks, and claiming success that didn't happen (24-39% of subtasks in RoboARCade). So my first seven tasks covered those: drawers, ordered stacking, peg insertion, a hook tool, and placing things in another person's left and right. I tuned each to 15-30% on sol.

**Then two things changed the plan.** Lukass pointed out that labs already train on standard manipulation, and asked for tasks outside pick-and-place. And when I ran Astra on the seven, it scored 40-100%. The standard families were no longer hard.

**So I asked what the literature says is not improving.** RoboARCade reports that failures come "mostly from choosing a poor manipulation strategy or executing a good one imprecisely, rarely from misunderstanding the scene". The Bitter Lesson study on real arms describes trials ending on an unrecoverable error, such as knocking an object off the table. A teammate in my lab said the same from experience: fast, contact-rich manipulation is where these agents break.

**That gave me a recipe.** Pick tasks where the right strategy is easy to know, the margin for carrying it out is thin, and one mistake cannot be undone. Stacking blocks out past an edge fits: the answer is a textbook result, and one bad placement puts a block on the floor. Weighing on a seesaw fits too: the method is obvious, and the surface moves under you.

**Last, I gave each hard task an easier sibling.** A low score alone doesn't say whether the model lacked the idea or the execution, so two of the five tasks exist only to answer that.

**Robocurve's Six Easy Tasks came out on the last day**, after the stacking and balance tasks were built. Astra scores 0/36 there on real robots, and every failure is physical: a dropped key, a bottle cap that never threads, a backpack that slides instead of being held. It backed up the direction. I also built three tasks straight from it (bracing a loose drawer, picking up a thin card, standing a bar upright), and none of them held up as hard in our sim. Astra braces once the prompt is fair and stands the bar up 5/5, and the thin card turned out to be a quirk of the simulator's contact model.

## The tasks one by one

**max_overhang.** I wanted a statics problem with a known answer. This is the book-stacking problem: how far can a stack lean out past an edge? With 14 cm blocks, one block reaches 7 cm, two reach 10.5, and four reach 14.6 at best. I set the target at 11.5 cm so it needs at least three blocks, each offset correctly, and can't be done by trial and error on one block. What I expected to be hard: every placement shifts the balance of everything above it, and a block that falls off the ledge is gone. My first scripted solution used 7 mm of safety per block and fell over on every seed, which told me the margins would matter before any model ran.

**balance_sort.** An earlier task, heavy_cube, hid one heavy cube among identical ones. Astra solved it 5/5 by pushing each cube and feeling which one resisted. That worked because the heavy cube was five times heavier. So I made the weights close (100, 150 and 220 g), where a push or a lift tells you nothing, and put a balance on the table. Now the only way to know is to measure, and the agent has to plan which pairs to compare. What I expected to be hard: planning the comparisons. What turned out to be hard: getting cubes on and off a plank that tilts. Before trusting the result I wrote a solution that sorts the cubes from the plank's tilt alone, to prove it could be done. It works 5/5.

**weighted_overhang.** This puts the two ideas together. Each block has a weight hidden at one end, so its balance point is off-centre, and you can't see which end. The target is 15 cm, which is past what four ordinary blocks can reach (14.6), so the task can only be done by finding each block's light end and pointing it outward. What I expected to be hard: it needs both the measuring from balance_sort and the careful stacking from max_overhang, and a mistake in either ends the attempt.

**balance_pick.** The easier sibling of balance_sort. Same cubes, same balance, but only the heaviest has to be found: two weighings and one placement. I built it to answer one question. balance_sort's failures mostly ended close to the step limit, so was it hard, or just long? If Astra passed this, the answer was "long". It scored 1/5, and in all three failures where it named a cube it named the right one and then dropped it. So the balance itself is the problem.

**overhang_or_impossible.** The easier sibling of max_overhang. On half the seeds there are only two blocks, which can reach 10.5 cm at most, so the 11.5 cm target can't be met and the right answer is to say so. It came from an earlier task where Astra, offered the option to call a task impossible, gave up on two of five that could be done. I wanted to know whether Astra understands the limit or just tries things. It understands it exactly: on the two-block seeds it gave the formula in one or two calls and touched nothing. On the four-block seeds it passed one of three. That is the cleanest evidence for the headline: the knowledge is there and the building fails.

## Strengths

- Precise insertion, tool use, drawers, ordered stacking, and other-person frames: 40-100%.
- Visual tricks: picking the one real cube among flat red decals (5/5), rearranging objects to match a goal photo (5/5).
- Finding a heavy cube among identical ones by pushing them (5/5).
- Counterweights (3/5) and bracing a loose box against a visible stop (3/3).
- Honest reporting. When it fails it almost always says so.

## Results

I only count attempts where my own setup didn't interfere, for example by the arm getting stuck. Doc 3 explains how I tell.

| Task | What the robot has to do | Astra succeeded | What goes wrong |
|---|---|---|---|
| max_overhang | Stack four blocks on a ledge so the top one sticks out 11.5 cm past the edge without anything falling | 5 of 18 | The stack tips when it lets go of the last block |
| weighted_overhang | The same, but every block has a hidden weight in one end, and the target is 15 cm | 0 of 12 | The lower blocks tip while it is still building |
| balance_sort | Three cubes look identical but weigh 100, 150 and 220 g. Put them in order of weight, using a seesaw on the table as a scale | 1 of 12 | It reads the seesaw correctly, then cubes slide off the tilting plank |
| balance_pick | Same cubes and seesaw, but only find the heaviest one | 1 of 5 | It names the right cube, then drops it taking it off the seesaw |
| overhang_or_impossible | max_overhang, but half the time there are only two blocks, which can't reach. Then the right answer is to say "impossible" | 3 of 5 | Right both times with two blocks. With four, it built a stack that held once in three tries |

Three things the traces show:

1. **It leaves no safety margin.** The further a block sticks out, the closer the stack is to tipping. The task only needs 11.5 cm, but Astra pushes the top block out to 12 or 12.5 cm, which makes its stack less stable than it has to be. My scripted solution does the opposite: it keeps every block a full centimetre back from the point where it would tip. The robot can only place a block to within about a centimetre, so a stack built right at the limit falls from one small placement error.
2. **It tests by letting go.** To find out whether something is stable it releases it and watches. When a wrong guess means a block on the floor, that one test ends the attempt.
3. **It misreads small distances.** One stack stood fine at 11.0 cm and was reported as "approximately 12 cm". Five millimetres is hard to see in a 256 px top view.

The two siblings settle the question. balance_pick shows the trouble is handling cubes on the plank, not the length of the task. overhang_or_impossible shows Astra has the statics exactly right and loses in the building.

## Retracted results

I had to withdraw three results after checking them. They are listed here because they are the easiest mistakes to repeat.

- **"Astra can't tell when it has failed."** The drawer in our sim had no friction, so it slid open after Astra closed it. With friction added, that task went from 3/15 to 9/10.
- **"Astra can't find a hidden weight."** The 1/10 was mostly our arm jamming on a wrist turn. The true rate is somewhere between 10% and 60%.
- **"Astra never braces a loose object."** It scored 0/8 only while the prompt didn't mention the heavy block it could use. Once the prompt did, 5/10.

## Cheaper models

sol scored 0/10 on balance_sort and 2/10 on max_overhang. It had 40 steps to Astra's 60, so part of that gap is the step budget. luna is at 0-10% on nearly everything and is only useful for finding harness bugs cheaply.

Difficulty depends on the model. A task set needs recalibrating whenever the model changes.

## Suggested task groups

| Group | Difficulty knob | Example |
|---|---|---|
| Statics and centre of mass | Overhang distance, number of blocks | max_overhang |
| Hidden properties found by handling | Mass ratio, where the weight sits | weighted_overhang |
| Using an instrument on an unstable surface | Number of weighings, plank damping | balance_sort, balance_pick |
| Judging whether a task is possible | Share of impossible seeds | overhang_or_impossible |

Not worth generating for Astra: selecting among objects, reference frames, plain pick-and-place.

## Limitations

- One robot, one arm, rigid objects, and a world that stands still between moves. The literature's clearest lasting gap is dynamic control (models act at about 0.3 Hz), and nothing here tests it.
- The two newest tasks have 5 episodes each.
- One real-robot result did not carry over. Standing a lying object upright is 0/20 for Astra at Robocurve and 5/5 in our sim, because a bar pinched at one end swings freely in our gripper.

## References

- LIBERO-10 frontier evaluation, [arXiv 2610.30051](https://arxiv.org/abs/2610.30051)
- RoboARCade, [arXiv 2611.08209](https://arxiv.org/abs/2611.08209)
- The Bitter Lesson Comes to Robotics, [arXiv 2610.25287](https://arxiv.org/html/2610.25287v1)
- Robocurve, [Six Easy Tasks](https://robocurve.org/blog/six-easy-tasks/) and [RoboDojo-RC Tier 1](https://robocurve.org/opus-5-5-robodojo-rc-tier-1/)
- Longer notes on all of these: `reports/Synthetic robot task generation review.md`
