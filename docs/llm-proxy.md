# LLM Proxy for PoC Projects

Many projects require API keys to LLM providers (OpenAI, Anthropic). Handing real keys to arbitrary third-party code is a security risk. AutoPoC solves this with an **OGX server** (formerly LlamaStack) that acts as an OpenAI-compatible proxy.

```
PoC App  -->  OGX Server  -->  vLLM (Qwen3-32B)
              (ogx namespace)   (vllm namespace)
```

When `OGX_BASE_URL` is configured:

1. **PoC Plan** detects that a project needs LLM API access (e.g., imports `openai`, expects `OPENAI_API_KEY`)
2. **Deploy** automatically substitutes `OPENAI_API_KEY=none` and `OPENAI_BASE_URL=<ogx-url>` in the generated manifests
3. The PoC app calls the OGX server, which routes to your vLLM backend -- no real API keys involved

## Deploying OGX

```bash
# Build the OGX container image (UBI9-based)
make ogx-image

# Push to registry
make ogx-image-push

# Deploy to cluster
kubectl apply -f deploy/lab/ogx.yaml
```

OGX runs in its own namespace (`ogx`) with a ConfigMap-driven config. Model aliases (gpt-4, gpt-4o, gpt-3.5-turbo) are pre-configured to route to Qwen3-32B. Adding real OpenAI/Anthropic providers later is a ConfigMap edit -- no AutoPoC code changes needed.

See [ADR 0006](adr/0006-ogx-llm-proxy.md) for the design rationale.
