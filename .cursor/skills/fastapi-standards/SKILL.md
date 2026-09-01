---
name: fastapi-standards
description: >-
  Build production-grade FastAPI services.
  Use when creating APIs, routers, endpoints, or schemas.
---

# FastAPI Standards

## Rules

- Use APIRouter.
- Use Pydantic models.
- Keep business logic outside endpoints.
- Return structured JSON.
- Handle exceptions explicitly.
- Add type hints everywhere.
- Preserve backward compatibility.
- Avoid global mutable state.
- Keep routes thin.
- Prefer dependency injection.