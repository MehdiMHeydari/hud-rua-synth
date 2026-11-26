# 1. What robot-use agents can and can't do

Every result in this doc comes from the same setup. A simulated Franka robot arm sits at a table. A language model controls it by calling one tool, `move_to`, which moves the gripper to a position and opens or closes it. After each move the model gets two camera images, one from above and one from the wrist. It has 60 moves per attempt.

The model I care most about is GPT-6 Astra, the strongest one. I also ran two cheaper models, GPT-6 sol and luna, for comparison.

## Summary

Astra understands the physics of these tasks. What it can't do reliably is carry out its own plan when the plan leaves little room for error.

The clearest example is a task where the robot has to stack blocks on a ledge so that the top block sticks out past the edge by 11.5 cm.

When I give it only two blocks, that distance is physically impossible. Astra works this out on its first move, without touching anything. It writes: "14/2 + 14/4 = 10.5 cm, short of the required 11.5 cm." That is the correct textbook calculation.

When I give it four blocks, the distance is possible. Astra starts building the right kind of stack, with each block shifted a little further out than the one below. But the stack falls over in about three attempts out of four.

So the knowledge is there. The failure is in the doing.

## How I got to these tasks

**I started from what the literature says agents get wrong.** Recent studies put frontier models at 40-50% on standard manipulation suites: Astra scores 44% on LIBERO-10 (at high effort) and 49.8% on RoboARCade. They name the same weak spots: precise placement, multi-step tasks, and claiming success that didn't happen (24-39% of subtasks in RoboARCade). So my first seven tasks covered those: drawers, ordered stacking, peg insertion, a hook tool, and placing things in another person's left and right. I tuned each to 15-30% on sol.

**Then two things changed the plan.** Lukass pointed out that labs already train on standard manipulation, and asked for tasks outside pick-and-place. And when I ran Astra on the seven, it scored 40-100%. The standard families were no longer hard.

**So I asked what the literature says is not improving.** RoboARCade reports that failures come "mostly from choosing a poor manipulation strategy or executing a good one imprecisely, rarely from misunderstanding the scene". The Bitter Lesson study on real arms describes trials ending on an unrecoverable error, such as knocking an object off the table. A teammate in my lab said the same from experience: fast, contact-rich manipulation is where these agents break.

**That gave me a recipe.** Pick tasks where the right strategy is easy to know, the margin for carrying it out is thin, and one mistake cannot be undone. Stacking blocks out past an edge fits: the answer is a textbook result, and one bad placement puts a block on the floor. Weighing on a seesaw fits too: the method is obvious, and the surface moves under you.

**Last, I gave each hard task an easier sibling.** A low score alone doesn't say whether the model lacked the idea or the execution, so two of the five tasks exist only to answer that.

**Robocurve's Six Easy Tasks came out on the last day**, after the stacking and balance tasks were built. Astra scores 0/36 there on real robots, and every failure is physical: a dropped key, a bottle cap that never threads, a backpack that slides instead of being held. It backed up the direction. I also built three tasks straight from it (bracing a loose drawer, picking up a thin card, standing a bar upright), and none of them held up as hard in our sim. Astra braces once the prompt is fair and stands the bar up 5/5, and the thin card turned out to be a quirk of the simulator's contact model.

## The five tasks

For each task I describe what is on the table, what the robot has to do, why I built it, and what happened. I only count attempts where our own setup didn't interfere, for example by the arm getting stuck. Doc 3 explains how I tell those apart.

### max_overhang

There is a ledge 8 cm high and four identical blocks lying on the table next to it. Each block is 14 cm long. The robot has to stack the blocks on the ledge so that the top block, the red one, sticks out at least 11.5 cm past the edge of the ledge. Nothing may fall.

This is a known physics puzzle, usually told with books on the edge of a desk. One block can stick out 7 cm before it tips. Two blocks can reach 10.5 cm. Four can reach 14.6 cm at best. I chose 11.5 cm so that the robot needs at least three blocks, each one placed at the right offset.

I built it because I wanted a task where the right answer is well known but hard to carry out. Every block you add changes the balance of the whole stack, and once a block falls off the ledge, Astra rarely manages to recover it.

Astra succeeded in 5 of 18 attempts. In the failures, the stack tips over at the moment it lets go of the last block.

### weighted_overhang

This is the same stacking task, made harder in one way. Each block has a weight hidden inside one end, so it balances off-centre. The blocks look identical, and you cannot see which end is the heavy one. The red block now has to stick out 15 cm.

Four ordinary blocks could reach 14.6 cm at most, so 15 cm cannot be done by stacking alone. The robot has to find the light end of each block, by picking it up and seeing which way it tilts, and then point every light end outward.

I built it to combine the two things Astra found hardest: finding out something it can't see, and stacking with care.

Astra succeeded in 0 of 12 attempts. The lower blocks tip over while it is still building.

### balance_sort

There are three red cubes that look exactly the same but weigh 100, 150 and 220 grams. There are three circles drawn on the table. The robot has to put the lightest cube in the left circle, the middle one in the centre, and the heaviest on the right. On the table there is also a seesaw: a plank on a pivot that tips toward the heavier side when you put a cube on each end.

I built it because of an earlier task. In that one, a single cube was five times heavier than the others, and Astra found it every time by pushing each cube and noticing which one barely moved. So I made the weights close together, where pushing or lifting tells you nothing. The only way to sort them is to use the seesaw as a scale.

I expected the hard part to be planning which cubes to compare. It was not. Astra reads the seesaw correctly. What goes wrong is physical: the plank tilts when a cube lands on it, cubes slide off the end, and Astra can't get them back.

Astra succeeded in 1 of 12 attempts. To be sure the task can be done at all, I wrote a program that sorts the cubes using only the tilt of the seesaw. It works every time.

### balance_pick

This is a shorter version of balance_sort. Same cubes, same seesaw, but there is one circle and the robot only has to put the heaviest cube in it. That takes two weighings and one placement.

I built it to answer a specific question. In balance_sort, most failed attempts ended near the limit of 60 moves. So I couldn't tell whether the task was hard or simply too long. If Astra passed the short version, the answer would be "too long".

Astra succeeded in 1 of 5 attempts. In three of the four failures it said which cube was heaviest, and it was right each time. Then it dropped the cube while taking it off the seesaw. So the length of the task was not the problem. Handling cubes on a tilting plank is.

### overhang_or_impossible

This is max_overhang with a twist. In half of the attempts all four blocks are there. In the other half there are only two blocks, and two blocks cannot reach 11.5 cm. The robot is told that if the task can't be done, it should say "impossible" and explain why.

I built it to find out whether Astra knows the limit or just tries things until something works. The idea came from an earlier task, where Astra was allowed to call a task impossible and wrongly gave up on two tasks out of five that could be done.

With two blocks, Astra got it right both times. It gave the calculation and left the blocks alone. With four blocks, it built a stack that held in one attempt out of three.

This task is the best evidence for the summary at the top. Astra knows exactly how far a stack can reach. It loses when it has to build one.

## What the failed attempts have in common

I read the recordings of the failed attempts. Three things come up again and again.

First, Astra leaves itself almost no margin. In max_overhang it aims for 12 to 12.5 cm when 11.5 is asked. My own scripted solution keeps a full centimetre of safety on every block. The `move_to` tool is only accurate to about a centimetre, so Astra's stacks are often one small error away from falling.

Second, it tests things by letting go. To check whether a block is stable, it releases the block and watches what happens. If the guess was wrong, the block is on the floor and the attempt is over.

Third, it misjudges small distances. One stack stood perfectly well with the red block 11.0 cm out, half a centimetre short. Astra reported it as "approximately 12 cm". At the size of image it gets, half a centimetre is very hard to see from above.

## What Astra does well

Astra is not weak in general. On the seven tasks I built first, it scores between 40% and 100%. Those cover putting a peg in a hole, using a hook to pull something closer, opening and closing drawers, stacking in a given order, and placing an object to another person's left or right.

It also passed every attempt at two tasks built to fool its vision. In one, it had to pick the single real cube out of several flat red stickers. In the other, it had to rearrange objects to match a photo.

And it is honest. When it fails, it nearly always says that it failed.

## Results I had to withdraw

Three times I thought I had found something Astra couldn't do, and I was wrong. The fault was in my setup each time. I'm listing them because they are easy mistakes to make again.

The first was "Astra can't tell when it has failed." It kept reporting a drawer as closed when it wasn't. It turned out the drawer in my simulation had no friction, so it slid back open after Astra shut it. Once I added friction, Astra went from 3 successes in 15 to 9 in 10.

The second was "Astra can't find a hidden weight." It scored 1 in 10 on that task. Most of those failures were the robot's wrist getting stuck after a large turn, which is a flaw in my setup. I don't know the true rate. It is somewhere between 10% and 60%.

The third was "Astra never steadies a loose object before pulling on it." It scored 0 in 8 on a task with a light cabinet that slides when you pull its drawer. But my instructions never mentioned the heavy block on the table that it could use to hold the cabinet down. When I added one sentence saying so, it scored 5 in 10.

## Cheaper models

GPT-6 sol is clearly weaker on these tasks. It scored 0 in 10 on balance_sort and 2 in 10 on max_overhang. I gave sol 40 moves and Astra 60, so some of that gap comes from the shorter limit.

GPT-6 luna fails nearly everything, between 0% and 10%. It is still useful, because it is cheap enough to run many times while hunting for mistakes in the setup.

How hard a task is depends on the model. The seven tasks I first tuned so that sol would pass 15-30% of the time are mostly easy for Astra. Any set of tasks has to be re-measured when a new model comes out.

## Task groups worth generating

From all of this, four kinds of task look worth producing in bulk for a model like Astra. Each has a setting that makes it easier or harder.

- **Balance and centre of mass.** Stacking past an edge is the example. You make it harder by asking for a longer overhang or giving fewer blocks.
- **Hidden properties.** Something the robot can only learn by handling the object, like where its weight sits. You make it harder by making the difference smaller.
- **Using a tool on an unsteady surface.** The seesaw is the example. You make it harder by requiring more weighings.
- **Deciding whether a task can be done.** You vary how many of the attempts are impossible.

Three kinds are not worth generating for Astra, because it already does them well: picking the right object out of several, working in another person's left and right, and plain pick-and-place.

## Limits of this profile

This profile covers one robot arm with a simple two-finger gripper, handling solid objects. It says nothing about soft things like bags, or tasks that need two hands.

In my simulation, the world only moves while the arm is moving. Between moves, everything stands still. So I could not test anything fast or reactive, like catching a rolling ball. Other studies point to that as the area where these models are furthest behind, because they can only act about once every three seconds.

The two newest tasks, balance_pick and overhang_or_impossible, have five attempts each. That is enough to see the pattern and not enough for a precise success rate.

One result from real robots did not show up here. Robocurve found that Astra could not stand a lying bottle upright, 0 times in 20. In my simulation it stood a bar upright 5 times in 5. The reason is that a bar held at one end swings freely in my simulated gripper, which makes the task much easier than it is on a real robot.

## Sources

- LIBERO-10 frontier evaluation, [arXiv 2610.30051](https://arxiv.org/abs/2610.30051)
- RoboARCade, [arXiv 2611.08209](https://arxiv.org/abs/2611.08209)
- The Bitter Lesson Comes to Robotics, [arXiv 2610.25287](https://arxiv.org/html/2610.25287v1)
- Robocurve, [Six Easy Tasks](https://robocurve.org/blog/six-easy-tasks/) and [RoboDojo-RC Tier 1](https://robocurve.org/opus-5-5-robodojo-rc-tier-1/)
- Longer notes on all of these: `reports/Synthetic robot task generation review.md`
