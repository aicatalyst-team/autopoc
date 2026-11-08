## NVIDIA OpenShell agent sandbox on OpenShift AI

**A 5-scenario proof of concept (PoC) under restricted-v2**

An agent sandbox that says no is more useful than one that only says hello. We deployed NVIDIA OpenShell on Red Hat OpenShift AI because platform teams keep asking whether an agent runtime can be bounded without giving it a privileged node. The PoC shows that OpenShell's gateway, supervisor, and sandbox run under restricted-v2, and that a denied request leaves supervisor policy evidence a platform engineer can operate on. **Start here:** explore [Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai), then read the [PoC report](https://github.com/aicatalyst-team/openshell/tree/autopoc-artifacts/runs/ac05c639abd848998db29ce2352d9a0f) for the evidence chain.

--------------------
**[Image Placeholder 1: The policy boundary at a glance]**

**Alt text**: A restricted-v2 namespace with a gateway, supervisor, and 3 sandbox pods, where a policy proxy allows one outbound path and denies another.

--------------------

## What NVIDIA OpenShell adds to an agent platform

OpenShell is a runtime for autonomous AI agents. Its job is to decide what an agent may do. A gateway provisions sandboxes. A trusted supervisor mediates filesystem, process, and network policy. On Kubernetes, the gateway creates an agent sandbox resource, a supervisor Pod, workload Pods, Services, NetworkPolicies, and a workspace PVC.

We used OpenShift AI as the platform, but this PoC exercised the Kubernetes, storage, and namespace surface rather than model serving or GPU features. The supported Kubernetes environment, storage classes, and console view were enough to verify readiness. OpenShell puts the policy decisions in a control plane instead of application code. At the pinned revision, the project is a Rust workspace with 41 crates, plus Python and Go SDKs and Helm charts, according to its Cargo manifest. That source was our only build input.

<div class="mermaid" role="img" aria-label="A validation client calls the gateway, which starts sandbox pods and talks to a shared supervisor. Sandbox traffic reaches a policy proxy that allows example.com and denies api.github.com inside a restricted-v2 namespace with workspace PVCs and NetworkPolicy.">
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#EE0000', 'primaryTextColor': '#ffffff', 'primaryBorderColor': '#A30000', 'lineColor': '#6A6E73', 'secondaryColor': '#F0F0F0', 'tertiaryColor': '#0066CC'}}}%%
graph TD
    SDK[Validation client] --> GW[Gateway StatefulSet]
    GW --> SUP[Shared supervisor]
    GW --> SB[Sandbox pods]
    SB --> PVC[10Gi workspace claims]
    SB --> PROXY[Policy proxy]
    PROXY --> ALLOW[example.com allowed]
    PROXY --> DENY[api.github.com denied]
    subgraph NS[poc-openshell-deepseek: restricted-v2, NetworkPolicy]
        GW
        SUP
        SB
        PVC
        PROXY
    end
</div>

*Figure 1: The tested control path.*

## Build and deploy path

### Build the images from source

We did not reuse a prebuilt core image. We built all 3 components from the pinned source with UBI based Dockerfiles and OpenShift binary BuildConfigs. The images went to Red Hat Quay with one new tag, deepseek-ac05c639, while existing tags stayed untouched.

| Component | Build time | Result |
|---|---:|---|
| Gateway | 38m47s | Pushed |
| Supervisor | 19m18s | Pushed |
| Sandbox | 13m27s | Pushed |

All 3 builds succeeded on the first attempt. The gateway took the longest because the Rust build is large. Plan for a long, memory-heavy gateway build: we chose 2 CPU and 4Gi of requests, with limits at 4 CPU and 16Gi, and smaller requests for the other 2 components. Those are chosen requests and limits, not observed peaks. No build retries were needed. The operator supplied compiled reference Dockerfiles and prior run lessons, and we reused them unchanged except for provenance comments. That is operator assistance, not a run result.

### Deploy the chart on OpenShift

We deployed with the project Helm chart into namespace poc-openshell-deepseek. The gateway ran as a 1-replica StatefulSet. The supervisor ran as a 1-replica Deployment with a PodDisruptionBudget. Both ran under the restricted-v2 Security Context Constraint (SCC), as non-root, with no added capabilities and no privileged or anyuid SCC. The report records the Pod security context and the namespace SCC binding we checked with kubectl.

Storage was IBM block storage with 10Gi claims. The gateway claim bound, and sandbox workspace claims attached on the same worker as the sandbox pods. We pinned gateway and sandbox placement to worker 2 in eu-gb-2, an operator preconfiguration informed by an earlier storage failure. The chart created namespace-scoped RBAC only.

The first Helm install with the wait flag created the release resources, but its wait step failed because the runner ServiceAccount could not list replicasets. We reconciled with a normal install or upgrade and checked objects with kubectl. That was a runner RBAC limit, not a product failure. The supervisor also retried its gateway assignment stream briefly while a token Secret propagated, then stayed attached.

```bash
helm upgrade --install openshell deploy/helm/openshell \
  --namespace poc-openshell-deepseek \
  -f kubernetes/values-openshell-deepseek.yaml
kubectl get statefulset,deployment,pvc -n poc-openshell-deepseek
```

## Scenarios and results

The final original execution, a23ddad8e73849acb7f3bf68b8e09c18, recorded **5 pass, 0 fail, 0 error, 0 skip, and 0 incomplete**. The test script, poc_test.py, uses the OpenShell Python SDK over a port-forward. It creates a node-pinned sandbox, runs commands, stops and starts the sandbox, then runs the 2 network scenarios. The script records every attempt in attempt-index.json, so the final execution sits next to the harness failure instead of replacing it.

| Scenario | What we checked | Result |
|---|---|---|
| Gateway health | /healthz returned HTTP 200 | Pass |
| Sandbox process execution | Sandbox reached READY, uname -s returned Linux, id -u was non-zero, and a marker printed | Pass |
| Workspace persistence | /sandbox/poc-marker survived stop and start unchanged | Pass |
| Network allow control | curl https://example.com returned HTTP 200 | Pass |
| Supervisor policy denial | curl https://api.github.com/zen was refused with supervisor policy evidence | Pass |

The sandbox scenarios used real commands and a real workspace. The persistence check stopped and started the sandbox, then compared the marker. The network checks used a reachable destination so a timeout would not be mistaken for a deny. Health proves the API is up. Execution and persistence prove the sandbox is real. Allow proves the control path works. Deny proves the policy path works. For platform guidance, see [Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai). The [full report](https://github.com/aicatalyst-team/openshell/tree/autopoc-artifacts/runs/ac05c639abd848998db29ce2352d9a0f) has the evidence chain.

An earlier execution, 7ca2d78ea463425985e900083da09a4f, is retained in the attempt index. It passed health, then errored before creating any sandbox because our harness used a 20-character template name and the gateway limit is 19 characters. We fixed the harness name to deepseek-nodepin and reran. No product code was changed to bypass a failure. We would rather keep a failed attempt in the record than pretend the first run was clean.

### Why a denied request was the right result

The fifth scenario is easy to misread as a failure. We asked the sandbox to reach api.github.com. A plain UBI Pod in the same namespace had already reached example.com, api.github.com, and pypi.org with HTTP 200, so the destination was reachable on the ordinary network path. OpenShell refused the sandbox request. The client scenario passed with a policy denial, not a timeout, and the supervisor recorded an Open Cybersecurity Schema Framework (OCSF) deny for /usr/bin/curl to api.github.com:443 with transparent_tcp_policy_denied. Open Policy Agent (OPA) is the policy engine, and the reason field identifies the transparent TCP policy path that refused the connection.

```text
OCSF NET:OPEN  [INFO] ALLOWED /usr/bin/curl(0) -> example.com:443 [policy:allow_example engine:opa]
OCSF NET:OPEN  [MED]  DENIED  /usr/bin/curl(0) -> api.github.com:443 [reason:transparent_tcp_policy_denied]
```

The refusal was the expected outcome, and the supervisor line shows why. It also sets a boundary: this is OpenShell supervisor and proxy mediation, not an independent test of Kubernetes NetworkPolicy enforcement by the Container Network Interface (CNI). The chart creates NetworkPolicy objects, but we did not prove CNI enforcement in this run. For the platform view of that boundary, see the [Red Hat OpenShift AI documentation](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed).

<div class="mermaid" role="img" aria-label="A validation client starts a sandbox through the gateway. One request through the policy proxy to example.com returns 200. A second request to api.github.com is denied with a policy event.">
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#EE0000', 'primaryTextColor': '#ffffff', 'primaryBorderColor': '#A30000', 'lineColor': '#6A6E73', 'secondaryColor': '#F0F0F0', 'tertiaryColor': '#0066CC'}}}%%
sequenceDiagram
    participant C as Validation client
    participant G as Gateway
    participant S as Sandbox
    participant P as Policy proxy
    C->>G: start sandbox
    G->>S: provision workload
    S->>P: curl https://example.com
    P-->>S: 200 allowed
    S->>P: curl https://api.github.com/zen
    P-->>S: denied with policy event
</div>

*Figure 2: Allow and deny in one sandbox.*

## Lessons and limits

The first run taught us more than the clean one. The control plane and sandbox lifecycle were the interesting part, not the health endpoint. A gateway that answers /healthz is table stakes. A sandbox that runs a command, keeps a file across a restart, and produces a policy record is a better signal. The harness also has to match product limits: a 20-character template name looked harmless until the gateway rejected it. Keep application policy and cluster policy separate in the report, because it is easy to say the network was locked down and mean several different mechanisms.

The biggest gap is identity. We used client certificates and a development principal, not OpenID Connect (OIDC) or multi-user authorization. We also did not test high availability, failover, load, filesystem isolation, or wider Kubernetes portability, and we did not run an independent CNI enforcement test. Those are the next tests, not claims. Health checks do not certify production security.

For related Red Hat platform reading, see the [Red Hat OpenShift AI blog](https://www.redhat.com/en/blog) and the [Red Hat AI topic page](https://www.redhat.com/en/topics/ai).

## Reproduce it

The source is [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) at commit f4a6137. Our values, validation script, report, and artifacts live in the fork aicatalyst-team/openshell under the autopoc-deepseek-20261104-ac05c639 branch and append-only run paths.

Read the [PoC report](https://github.com/aicatalyst-team/openshell/tree/autopoc-artifacts/runs/ac05c639abd848998db29ce2352d9a0f), then try the same 5 scenarios on your own project. Try one deny scenario this week: start the gateway, create a sandbox, allow example.com, deny a second reachable host, and read the supervisor event. If you are planning agent workloads on [Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai), that single test tells you more than a health check ever will.
