# Pipeline diagram (draft, for deliverable 2)

```mermaid
flowchart LR
    I[Intent<br/>one line of text<br/>or a tabletop photo] --> G[Generator<br/>LLM writes YAML only<br/>docs/generator_prompt.md]
    C[Capability profile<br/>+ existing tasks] -.-> G
    G -->|spec| S[Task spec<br/>objects · ranges · success<br/>oracle · knobs · variants]
    S --> F{Free gates<br/>schema · prompt · settle · joints<br/>reach · visible · trivial<br/>oracle · robust · oracle via real tool}
    F -->|fail + exact reason| G
    F -->|pass| H[Human approval<br/>review sheet]
    H --> P{Calibrate on the target model<br/>flags: step cap · jammed · near budget}
    P -->|too easy / too hard| G
    P -->|in band| T[Trace review + replay<br/>harness or model?]
    T -->|model| L[(Task library)]
    T -->|harness: fix + new free check| K[Harness + truth test<br/>15 checks]
    K -.->|replay recorded successes<br/>before any paid rerun| F
    L -.->|updates| C
```

- Everything left of "Calibrate" is free and caught most problems (weak grip, jammed drawer, precision cliffs, grading crash).
- Calibration only measures difficulty. A low score is not read as capability until the flags are zero and a replay shows the failure is the model's.
- Every harness fault found becomes a free check, so the discriminator tightens over time; replay of recorded episodes is the regression test for the harness itself.
