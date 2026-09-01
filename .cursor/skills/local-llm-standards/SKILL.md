---
name: local-llm-standards
description: >-
  Configure LLM access using shared wrappers and prefer local inference.
  Use when adding Ollama, vLLM, OpenAI, or NIM integrations.
---

# Local LLM Standards

## Rules

- Prefer local inference first.
- Avoid paid APIs unless explicitly requested.
- Reuse existing model wrappers.
- Never instantiate models inside business logic.
- Model names must come from configuration.
- Keep prompts separate from code.
- Avoid duplicate client implementations.
- Support provider switching.
- Use structured outputs whenever possible.
- Keep temperatures deterministic by default.

## Preferred Providers

1. Ollama
2. vLLM
3. NVIDIA NIM
4. OpenAI

## Preferred Models

1. qwen2.5-coder:7b
2. qwen3:14b
3. llama3.1:8b