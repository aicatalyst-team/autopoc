# Pre-filter Heuristic Scoring

Score candidates without LLM calls or cloning, using only sheet metadata.

## Category Score (0-30)

| Category Keywords | Score |
|---|---|
| model-serving, inference, serving | 30 |
| rag, retrieval, vector, embedding | 28 |
| llm, chatbot, agent, agentic | 25 |
| training, fine-tuning, fine-tune | 22 |
| ml, machine-learning, deep-learning | 20 |
| data-pipeline, etl, feature-engineering | 15 |
| notebook, jupyter | 12 |
| web-app, api, microservice | 10 |
| infrastructure, operator, library | 8 |
| other / unclassified | 5 |

Match is case-insensitive against the `category` column. Use the highest matching score.

## Title Keyword Score (0-20)

Search the `title` field for these keywords (case-insensitive):

| Keywords | Score |
|---|---|
| vllm, triton, kserve, modelmesh, tgi | +5 |
| langchain, llamaindex, chromadb, qdrant | +4 |
| pytorch, tensorflow, transformers, huggingface | +4 |
| openshift, kubernetes, k8s, docker | +3 |
| fastapi, flask, express, gradio, streamlit | +2 |

Sum all matches, cap at 20.

## PM Signal (0-10)

If PM comments column exists:
- Explicit approval terms ("must have", "priority", "critical", "important"): +10
- General approval ("approve", "yes", "good"): +5
- Neutral or no comment: 0
- Negative ("skip", "defer", "low priority"): -5

## Final Heuristic Score

```
score = category_score + title_keyword_score + pm_signal
```

Range: -5 to 60. Higher is better.
