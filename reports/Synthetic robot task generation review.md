# Calibrate generated robot tasks against the agent

Since 2023, researchers have converged on one recipe for LLM-generated robot tasks. A fixed simulator API and a curated asset library come first. The LLM proposes a task and writes code for the scene, the success check and often a scripted solution. Execution gates then filter for code that runs and tasks an oracle can solve, a short repair loop follows, and accepted tasks join a library that seeds the next round of generation. Getting runnable code is now close to solved: AnyTask reports 84-96% runnable tasks with a reasoning model and a tuned prompt ([AnyTask](https://arxiv.org/html/2512.17853v2)). Semantic correctness, solvability and difficulty are where the work remains. Every major generator (GenSim, GenSim2, RoboGen, RoboTwin 2.0, AnyTask) produces training data for RL, behaviour-cloning or VLA policies. None calibrates task difficulty against an LLM that drives the arm through tool calls, and that gap is the one this project fills. The benchmarks show where the 5-30% band sits. In late 2026, frontier models directly controlling arms with `move_to`-style calls score around 40-50% on suites such as LIBERO-10, RoboARCade and RoboDojo Tier 1. On precision tasks they fall to roughly 0-5%. Their failures come from metric precision, orientation, feedback interpretation and false claims of success, not from perception ([Bitter Lesson](https://arxiv.org/html/2610.25287v1); [RoboARCade](https://arxiv.org/abs/2611.08209)). For a MuJoCo pipeline aimed at robot-use agents, the design follows:
- The LLM emits a small declarative spec, and fixed code builds the scene.
- Validity checks run in physics, not through a VLM judge.
- Every task passes a negative control and a positive control.
- Calibration uses sequential sampling on the target agent, with the harness pinned and recorded.

Confidence markers are kept from the source notes:
- **[PK] / [recalled]**: details from prior knowledge, not re-fetched.
- **abstract-only**: only the abstract or project page was read.

Many 2026 robot-use-agent results are unreviewed arXiv preprints from Sep-Nov 2026. Model names such as GPT-6 Astra and Mythos Preview are reported as written in those sources.

## Generators write task code against a closed world, then filter by execution

### The common recipe
In every system the LLM writes *executable task code* against a fixed API and a closed asset library. Nobody lets the LLM invent geometry inside task code. Assets come from:
- a URDF whitelist (GenSim);
- PartNet-Mobility, or Objaverse retrieval checked by a VLM (RoboGen);
- an annotated object database (AnyTask).

The pipeline runs propose → generate → execute and verify → reflect and repair → admit to library. The library is fed back as few-shot context. GenSim's library serves as both retrieval context and fine-tuning data ([GenSim](https://arxiv.org/html/2310.01361v2)).

Acceptance funnels are steep. On primitive tasks, GenSim2 reports an execution rate of 0.94 but a solution rate of only 0.78. On long-horizon tasks the solution rate falls to 0.54-0.68, against 0.43 for RoboGen ([GenSim2](https://arxiv.org/html/2410.03645)). In other words, roughly a quarter to a half of runnable tasks still cannot be solved.

### Key papers

| System | Venue / status | One-line contribution |
|---|---|---|
| GenSim | ICLR 2024 (spotlight) | Two-stage LLM chain (description → code) on Ravens/PyBullet. Grew 10 human tasks into 100+. Gates: syntax, runtime, oracle demo, 3-vote LLM critic, human review. Tasks match human-written ones as training data (75.8% vs 76.6% single-task) ([arXiv](https://arxiv.org/html/2310.01361v2)) |
| GenSim2 | CoRL 2024 | SAPIEN articulated tasks. A VLM emits kPAM keypoint constraints for a planner. Bottom-up library composition beats top-down LLM decomposition (solution rate 0.68 vs 0.54). About 4 min of human time per task ([arXiv](https://arxiv.org/html/2410.03645)) |
| RoboGen | ICML 2024 | Propose → scene → decompose → pick a learner (RL / motion planning / trajectory optimisation) → reward. Of 155 tasks, 13 had scene failures and 6 had bad rewards, often from misreading joint-state semantics ([arXiv](https://arxiv.org/html/2311.01455v3)) |
| Eureka | ICLR 2024 | Gives the LLM the raw environment source code and evolves rewards against measured fitness. Beats expert rewards on 83% of 29 environments. It generates rewards, not tasks ([arXiv](https://arxiv.org/abs/2310.12931)) |
| Text2Reward | ICLR 2024 spotlight | Gives the LLM a compact Pythonic environment abstraction instead of raw source. Matches or beats expert rewards on 13 of 17 manipulation tasks ([arXiv](https://arxiv.org/html/2309.11489v3)) |
| Eurekaverse | CoRL 2024 oral | LLM writes environments as code. Each round is conditioned on how the trained policy performed, which yields a curriculum ([project](https://eureka-research.github.io/eurekaverse)) |
| OMNI-EPIC | ICLR 2025 (venue [PK] in one note) | LLM writes environment code and success detectors aimed at "not too easy, not too hard" tasks, with an interestingness filter against an archive ([arXiv](https://arxiv.org/abs/2405.15568)) |
| RoboTwin 2.0 | arXiv 2506.18088; PMLR version listed | Code agent plus a VLM observer with up to 5 repair rounds. Average of 1.76 rounds needed. The VLM observer reaches F1 of only 0.30 ([arXiv](https://arxiv.org/html/2506.18088v2)) |
| AnyTask | arXiv 2512.17853, preprint | Writes `check_success` *first* and then the rest. `reset()` is the dominant error. Drawer tasks: 0% of tasks reach >10% planner success ([arXiv](https://arxiv.org/html/2512.17853v2)) |
| RoboCasa | RSS 2024 [PK] | The closest MuJoCo prior: 100 tasks. LLMs propose the composite tasks, but humans implement them ([arXiv](https://arxiv.org/abs/2406.02523)) |
| Embodied-BenchForge | arXiv 2609.13082, abstract-only | Agentic benchmark synthesis with backward verification and rollback through an artifact dependency graph ([arXiv](https://arxiv.org/abs/2609.13082)) |

### Disagreements and open gaps
The field splits along five axes:
- **Context: raw source or compact API.** Eureka gives the LLM the raw environment source. Text2Reward gives it a hand-written compact abstraction.
- **Output: code or structured spec.** GenSim and AnyTask generate full task code. RoboGen generates structured scene configs plus reward code. GenSim2 has the model emit constraints, and a planner produces the motion.
- **Structure: top-down or bottom-up.** GenSim2's data favours bottom-up composition from the library.
- **LLM or procedural.** MimicGen [PK] scales data with no LLM at all ([arXiv](https://arxiv.org/abs/2310.17596)).
- **Repair budget.** RoboTwin 2.0 needs only 1.76 rounds on average. Eureka runs about five evolutionary rounds, and a third party reports roughly 10x the tokens per iteration of its own method ([arXiv 2410.14660](https://export.arxiv.org/pdf/2410.14660)).

No head-to-head study compares code-as-task with spec-as-task. No paper reports a duplicate rate or a principled novelty threshold. RoboGen's Self-BLEU table (0.284 vs GenSim's 0.378) is the only quantified diversity comparison ([RoboGen](https://arxiv.org/html/2311.01455v3)). Most important for this project: no paper measures how often a success function runs but is wrong.

### Design implications
The hybrid design wins on this evidence:
- The coding agent emits a small spec: objects from a fixed MuJoCo set, placement ranges, and a success predicate over sim state.
- Deterministic code builds the scene and samples placements.

The reasons are concrete. `reset()` and placement are AnyTask's main error source, and hallucinated assets are GenSim's first-listed implementation error.

Two practices transfer directly:
- **Success-check-first ordering (AnyTask).** Writing the check first constrains everything generated after it.
- **Bottom-up composition from accepted primitives (GenSim2).** This is the cheapest route to long-horizon difficulty.

The repair cap can be small (about 3). If one artifact proves wrong, regenerate only the artifacts downstream of it (BenchForge-style dependency tracking).

## Scene generation works when LLMs choose relations and solvers choose coordinates

### The common recipe
Scene-generation work converged on the same split. The LLM proposes semantics and relations, a solver computes coordinates, and physics validates the result. Raw LLM coordinates are the baseline everyone beats.

Holodeck's ablation makes the case. Absolute LLM coordinates scored an MRR of 0.364 on human layout preference, below random placement at 0.369. Constraint-based layout scored 0.706 ([Holodeck](https://arxiv.org/html/2312.09067v2)). Holodeck has GPT-4 emit relational constraints from 10 types (near, on top of, face to, and so on) and places objects with a DFS solver. It costs about $0.20 and 3 minutes per room on an M1 MacBook.

Tabletops are essentially a 2.5D problem. Even so, state-of-the-art tabletop generators still leave collisions: TabletopGen reports colliding objects in **7.69%** of its scenes after a pipeline of generated reference image → Hunyuan3D objects → pose alignment ([TabletopGen](https://arxiv.org/html/2512.01204)). On room-scale methods, a third-party preprint reports collision-free rates of only 77-84% (LayoutGPT 83.8, Holodeck 77.8, I-Design 76.8) ([arXiv 2604.16299](https://arxiv.org/pdf/2604.16299)). Its metrics differ from Holodeck's own, so cross-paper comparison is unsafe.

### Key papers

| System | Venue / status | One-line contribution |
|---|---|---|
| Holodeck | CVPR 2024 | Relational constraints plus a DFS/MILP solver. Retrieval score 100·CLIP + SBERT − 10·bbox mismatch. GPT-4V annotates 51k assets with size and mass ([arXiv](https://arxiv.org/html/2312.09067v2)) |
| LayoutVLM | CVPR 2025 | VLM produces initial numeric poses, then differentiable optimisation of collision, bounds and relation terms ([arXiv](https://arxiv.org/html/2412.02193v3)) |
| MesaTask | NeurIPS 2025 | Task instruction → tabletop via a "spatial reasoning chain". 10.7k-scene dataset, SFT + DPO ([arXiv](https://arxiv.org/abs/2509.22281)) |
| TabletopGen | arXiv 2512.01204, preprint | Image-guided generation: Hunyuan3D per object, scale anchored on an LLM-supplied size. Physics settle metrics. Warns that CLIP/LPIPS scores hide implausible layouts ([arXiv](https://arxiv.org/html/2512.01204)) |
| STABLE | ICML 2026 per arXiv comments, abstract-only | Fine-tuned semantic reasoner alternating with a flow-based "physics corrector" ([arXiv](https://arxiv.org/abs/2605.16137)) |
| ACDC | CoRL 2024 | "Digital cousins" from one image: on a real door-opening task, cousins reach 90% vs 25% for an exact twin (20 real trials) ([arXiv](https://arxiv.org/html/2410.07408v2)) |
| Articulate-Anything | ICLR 2025 | VLM actor-critic writes articulation code, raising success from about 9-12% to 75% ([arXiv](https://arxiv.org/html/2410.13882v4)) |
| SIMPLER | CoRL 2024 | For sim-based evaluation of real policies, visual matching gives the best real-sim correlation ([arXiv](https://arxiv.org/html/2405.05941v1)) |
| ProcTHOR, Infinigen Indoors, Architect, PhyScene, I-Design | NeurIPS 2022 / CVPR 2024 / NeurIPS 2024 / CVPR 2024 / ECCV-W 2024, all [PK] | Procedural, diffusion-guided and multi-agent alternatives ([ProcTHOR](https://arxiv.org/abs/2206.06994), [Infinigen](https://arxiv.org/abs/2406.11824)) |

### Disagreements and open gaps
Three representations compete:
- relational constraints with a discrete solver (Holodeck, MesaTask);
- numeric initialisation with physics refinement (LayoutVLM, STABLE);
- image-as-layout (Architect [PK], TabletopGen).

Retrieval and generation also compete. TabletopGen generates every object. Holodeck and ACDC retrieve from curated libraries.

Several things are unknown. No study measures how accurate LLM-guessed mass and friction are. Nothing reports agreement between VLM judges and humans on scene plausibility. No neutral benchmark compares simulators: ManiSkill3's parity claims and Genesis's speed claims come from interested parties ([ManiSkill3](https://arxiv.org/html/2410.00425v2); [Substack critique](https://stoneztao.substack.com/p/the-new-hyped-genesis-simulator-is)). A 2026 survey names "the gap between geometric quality and physical validity" as a field-level bottleneck ([arXiv 2604.26509](https://arxiv.org/abs/2604.26509)).

### Design implications
For a CPU-only MuJoCo tabletop:
- **Layout.** Have the LLM emit a scene graph (on / near / left-of / inside / stacked-on). Solve it with a rejection sampler on the table plane.
- **Physics gate.** Treat it as mandatory, and expect it to reject roughly 8-20% of samples, based on the published collision rates. Resample rather than repair.
- **Objects.** Prefer primitives and compound primitives. This removes the mesh failure class (scale errors, bad collision hulls).
- **Containers.** If bowls or bins use meshes, they need multi-hull decomposition. MuJoCo collides with the convex hull of a mesh, so a single-hull bowl is solid and "put X in the bowl" becomes physically impossible ([MuJoCo modeling docs](https://mujoco.readthedocs.io/en/stable/modeling.html)). The task will still pass a runnable check, which makes this a non-obvious failure.
- **Articulated objects.** Take them from existing libraries rather than generating them, since 75% generation success still means one in four is broken.
- **Simulator.** MuJoCo suits single-environment rollouts dominated by LLM latency. Isaac does not run on macOS, and GPU parallelism buys nothing here.

## Verification proves solvability but rarely rules out false credit

### The common recipe
The standard funnel is: code compiles → code runs → the generator's own oracle or planner solves the task → humans or a VLM review the output. GenSim uses a scripted demonstrator plus about 10 s of human review per task ([GenSim](https://arxiv.org/pdf/2310.01361)). GenSim2 uses a kPAM plus motion-planning solver ([GenSim2](https://arxiv.org/pdf/2410.03645)).

This funnel proves that a task can be solved. It says nothing about whether the success predicate is too loose. The notes found no generator paper that runs a **negative control**, i.e. checks that a no-op or random policy cannot succeed.

Agent benchmarks outside robotics show why that check matters:
- The Agentic Benchmark Checklist found that 7 of 10 popular benchmarks violate task validity and 7 violate outcome validity. In τ-bench, a trivial agent passes 38% of tasks ([ABC](https://arxiv.org/html/2507.02825v5)).
- OpenAI audited the SWE-bench Verified problems o3 failed to solve consistently and found **59.4%** with material flaws: 35.5% had narrow tests that reject correct fixes, and 18.8% had tests checking behaviour the task never asked for ([OpenAI](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)).

VLM judges are too weak to serve as the gate. RoboTwin 2.0's observer reached precision 0.208 and F1 0.302, and it hallucinated success on misaligned stacks ([RoboTwin 2.0](https://arxiv.org/html/2506.18088v2)).

### Difficulty calibration: the literature's optimum is 50%, not 5-30%
For binary rewards, the learning signal scales with p(1-p), which peaks at p = 0.5. The evidence:
- **Online Difficulty Filtering** (EACL 2026) proves policy improvement is lower-bounded by this variance. Keeping prompts with 0.25 ≤ p ≤ 0.75 gains about 10 points on AIME over plain GRPO ([arXiv](https://arxiv.org/html/2504.03380v2)).
- **DAPO** (NeurIPS 2025) keeps only prompts with 0 < correct < G (the group size) ([arXiv](https://arxiv.org/pdf/2503.14476v2)).
- **No Regrets / SFL** (NeurIPS 2024) scores levels by p(1-p) and argues that the regret proxies used by PLR, ACCEL and PAIRED are flawed in practice ([arXiv](https://arxiv.org/pdf/2408.15099)).
- **Absolute Zero** (NeurIPS 2025) rewards its proposer with 1 − p when 0 < p < 1 ([arXiv](https://arxiv.org/html/2505.03335v2)). A NeurIPS 2026 critique calls that reward under-determined, since tasks with equal failure rates can differ widely in teaching value ([NeurIPS 2026](https://neurips.cc/virtual/2026/172340)).

HUD's own guidance says a task is "often" hard at a pass rate of 50% or less. It adds that "one successful run in a handful of runs is noise", and that difficulty must come from the environment, not from stricter graders ([HUD](https://www.hud.ai/research/what-is-a-good-task)).

**No source endorses 5-30%.** It should be stated as a deliberate choice. For example, eval headroom for frontier models whose task difficulty decays over time would justify it. The cost is concrete: a task at p = 0.05 carries only 19% of the variance of a task at 0.5 (my computation).

### Difficulty knobs and success-predicate hygiene
COLOSSEUM (RSS 2024) adds perturbations to 20 RLBench tasks:
- Each perturbation factor costs 30-50% of success, and combined factors cost more than 75%.
- Distractors, colour and lighting hurt most; object size hurts least.
- Simulated drops correlate with real-robot drops (adjusted R² 0.614) ([arXiv](https://arxiv.org/html/2402.08191v2)).

ManiSkill counts success only within 2.5 cm *and* with the robot static ([ManiSkill2](https://arxiv.org/pdf/2302.04659)). ManiSkill-HAB defines "static" as arm joint velocity below 0.2 ([arXiv](https://arxiv.org/html/2412.13211v3)). The static requirement is a built-in anti-hacking dwell.

### Sample-efficient calibration
The literature uses a fixed number of rollouts G (8-16, or 64 for audits) and no sequential tests. Two papers suggest small models can pre-filter difficulty:
- Agent-RewardBench reports that "difficulty filtering by small models generalizes to other models" ([arXiv](https://arxiv.org/pdf/2506.21252)).
- Guru treats the strong-minus-weak pass-rate gap as a signal in its own right ([arXiv](https://arxiv.org/pdf/2506.14965)). If the gap carries information, it is not zero, so a cheap model cannot set the final p.

The binomial arithmetic is unforgiving (my computation, not sourced):
- At p = 0.15 and n = 10 the standard error is about 0.11, so 5% and 30% cannot be told apart.
- With 0 successes in n runs, the 95% upper bound is about 3/n (the rule of three).

### Disagreements and open gaps
- No paper compares difficulty bands for agentic or robotic tasks; all the evidence comes from math/code RLVR and grid worlds.
- No paper applies SPRT (sequential probability ratio testing) or Bayesian stopping to task calibration.
- No study measures how well difficulty correlates across models on embodied tasks.
- No source documents success-check leakage through robot tool outputs.

### Design implications
Run the funnel cheapest first:
1. The spec builds and the MJCF loads.
2. Physics settle for about 1 s. Reject on penetration, objects falling, or drift.
3. The success predicate is false at reset across N seeds.
4. **Negative controls:** no-op and random tool-call policies never succeed.
5. **Positive control:** a scripted oracle using the *same* `move_to` / `move_joints` tools succeeds in k of k runs.
6. Ideally a second, different oracle strategy also succeeds. This catches narrow graders, the SWE-bench failure.
7. Sequential calibration on a cheap model rejects the extremes: stop at 0 successes in about 8 runs, or 4+ in 8.
8. About 20-30 runs on the target model, only for tasks near the band edges.
9. Read all successes and a sample of failures.

Predicates should be relative to object extents and require release, low velocity and dwell. Keep the grader out of tool outputs. Pair the band reward with a novelty check so the generator cannot hit the band with near-duplicates or grader strictness. That is the Absolute Zero failure mode.

## Frontier models directly controlling arms reach 40-50% on suites, near zero on precision

### The interface ladder
Performance depends heavily on the interface. Anthropic's Embody study defines a ladder: direct control → programmatic → policy supervision → RL supervision. On Franka LIBERO-40 direct manipulation, Mythos Preview scored 5.5% and most other models scored 0%. Adding a cursor tool raised Mythos from 6% to 32% on a 10-task subset ([Anthropic](https://www.anthropic.com/research/claude-plays-robotics)).

URAI shows the value of keeping the model in the loop. With identical tools, a pre-written program reached 24% while agents deciding after each call reached 56% ([arXiv 2609.39018](https://arxiv.org/abs/2609.39018)).

The harness alone moves results as much as a model generation. JustRUA kept only the key harness components and raised RoboDojo sim score from 29.7 to 50.3 with no learned policy. The biggest levers were full episode history, stopping motions early, and providing scene geometry ([JustRUA](https://arxiv.org/abs/2611.16009), abstract-only).

### Benchmarks and numbers

| Benchmark | Venue / status | Setup and headline numbers |
|---|---|---|
| EmbodiedBench | ICML 2025 | Discretised 7-D action. Low-level manipulation is far below high-level tasks for every model: GPT-4o 28.9 vs 56.3 (ALFRED), Claude-3.5-Sonnet 25.4 vs 64.0. Removing vision costs 40-70% on low-level tasks only ([arXiv](https://arxiv.org/html/2502.09560v3)) |
| Bitter Lesson Comes to Robotics | arXiv 2610.25287, preprint | Real bimanual YAM arms, `move_to(x,y,z,yaw,pitch,roll,gripper)`, 40-action budget, 20 trials × 6 tasks. Best mean task scores 45-48%. Stand Up Bottles: 5/140 trials stood one bottle. Grasps closing on nothing: 32-64% depending on model ([arXiv](https://arxiv.org/html/2610.25287v1)) |
| LIBERO-10 frontier eval | arXiv 2610.30051, abstract-only | 18 configurations, 1,800 episodes, end-effector pose tool calls. GPT-6 Astra 44%, Gemini-4 Argon 43%. Weak on precise arrangement and multi-step tasks ([arXiv](https://arxiv.org/abs/2610.30051)) |
| RoboARCade | arXiv 2611.08209, abstract-only | Long-horizon MuJoCo tasks over 3 embodiments. Astra 49.8%, Claude Fable 5.1 43.6%. One in-context demo: 53.5% → 73.0%. False success claims on 24-39% of subtasks ([arXiv](https://arxiv.org/abs/2611.08209)) |
| Anthropic Embody | Lab blog, Jul 2026 | Images plus gripper force, never object coordinates. LIBERO-40 direct: 5.5% at best. G1 humanoid standing up: 0 successes for any model ([Anthropic](https://www.anthropic.com/research/claude-plays-robotics)) |
| RoboDojo / uni-robot-agent / LIBERO-Agent | arXiv 2607.04434 / 2611.01560 / 2609.39507, abstract or summary only | RoboDojo has 42 sim + 18 real tasks. uni-robot-agent shows a shared harness raises open models (Qwen3.8-Flash-Next 31.39 RoboDojo Score). LIBERO-Agent finds a "reliability gap" on hard short-horizon and long-horizon tasks ([RoboDojo](https://arxiv.org/abs/2607.04434); [uni-robot-agent](https://hyper.ai/en/papers/2611.01560); [LIBERO-Agent](https://arxiv.org/abs/2609.39507)) |
| Code as Policies, VoxPoser, ReKep, MOKA, PIVOT | ICRA 2023 / CoRL 2023 / CoRL 2024 / RSS 2024 / ICML 2024, all [recalled] | Older lineage that hides metric control behind planners, optimisers or visual selection. These measure semantic grounding, not control ([CaP](https://arxiv.org/abs/2209.07753); [ReKep](https://arxiv.org/abs/2409.01652); [PIVOT](https://arxiv.org/abs/2402.07872)) |

### Failure modes: what scale is fixing and what persists
RoboARCade reports that scene misunderstanding is now rare. Most failures are poor strategy or imprecise execution of a reasonable one ([RoboARCade](https://arxiv.org/abs/2611.08209)). In 2025, perception still caused 33% of GPT-4o's manipulation errors ([EmbodiedBench](https://arxiv.org/html/2502.09560v3)), so this is a real shift.

The Bitter Lesson study documents the mechanisms on a real arm ([Bitter Lesson](https://arxiv.org/html/2610.25287v1)):
- **Grasping nothing:** 32-64% of grasps close on empty air.
- **Inefficient correction:** Opus 5 needed about 6.7 actions to position the gripper.
- **Over-wide grasps:** 19% of grasps used an aperture of 0.1 or more.
- **Misread feedback:** weaker models read a thin-bowl pinch as an empty gripper and regrasped bowls they already held.
- **Irrecoverable errors:** knocking objects off the table, launching a pen lid out of reach.
- **Orientation near joint limits:** behind the 5/140 bottle result.

Anthropic adds three more ([Anthropic](https://www.anthropic.com/research/claude-plays-robotics)):
- Errors in spatial memory and self-localisation.
- Context rot.
- Regressions between model versions (Opus 4.7 scored 3% vs 15% for Opus 4.6 on one task).

Scale is clearly improving reaching, grasping and simple stacking. On Stack Bowls, four stronger models reached 70% or more while weaker ones stayed at 25% or less. The study's fitted throughput doubling time of 44.5 days rests on only 3 record points and is explicitly exploratory.

Some failures look persistent:
- fine alignment near joint limits;
- dynamic and reactive control, where models infer at about 0.2-0.4 Hz but a real-time Go2 robot needs about 83 Hz;
- honest termination;
- correctly interpreting scalar proprioception such as gripper width.

### Disagreements and open gaps
**Reasoning effort** gives mixed results:
- Anthropic found it regressed newer models on reactive control.
- The LIBERO-10 study found it generally helps.
- Astra at high effort with an extra configuration (H+UF) beat Astra at extra-high effort (XH) by 1.9 points.

**Headline numbers** are not comparable across papers. Subtask partial credit, RoboDojo Score and binary success are different metrics, and the harness alone moves scores by about 20 points.

**Unmeasured gaps.** HUD lists precise manipulation, articulated objects, tool use, affordances and physical common sense as under-tested ([rua.hud.ai](https://rua.hud.ai/blog/launch)). The notes found no direct evidence isolating Euler-angle errors, confusion between camera and world frames, or drawer/door handling under direct control. These are both gaps and opportunities. No controlled study compares `move_to`, `move_joints` and `move_by` for the same model and tasks.

### Design implications
The 5-30% band sits between "about 45% on suites" and "about 0-5% on precision tasks". This suggests task families in that band, each with a knob:

| Failure axis | Example task family | Difficulty knob |
|---|---|---|
| Metric localisation | Grasp small objects with no pose given | Object size, whether numeric poses are exposed |
| Orientation | Reorient or stand up objects | Required pitch/yaw, distance to joint limits |
| Grasp aperture | Grasp thin or flat objects | Object thickness |
| Correction efficiency | Tight-tolerance placement | Step budget |
| Proprioception | Ambiguous gripper readings | Gripper-reading ambiguity |
| Recoverability | Clutter, objects near table edges | Clutter density, edge distance |
| Self-verification | Visually subtle goals | Visual salience and occlusion of the goal |
| Long-horizon composition | Multi-stage tasks | Number of stages |
| Articulated objects | Drawers, doors, lids | Joint type, pull direction |
| Tool use | Reach with a stick or hook | Tool-target distance, tool shape |

Dynamic tasks are probably out of band.

Harness parameters must be part of every task record, and difficulty must be tuned on a fixed harness:
- views and overlays;
- numeric state in tool outputs;
- history window;
- step cap.

Overlays and geometry can quietly turn a precision task into a selection task. Record whether the agent declares `done` itself, and treat false `done` as its own metric.

## MuJoCo practice supplies a light, honest substrate

### The common recipe
Frameworks split an environment into four parts: a scene XML, an untouched robot from a curated source, freejoint objects, and Python task logic (sampler, action mapping, predicates).

MuJoCo Playground (arXiv 2502.08844) builds its Panda pick task from a small XML that includes a shared scene, plus named keyframes, with `pick.py` holding the logic ([Playground XML](https://github.com/google-deepmind/mujoco_playground/blob/main/rss2025/mujoco_playground/_src/manipulation/franka_emika_panda/xmls/mjx_single_cube.xml)).

`MjSpec` lets the scene be composed programmatically: load, add bodies, sites and cameras, then compile, with no XML string templating ([MuJoCo model editing](https://mujoco.readthedocs.io/en/stable/programming/modeledit.html)). A local benchmark run for this study confirmed it works unchanged on MuJoCo 4.0.1 with the Menagerie Panda.

Other frameworks build on MuJoCo with their own object models. VLABench (ICCV 2025) builds on dm_control with modular entities ([arXiv](https://arxiv.org/html/2412.18194v1)). LIBERO (NeurIPS 2023 D&B) defines success with BDDL predicates. Its `On` check passes when the two body origins are less than 3 cm apart in XY and the objects touch, regardless of object size, and its `Up` predicate uses an absolute world height of z ≥ 1.0 ([LIBERO predicates](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/master/libero/libero/envs/object_states/base_object_states.py)).

### Control and physics findings
mink provides QP-based differential IK with joint limits and Panda examples ([mink](https://github.com/kevinzakka/mink)). Menagerie's Panda has no end-effector site and uses position servos ([panda.xml](https://github.com/google-deepmind/mujoco_menagerie/blob/main/franka_emika_panda/panda.xml)). MetaWorld's mocap-weld control clips motion to a box ([MetaWorld](https://github.com/Farama-Foundation/Metaworld/blob/main/metaworld/sawyer_xyz_env.py)), so the arm can pass through infeasible poses and reachability failures stay hidden.

The local benchmark (an M1 Pro Mac, scratchpad `bench2.py`; not externally sourced) found:
- **IK speed:** mink converges in 1-4 iterations.
- **`move_to` cost:** 2-36 ms per call.
- **Sim speed:** about 67k steps/s.
- **Tracking error:** 4-7 mm at the end effector after settling.
- **Grasp stability:** a cube held with zero slip under default contacts.
- **Setpoint jumps:** commanding the IK solution as a single jump **dropped the grasped cube** during transport, while interpolating over 1-3 s kept it.

MuJoCo's documentation recommends elliptic friction cones plus a large impratio against slip ([modeling docs](https://mujoco.readthedocs.io/en/stable/modeling.html)). Locally this doubled the cost of contact-heavy steps. The default offscreen framebuffer is 640×480, and macOS renders through CGL ([gl_context.py](https://github.com/google-deepmind/mujoco/blob/main/python/mujoco/rendering/classic/gl_context.py)).

### Disagreements and open gaps
How heavy should the composition layer be? robosuite, LIBERO and RoboCasa merge their own XML object models. The DeepMind-side code (Playground, Menagerie) uses small XML plus `MjSpec`. No one has measured `MjSpec` against templating head to head.

Weld-on-grasp is a common shortcut, but it makes grasp quality untestable. The notes found no authoritative list of which benchmarks use it. The root cause of the 4-7 mm residual is unisolated. Container rendering speed with osmesa or EGL is unmeasured.

### Design implications
**Robot.** Load Menagerie's Panda untouched via `MjSpec` and add a `tcp` site. Rebuild keyframes by joint name, because adding freejoint objects breaks the length of the stored keyframe vectors.

**`move_to`.** Implement it as:
1. mink IK with configuration limits.
2. Report "unreachable" when the residual exceeds tolerance, and never silently snap to the nearest pose.
3. Interpolate joint targets.
4. Step until settled.
5. Return the achieved pose.

Mocap control is rejected because it hides exactly the reachability failures a robot-use-agent benchmark should expose.

**Tolerances.** Keep success tolerances above the measured 4-7 mm tracking error, or the grader will reject correct solutions.

**Speed.** Physics and rendering cost under 3 s per 70-step rollout, so LLM latency dominates cost and parallel processes on the Mac are viable.

**Rendering.** Render only at observation time, at 256×256 or 320×240.

## Conclusion

The literature's generators and its robot-use-agent benchmarks barely touch. Generators optimise for policy training data, and verify solvability through a planner the agent never uses. Benchmarks repackage LIBERO and RoboDojo tasks and discover, after the fact, that harness choices move scores by 20 points. The open niche is a generator whose fitness signal is the LLM agent's own pass rate, measured through the same `move_to` / `move_joints` / `move_by` tools the oracle used. That is Eurekaverse/OMNI-EPIC-style difficulty feedback applied to tool-call control. This reframes what "verified" must mean. Solvability through the agent's own interface is the positive control. Failure of no-op and random policies is the negative control. Dwell, release and extent-relative predicates guard against false credit. A VLM serves only as a smell test, given an F1 around 0.30.

Two non-obvious risks follow. The first is the 5-30% band. It sits well below the p(1-p) optimum, so it costs signal per rollout and needs sequential, model-pinned estimation; n = 10 cannot separate 5% from 30%. A generator rewarded only for hitting the band will learn to hit it with tight tolerances and near-duplicates, unless difficulty is forced into environment-side knobs and diversity is checked. The second is the capability profile. Its most defensible axes are the ones current benchmarks leave unmeasured: orientation near joint limits, proprioceptive interpretation, articulated objects, tool use and honest termination. Each maps to a scene knob the pipeline can turn. Because difficulty expires (HUD) and models regress as well as improve, every pass rate should carry its model, harness, step cap and n, and the bank should be re-calibrated whenever the target model changes.
