---
name: langgraph-architecture
description: >-
  Design and implement LangGraph agents and workflows using StateGraph,
  typed state, small single-purpose nodes, conditional edges, and structured
  outputs. Use when creating LangGraph agents, workflows, graphs, nodes,
  edges, or when the user mentions LangGraph architecture.
---

# LangGraph Architecture

## Rules

- Prefer StateGraph.
- Use TypedDict or Pydantic state.
- Keep nodes small.
- One responsibility per node.
- Avoid giant monolithic agents.
- Use conditional edges instead of nested if statements.
- Preserve graph readability.
- Separate prompts from implementation.
- Never hardcode model names inside nodes.
- Return structured outputs whenever possible.

## Project layout

```
state.py              # TypedDict or Pydantic state schema
graph.py / app.py     # Graph wiring only — no business logic
agents/               # One module per node
prompts/              # Prompt templates (optional but preferred)
```

Graph files declare nodes and edges. Node modules implement behavior. Prompts live outside nodes.

## State

Use `TypedDict` for simple string-heavy state; use Pydantic `BaseModel` when validation or nested objects are needed.

```python
from typing import TypedDict

class AgentState(TypedDict, total=False):
    question: str
    context: str
    analysis: str
    final_decision: str
```

Nodes return partial state updates — only the keys they own.

## Graph wiring

Keep the graph readable: named nodes, explicit edges, routing in one place.

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(AgentState)

builder.add_node("analyze", analyze_node)
builder.add_node("review", review_node)
builder.add_node("decide", decide_node)

builder.add_edge(START, "analyze")
builder.add_edge("analyze", "review")
builder.add_edge("review", "decide")
builder.add_edge("decide", END)

graph = builder.compile()
```

Use `add_conditional_edges` for branching — not `if` chains inside nodes.

```python
def route_after_review(state: AgentState) -> str:
    if state.get("needs_revision"):
        return "analyze"
    return "decide"

builder.add_conditional_edges("review", route_after_review, {
    "analyze": "analyze",
    "decide": "decide",
})
```

## Node design

Each node: read state → call LLM or tool → return partial update.

```python
# agents/analyze_node.py
from prompts.analyze import ANALYZE_PROMPT
from llm import get_llm

def analyze_node(state: AgentState) -> dict:
    llm = get_llm()
    prompt = ANALYZE_PROMPT.format(
        question=state.get("question", ""),
        context=state.get("context", ""),
    )
    response = llm.invoke(prompt)
    return {"analysis": response.content}
```

**Do not** embed prompts or model names in nodes. Inject LLM via factory or module-level config.

## Model configuration

Define models once, outside nodes:

```python
# llm.py
from langchain_ollama import ChatOllama

def get_llm(model_name: str, temperature: float = 0.2):
    return ChatOllama(
        model=model_name,
        temperature=temperature,
    )
```

## Structured outputs

Prefer structured responses over free-form strings when downstream nodes consume the output.

```python
from pydantic import BaseModel, Field

class Decision(BaseModel):
    action: str = Field(description="BUY, SELL, WAIT, STRONG_BUY, or STRONG_SELL")
    confidence: int = Field(ge=0, le=100)
    reasoning: str

llm = get_llm().with_structured_output(Decision)
result: Decision = llm.invoke(prompt)
return {"final_decision": result.model_dump()}
```

## Anti-patterns

| Avoid | Prefer |
|-------|--------|
| One 200-line node doing fetch + analyze + decide | Separate nodes per step |
| `if/elif` routing inside a node | `add_conditional_edges` + router function |
| Inline prompt strings in node functions | `prompts/` module or template constants |
| `ChatOllama(model="...")` inside every node | Shared `get_llm()` factory |
| Returning raw `response.content` for structured data | Pydantic `with_structured_output` |
| Graph logic mixed with RAG or API calls | Pre-graph setup; nodes receive prepared state |

## Multi-Agent Pattern

When multiple agents exist:

- Technical Agent performs indicator analysis.
- Risk Agent evaluates risk.
- News Agent evaluates external events.
- Debate Agent reconciles disagreements.
- Supervisor Agent produces the final decision.

No agent should duplicate responsibilities.
Supervisor Agent is the only node allowed to create the final recommendation.

## Checklist

Before finishing a graph change:

- [ ] State schema defined in `state.py`
- [ ] Graph file contains only wiring
- [ ] Each node has one clear responsibility
- [ ] Prompts separated from node implementation
- [ ] Model names configured outside nodes
- [ ] Branching uses conditional edges
- [ ] Outputs are typed or structured where consumed downstream
