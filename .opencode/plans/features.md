# Features

1. [V] GitHub fork
2. [V] Accept HuggingFace sources (see hf-sources-plan.md)
3. [ ] Increase recursion, tool use, smartness
4. [ ] Deploy to GCP!!
5. [ ] Create JIRA tickets for ODH
6. [ ] Human in the loop
7. [ ] Include tests output in the report, or at least as some kind of an appendix
8. [V] OGX LLM Proxy for PoC projects (see ogx-llm-proxy-plan.md)
9. [ ] Blog post generation from PoC results (see blog-post-plan.md)

## Deeper dive

### Accept HuggingFace sources
In terms of things we'd like to PoC, this is great. In terms of GitHub fork, does it work? is it desireable? do we want to say that for Models the PoC flow is different?
How do models look like in ODH/OpenShiftAI ?

### Deploy to GCP

We'll have a VM running on GCP, do we create TF files for that? How do we deploy? How do we keep secrets? We probably need a systemd service, a container, or some other thing to keep this boy running in the background or something.

### Human in the loop

I'd like to have at least three modes of human in the loop, ideally when we run the CLI we'll choose
1. Fully automated. No human input is needed except for maybe run the CLI in the first place
2. **default** Big picture. Human approves the plan and maybe the report
3. Micro manager. Approve plan, approve final Dockerfile.ubi, kubernetes, report.
