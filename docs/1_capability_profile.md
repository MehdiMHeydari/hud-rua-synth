# 1. What robot-use agents can and can't do

Setup for every number here: a Franka arm in MuJoCo, driven by an LLM through HUD's `move_to` tool. The agent gets a top camera and a wrist camera (256 px), 60 steps, and medium reasoning effort. The main model is GPT-6 Astra. GPT-6 sol and luna are the cheaper comparisons.

## Short version

Astra knows the physics. It fails when the task leaves little room for error in carrying it out.

Asked for an overhang that two blocks cannot reach, it answers in one call: "14/2 + 14/4 = 10.5 cm, short of the required 11.5 cm." Given four blocks, where the same overhang is possible, it builds the right kind of stack and then tips it over on about three tries in four.

## What Astra handles

- Precise insertion, tool use, drawers, ordered stacking, and placing things in another person's left/right frame. These were tuned to be 15-30% for sol. Astra scores 40-100% on them.
- Visual tricks: picking the one real cube among flat red decals (5/5), rearranging objects to match a goal photo (5/5).
- Finding a heavy cube among identical ones by pushing them (5/5).
- Counterweights (3/5) and bracing a loose box against a visible stop (3/3).
- Honest reporting. When it fails it almost always says so.

## Where it fails

Counts are clean episodes only: no arm jam, no harness bug. See doc 3 for why that matters.

| Task | What it asks | Astra | What goes wrong |
|---|---|---|---|
| max_overhang | Stack four blocks on a ledge so the top one sticks out 11.5 cm | 5/18 | The stack tips when the last block is released |
| weighted_overhang | Same, but each block hides a weight at one end and 15 cm is asked | 0/12 | The supports tip while it is still stacking |
| balance_sort | Order three identical-looking cubes by weight, using a seesaw as a balance | 1/12 | It reads the balance correctly, then loses cubes on the tilting plank |
| balance_pick | Same scene, only find the heaviest | 1/5 | In 3 of 4 failures it names the right cube, then drops it |
| overhang_or_impossible | max_overhang, but on half the seeds only two blocks exist and the right answer is "impossible" | 3/5 | Impossible seeds 2/2. Buildable seeds 1/3 |

Three things the traces show:

1. **It builds the right kind of stack and leaves no margin.** It steps the blocks forward the way the textbook solution does, and aims for 12 to 12.5 cm when 11.5 is asked. Our scripted solution keeps 1 cm of safety on every block. The tool only stops within about 1 cm of where it is told, so Astra's margin is too thin.
2. **It tests by letting go.** To find out whether something is stable it releases it and watches. When a wrong guess means a block on the floor, that one test ends the attempt.
3. **It misreads small distances.** One stack stood fine at 11.0 cm and was reported as "approximately 12 cm". Five millimetres is hard to see in a 256 px top view.

## Things that looked like failures and weren't

I had to withdraw three results after checking them. They are listed here because they are the easiest mistakes to repeat.

- **"Astra can't tell when it has failed."** The drawer in our sim had no friction, so it slid open after Astra closed it. With friction added, that task went from 3/15 to 9/10.
- **"Astra can't find a hidden weight."** The 1/10 was mostly our arm jamming on a wrist turn. The true rate is somewhere between 10% and 60%.
- **"Astra never braces a loose object."** It scored 0/8 only while the prompt didn't mention the heavy block it could use. Once the prompt did, 5/10.

## Cheaper models

sol scored 0/10 on balance_sort and 2/10 on max_overhang. It had 40 steps to Astra's 60, so part of that gap is the step budget. luna is at 0-10% on nearly everything and is only useful for finding harness bugs cheaply.

Difficulty depends on the model. The seven tasks I calibrated to 15-30% for sol are mostly solved by Astra, so a task set needs recalibrating whenever the model changes.

## Task groups worth generating

| Group | Difficulty knob | Example | Where the idea came from |
|---|---|---|---|
| Statics and centre of mass | Overhang distance, number of blocks | max_overhang | The book-stacking problem |
| Hidden properties found by handling | Mass ratio, where the weight sits | weighted_overhang | Our own traces |
| Using an instrument on an unstable surface | Number of weighings, plank damping | balance_sort, balance_pick | Balance-scale puzzles |
| Judging whether a task is possible | Share of impossible seeds | overhang_or_impossible | Astra giving up on doable seeds in an earlier task (3/5) |

Not worth generating for Astra: selecting among objects, reference frames, plain pick-and-place.

Two outside sources pointed me at physical execution instead of reasoning. Robocurve's Six Easy Tasks (Nov 2026) has Astra at 0/36 on real robots: it drops keys, never threads a bottle cap, and lets a backpack slide instead of holding it. A teammate in my lab named fast, contact-rich manipulation as the weak spot.

## Limits of this profile

- One robot, one arm, rigid objects, and a world that stands still between moves. Nothing here tests speed or reaction.
- The two newest tasks have 5 episodes each.
- One real-robot result did not carry over. Standing a lying object upright is 0/20 for Astra at Robocurve and 5/5 in our sim, because a bar pinched at one end swings freely in our gripper.
