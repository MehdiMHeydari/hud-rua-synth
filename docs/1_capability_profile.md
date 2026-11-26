# 1. What robot-use agents can and can't do

Setup for every number here: a Franka arm in MuJoCo, driven by an LLM through HUD's `move_to` tool. The agent gets a top camera and a wrist camera (256 px), 60 steps, and medium reasoning effort. The main model is GPT-6 Astra. GPT-6 sol and luna are the cheaper comparisons.

## Short version

Astra knows the physics. It fails when the task leaves little room for error in carrying it out.

Asked for an overhang that two blocks cannot reach, it answers in one call: "14/2 + 14/4 = 10.5 cm, short of the required 11.5 cm." Given four blocks, where the same overhang is possible, it builds the right kind of stack and then tips it over on about three tries in four.

## How I got to these tasks

**I started from what the literature says agents get wrong.** Recent studies put frontier models at 40-50% on standard manipulation suites: Astra scores 44% on LIBERO-10 and 49.8% on RoboARCade. They name the same weak spots: precise placement, multi-step tasks, and claiming success that didn't happen (24-39% of subtasks in RoboARCade). So my first seven tasks covered those: drawers, ordered stacking, peg insertion, a hook tool, and placing things in another person's left and right. I tuned each to 15-30% on sol.

**Then two things changed the plan.** Lukass pointed out that labs already train on standard manipulation, and asked for tasks outside pick-and-place. And when I ran Astra on the seven, it scored 40-100%. The standard families were no longer hard.

**So I asked what the literature says is not improving.** RoboARCade reports that scene misunderstanding is now rare and most failures are "imprecise execution of a reasonable strategy". The Bitter Lesson study on real arms lists irrecoverable errors, such as knocking an object off the table, as a main failure. Robocurve's Six Easy Tasks (Nov 2026) has Astra at 0/36 on real robots, and every failure they describe is physical: a dropped key, a bottle cap that never threads, a backpack that slides instead of being held. A teammate in my lab said the same from experience: fast, contact-rich manipulation.

**That gave me a recipe.** Pick tasks where the right strategy is easy to know, the margin for carrying it out is thin, and one mistake cannot be undone. Stacking blocks out past an edge fits: the answer is a textbook result, and one bad placement puts a block on the floor. Weighing on a seesaw fits too: the method is obvious, and the surface moves under you.

**Last, I gave each hard task an easier sibling.** A low score alone doesn't say whether the model lacked the idea or the execution. balance_pick asks for a third of balance_sort's work. overhang_or_impossible asks whether Astra can work out the limit without building anything. The answers are in the table below.

## What Astra handles

- Precise insertion, tool use, drawers, ordered stacking, and other-person frames: 40-100%.
- Visual tricks: picking the one real cube among flat red decals (5/5), rearranging objects to match a goal photo (5/5).
- Finding a heavy cube among identical ones by pushing them (5/5).
- Counterweights (3/5) and bracing a loose box against a visible stop (3/3).
- Honest reporting. When it fails it almost always says so.

## Where it fails

Counts are clean episodes only: no arm jam, no harness bug. Doc 3 explains why that matters.

| Task | What it asks | Why I built it | Astra | What goes wrong |
|---|---|---|---|---|
| max_overhang | Stack four blocks on a ledge so the top one sticks out 11.5 cm | Known answer (the book-stacking problem), thin margin, a fall can't be undone | 5/18 | The stack tips when the last block is released |
| weighted_overhang | Same, but each block hides a weight at one end and 15 cm is asked | Adds something it has to find out by handling the blocks | 0/12 | The supports tip while it is still stacking |
| balance_sort | Order three identical-looking cubes by weight, using a seesaw as a balance | The answer can't be seen, only measured | 1/12 | It reads the balance correctly, then loses cubes on the tilting plank |
| balance_pick | Same scene, only find the heaviest | Easier sibling: is balance_sort hard because it is long, or because of the balance? | 1/5 | In all 3 failures where it named a cube it named the right one, then dropped it |
| overhang_or_impossible | max_overhang, but on half the seeds only two blocks exist and the right answer is "impossible" | Easier sibling: does it know the limit? | 3/5 | Impossible seeds 2/2. Buildable seeds 1/3 |

Three things the traces show:

1. **It builds the right kind of stack and leaves no margin.** It steps the blocks forward the way the textbook solution does, and aims for 12 to 12.5 cm when 11.5 is asked. Our scripted solution keeps 1 cm of safety on every block. The tool only stops within about 1 cm of where it is told, so Astra's margin is too thin.
2. **It tests by letting go.** To find out whether something is stable it releases it and watches. When a wrong guess means a block on the floor, that one test ends the attempt.
3. **It misreads small distances.** One stack stood fine at 11.0 cm and was reported as "approximately 12 cm". Five millimetres is hard to see in a 256 px top view.

The two siblings settle the question. balance_pick shows the trouble is handling cubes on the plank, not the length of the task. overhang_or_impossible shows Astra has the statics exactly right and loses in the building.

## Things that looked like failures and weren't

I had to withdraw three results after checking them. They are listed here because they are the easiest mistakes to repeat.

- **"Astra can't tell when it has failed."** The drawer in our sim had no friction, so it slid open after Astra closed it. With friction added, that task went from 3/15 to 9/10.
- **"Astra can't find a hidden weight."** The 1/10 was mostly our arm jamming on a wrist turn. The true rate is somewhere between 10% and 60%.
- **"Astra never braces a loose object."** It scored 0/8 only while the prompt didn't mention the heavy block it could use. Once the prompt did, 5/10.

## Cheaper models

sol scored 0/10 on balance_sort and 2/10 on max_overhang. It had 40 steps to Astra's 60, so part of that gap is the step budget. luna is at 0-10% on nearly everything and is only useful for finding harness bugs cheaply.

Difficulty depends on the model. A task set needs recalibrating whenever the model changes.

## Task groups worth generating

| Group | Difficulty knob | Example |
|---|---|---|
| Statics and centre of mass | Overhang distance, number of blocks | max_overhang |
| Hidden properties found by handling | Mass ratio, where the weight sits | weighted_overhang |
| Using an instrument on an unstable surface | Number of weighings, plank damping | balance_sort, balance_pick |
| Judging whether a task is possible | Share of impossible seeds | overhang_or_impossible |

Not worth generating for Astra: selecting among objects, reference frames, plain pick-and-place.

## Limits of this profile

- One robot, one arm, rigid objects, and a world that stands still between moves. The literature's clearest lasting gap is dynamic control (models act at about 0.3 Hz), and nothing here tests it.
- The two newest tasks have 5 episodes each.
- One real-robot result did not carry over. Standing a lying object upright is 0/20 for Astra at Robocurve and 5/5 in our sim, because a bar pinched at one end swings freely in our gripper.

## Sources

- LIBERO-10 frontier evaluation, [arXiv 2610.30051](https://arxiv.org/abs/2610.30051)
- RoboARCade, [arXiv 2611.08209](https://arxiv.org/abs/2611.08209)
- The Bitter Lesson Comes to Robotics, [arXiv 2610.25287](https://arxiv.org/html/2610.25287v1)
- Robocurve, [Six Easy Tasks](https://robocurve.org/blog/six-easy-tasks/) and [RoboDojo-RC Tier 1](https://robocurve.org/opus-5-5-robodojo-rc-tier-1/)
- Longer notes on all of these: `reports/Synthetic robot task generation review.md`
