# PoC Plan Generation Instructions

Generate a PoC plan that answers: "What would prove this project works on OpenShift AI?"

## Project Classification

Classify into one of these types:

| Type | Description | Example |
|---|---|---|
| `model-serving` | Trained ML model needing an inference endpoint | PyTorch + FastAPI |
| `rag` | Retrieval-augmented generation pipeline | LangChain + ChromaDB |
| `training` | Model training or fine-tuning job | Training script + dataset |
| `data-pipeline` | ETL, feature engineering, data processing | Spark, Airflow |
| `notebook` | Jupyter notebook exploration | .ipynb files |
| `web-app` | Web application (possibly with ML features) | Flask, React |
| `api-service` | Backend API service | FastAPI, Express |
| `infrastructure` | Operator, controller, library, SDK | Python package |
| `llm-app` | LLM-based application (chatbot, agent, summarizer) | LangChain agent |

## Infrastructure Requirements

Determine for the PoC plan:

### Deployment Model (CRITICAL)

| Application Type | deployment_model | listens_on_port |
|---|---|---|
| Web server, API server, inference server | `deployment` | `true` |
| Message queue consumer, watcher | `deployment` | `false` |
| CLI tool, library, SDK | `job` | `false` |
| Batch processing, training, data pipeline | `job` | `false` |
| Scheduled task | `cronjob` | `false` |

**Getting this wrong causes CrashLoopBackOff** (deploying CLI tools as Deployments) or missing Services.

### Resource Profile

| Profile | Use For |
|---|---|
| `small` | Web apps, simple APIs: 256Mi RAM, 250m CPU |
| `medium` | ML inference (CPU), data processing: 1Gi RAM, 500m CPU |
| `large` | Large model inference, training: 4Gi RAM, 2 CPU |
| `gpu` | GPU-accelerated workloads: 8Gi RAM, 4 CPU, 1 GPU |

### LLM API Detection

Check if the project calls external LLM APIs:

| Pattern | Detection |
|---|---|
| `openai` | `import openai`, `OPENAI_API_KEY` in env/config |
| `anthropic` | `import anthropic`, `ANTHROPIC_API_KEY` |
| `langchain` | `from langchain_openai import ChatOpenAI`, `from langchain_anthropic import ...` |
| `custom` | Direct HTTP calls to `/v1/chat/completions` |

Set `needs_llm_api: true` and the correct `llm_env_pattern` if detected.

## Test Scenarios

Define 2-5 concrete, automatable test scenarios:

### HTTP Tests (for services with ports)
```yaml
- name: "health-check"
  type: "http"
  endpoint: "/health"
  expected_behavior: "Returns 200 OK"
  timeout_seconds: 30
```

### CLI Tests (for tools/libraries)
```yaml
- name: "help-output"
  type: "cli"
  input_data: "tool-name --help"
  expected_behavior: "Exits 0, shows usage info"
  timeout_seconds: 15
```

## Output Format

### poc-plan.md Structure

```markdown
# PoC Plan: {project_name}

## Project Classification
- **Type:** {poc_type}
- **Key Technologies:** {list}
- **ODH Relevance:** {why relevant}

## PoC Objectives
1. {objective 1}
2. {objective 2}

## Infrastructure Requirements
- **Resource Profile:** {small/medium/large/gpu}
- **GPU Required:** {yes/no}
- **Persistent Storage:** {size or none}
- **Sidecar Containers:** {list or none}

## Test Scenarios
### Scenario 1: {name}
- **Description:** {what this tests}
- **Type:** {http/cli}
- **Input:** {sample input}
- **Expected:** {success criteria}
- **Timeout:** {seconds}

## Dockerfile Considerations
{Instructions for containerize phase}

## Deployment Considerations
{Instructions for deploy phase - deployment model, Service creation, test method}
```

### Structured Data for State File

After writing poc-plan.md, update the state with structured data:
- `poc_type`
- `poc_components` (which components to containerize)
- `scenarios` array
- `infrastructure` object with all fields
