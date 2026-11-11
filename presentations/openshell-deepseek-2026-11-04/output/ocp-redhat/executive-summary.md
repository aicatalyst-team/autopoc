# OpenShell executive summary

Run: ac05c639abd848998db29ce2352d9a0f

Report: archived report.md in render-inputs.zip → evidence.zip.


## Repository purpose


- OpenShell is NVIDIA's policy-governed runtime for fleets of autonomous AI agents. (Evidence: report.md)

- This PoC tested whether its gateway, shared supervisor, and sandbox run on OpenShift under restricted-v2 with block storage. (Evidence: report.md, plan.md)


## Testing strategy


- Five original scenarios covered gateway health, process execution, workspace persistence, and network allow/deny against a reachable control. (Evidence: plan.md)

- The denial was an expected policy outcome, measured with supervisor OCSF events; CNI, OIDC, HA, and load were excluded. (Evidence: report.md, plan.md)


## Test execution


- The final original execution passed 5 of 5 scenarios; an earlier harness-only attempt is retained in the evidence. (Evidence: test-results.json, attempt-index.json)

- All three images were source-built with UBI; build times were 38m47s, 19m18s, and 13m27s with no build retries. (Evidence: report.md, state.json)


## OpenShift and Kubernetes suitability


- Gateway and sandbox workloads ran on the eu-gb-2 worker with 10Gi IBM block claims; restricted-v2 needed no privileged SCC. (Evidence: report.md, state.json)

- Tested compatibility is limited to this single-replica PoC; Kubernetes portability beyond it is inferred, not proven. (Evidence: report.md)


## Limitations


- Single replica; no OIDC, HA, load, failover, filesystem, or wider-portability validation.

- Network denial is supervisor/proxy mediation; CNI enforcement was not independently tested.

- Google durable publication is blocked; no cloud links exist.

- [Source](executable-source.zip) — generated, unpublished.

- [Deck](static-site.zip) — generated, unpublished.

- [Pdf](executive-summary.pdf) — generated, unpublished.

- [Video](executive-summary.mp4) — generated, unpublished.

- Silent video; animation timing is illustrative. No live tests were replayed.
