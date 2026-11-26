# 1. What robot-use agents can and can't do

The setup is the same for every result here. A simulated Franka arm sits at a table. A language model controls it with one tool, `move_to`, and sees two camera images after each move, one from above and one from the wrist. It gets 60 moves per attempt. The main model is GPT-6 Astra. GPT-6 sol and luna are cheaper comparisons.

## Summary

Astra understands the physics of these tasks. What it can't do reliably is carry out its own plan when there is little room for error.

One task shows this clearly. The robot has to stack blocks on a ledge so the top block sticks out 11.5 cm past the edge. With two blocks that is impossible, and Astra says so on its first move without touching anything: "14/2 + 14/4 = 10.5 cm, short of the required 11.5 cm." With four blocks it is possible. Astra starts the right kind of stack, and it falls over about three times in four.

## The five tasks

| Task | What the robot has to do | Astra succeeded | What goes wrong |
|---|---|---|---|
| max_overhang | Stack four blocks on a ledge so the top one sticks out 11.5 cm past the edge without anything falling | 5 of 18 | The stack tips when it lets go of the last block |
| weighted_overhang | The same, but every block has a hidden weight in one end, and the target is 15 cm | 0 of 12 | The lower blocks tip while it is still building |
| balance_sort | Three cubes look identical but weigh 100, 150 and 220 g. Put them in order of weight, using a seesaw on the table as a scale | 1 of 12 | It reads the seesaw correctly, then cubes slide off the tilting plank |
| balance_pick | Same cubes and seesaw, but only find the heaviest one | 1 of 5 | It names the right cube, then drops it taking it off the seesaw |
| overhang_or_impossible | max_overhang, but half the time there are only two blocks, which can't reach. Then the right answer is to say "impossible" | 3 of 5 | Right both times with two blocks. With four, it built a stack that held once in three tries |

I only count attempts where my own setup didn't interfere, for example by the arm getting stuck. Doc 3 explains how I tell.

## How I got to these tasks

I started with what the literature says these agents get wrong: precise placement, multi-step tasks, and claiming success that didn't happen (LIBERO-10, RoboARCade). My first seven tasks covered those, and I tuned them so that sol passed 15-30% of the time.

Two things changed the plan. Lukass said labs already train on standard manipulation and asked for tasks outside pick-and-place. And Astra scored 40-100% on those seven.

So I looked for what is not improving. RoboARCade says failures now come "mostly from choosing a poor manipulation strategy or executing a good one imprecisely, rarely from misunderstanding the scene". A teammate in my lab said the same. That gave me a recipe: pick a task where the right method is easy to know, the margin for doing it is thin, and a mistake can't be undone.

- **max_overhang** is a textbook puzzle (how far can a stack of books lean past a desk edge). The answer is known, and one bad placement puts a block on the floor.
- **balance_sort** came from an earlier task where Astra found a much heavier cube by pushing it. I made the weights close so pushing tells you nothing and the seesaw is the only way.
- **weighted_overhang** combines the two. 15 cm is further than four ordinary blocks can reach, so it only works if the robot finds each block's light end and points it outward.
- **balance_pick** and **overhang_or_impossible** are shorter versions of the first two. I built them to see whether Astra lacks the idea or the execution. Both say execution.

Robocurve's Six Easy Tasks came out on my last day. Astra scores 0 of 36 there on real robots, all physical failures, which backed up the direction. I built three tasks straight from it, and none held up as hard in my simulation.

## What the failures have in common

- **It leaves no safety margin.** The further a block sticks out, the closer the stack is to tipping. The task only needs 11.5 cm, but Astra pushes the top block out to 12 or 12.5 cm, which makes its stack less stable than it has to be. My scripted solution does the opposite: it keeps every block a full centimetre back from the point where it would tip. That matters because the robot can only place a block to within about a centimetre, so a stack built right at the limit falls from one small placement error.
- **It tests by letting go.** To check if a block is stable, it releases it and watches. A wrong guess ends the attempt.
- **It misjudges small distances.** One stack stood fine half a centimetre short, and Astra reported it as "approximately 12 cm".

## What Astra does well

It scores 40-100% on my first seven tasks: peg in a hole, a hook tool, drawers, ordered stacking, and placing things to another person's left or right. It passed every attempt at two tasks built to fool its vision. And when it fails, it nearly always says so.

## Results I had to withdraw

Three times I thought I'd found something Astra couldn't do, and the fault was in my setup.

- **"It can't tell when it has failed."** My simulated drawer had no friction and slid back open. With friction, 3 of 15 became 9 of 10.
- **"It can't find a hidden weight."** Most failures were the robot's wrist getting stuck. The true rate is somewhere between 10% and 60%.
- **"It never steadies a loose object."** My instructions didn't mention the heavy block it could use. With one more sentence, 0 of 8 became 5 of 10.

## Cheaper models

sol scored 0 of 10 on balance_sort and 2 of 10 on max_overhang, with 40 moves to Astra's 60. luna fails nearly everything and is only useful for finding mistakes in the setup cheaply. Tasks I tuned for sol are mostly easy for Astra, so any task set has to be re-measured when a new model comes out.

## Task groups worth generating

- **Balance and centre of mass.** Harder with a longer overhang or fewer blocks.
- **Hidden properties** the robot can only learn by handling an object. Harder when the difference is smaller.
- **Using a tool on an unsteady surface.** Harder with more weighings.
- **Deciding whether a task can be done.** Vary how often it can't.

Not worth generating for Astra: picking the right object, other-person frames, plain pick-and-place.

## Limits

- One arm, a two-finger gripper, solid objects only.
- The simulated world stands still between moves, so nothing fast or reactive is tested. Other studies name that as the biggest remaining gap.
- The two newest tasks have five attempts each.
- Robocurve found Astra can't stand a lying bottle upright (0 of 20). In my simulation it does it 5 of 5, because a bar held at one end swings freely in the simulated gripper.

## Sources

- LIBERO-10 frontier evaluation, [arXiv 2610.30051](https://arxiv.org/abs/2610.30051)
- RoboARCade, [arXiv 2611.08209](https://arxiv.org/abs/2611.08209)
- Robocurve, [Six Easy Tasks](https://robocurve.org/blog/six-easy-tasks/) and [RoboDojo-RC Tier 1](https://robocurve.org/opus-5-5-robodojo-rc-tier-1/)
- Longer notes: `reports/Synthetic robot task generation review.md`
