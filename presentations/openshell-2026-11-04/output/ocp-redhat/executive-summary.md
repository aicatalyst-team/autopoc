# OpenShell executive summary

Run: a189bdf54ac849778a8ed7b228db599f

Report: archived report.md in render-inputs.zip → evidence.zip.


## Repository purpose


- NVIDIA OpenShell is designed to isolate AI agent workloads with kernel and network policies. (Evidence: report.md, evaluation.md)

- Build three Rust runtime components as UBI9 images and test control-plane access and sandbox behavior on OpenShift. (Evidence: report.md)


## Testing strategy


- Five planned checks cover health, metrics, mTLS API, sandbox lifecycle and network policy. (Evidence: plan.md)

- A reachable out-of-policy control was added to the harness; its scenario remained skipped. Filesystem policy was not tested. (Evidence: report.md)


## Test execution


- Final capture: 3 pass, 1 error, 1 skip. Health, metrics and mTLS Health/list passed; prior attempts remain in history. (Evidence: test-results.json, attempt-index.json)

- Sandbox readiness timed out after 240s with an IBM disk-attachment quota. Network-policy validation was skipped. (Evidence: report.md, test-results.json)


## OpenShift and Kubernetes suitability


- Gateway and supervisor ran on OpenShift 4.21.8 under restricted-v2. All three images were source-built with documented patches. (Evidence: report.md)

- Operators assisted the build, RBAC and same-zone placement. Security, HA and wider Kubernetes portability remain unverified. (Evidence: report.md)


## Limitations


- No network/filesystem isolation, CNI, load/HA or wider Kubernetes portability validation.

- mTLS used a local-dev principal; production OIDC was not tested.

- Storage blocked sandbox validation. Operator-assisted PoC; production readiness is unproven.

- [Source](executable-source.zip) — generated, unpublished.

- [Deck](static-site.zip) — generated, unpublished.

- [Pdf](executive-summary.pdf) — generated, unpublished.

- [Video](executive-summary.mp4) — generated, unpublished.

- Silent video; animation timing is illustrative. No live tests were replayed.
