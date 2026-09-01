---
name: multi-agent-debate-pattern
description: >-
  Coordinate multiple specialized agents with clear responsibilities.
  Use when creating debate or supervisor workflows.
---

# Multi-Agent Debate Pattern

## Rules

- Agents must have distinct responsibilities.
- Avoid duplicated analysis.
- Technical Agent performs indicator analysis.
- Risk Agent evaluates risk.
- News Agent evaluates external events.
- Debate Agent reconciles disagreements.
- Supervisor Agent produces the final recommendation.
- Only the Supervisor Agent can emit final decisions.
- Preserve explainability.
- Prefer structured outputs.