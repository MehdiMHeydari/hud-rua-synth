# Pipeline diagram (draft, for deliverable 2)

```mermaid
flowchart LR
    I[Intent<br/>e.g. "test chaining"] --> G[Generator<br/>coding agent<br/>docs/generator_prompt.md]
    G -->|writes| S[Task spec YAML<br/>objects · ranges · success · oracle · knobs]
    S --> F{Free gates<br/>schema · settle · joints · reach<br/>trivial · oracle · robust<br/>oracle via real tool}
    F -->|fail + reason| G
    F -->|pass| P{Paid gates<br/>strong model on easy setting<br/>calibrate knob on sol, n≥20}
    P -->|too easy / too hard| G
    P -->|5–30%| L[(Task library)]
    P -.->|trace review| R[Harness fault?]
    R -->|yes: fix + new check| H[Harness + truth test]
    H -.-> F
```

- Free gates and the truth test cost $0 and caught most problems (weak grip, jammed drawer, precision cliffs, grading crash).
- Paid gates only measure difficulty; any harness fault found in traces becomes a new free check, so the discriminator tightens over time.
