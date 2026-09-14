# Security

This document describes the current, verified security posture of this
repository — what was checked, how, and what was found. It describes
the system as it exists today, not an aspirational target.

## Threat model

This is a **single-user, local-first** application. It is designed to
run on one operator's own machine, reachable at most from that
machine's own network (the dashboard binds to loopback by default).
It is **not** designed to be exposed to the public internet, run
multi-tenant, or handle untrusted input from strangers. Every finding
below should be read against that threat model.

## Live trading is structurally blocked

This is the single most important security property of the system, so
it is verified repeatedly, not assumed:

- `live/dhan/broker_adapter.py`'s `DisabledDhanOrderExecutor` raises
  `RealOrderPlacementDisabledError` unconditionally from every order
  method (`place_order`, `modify_order`, `cancel_order`) — not merely
  unimplemented, but structurally incapable of executing.
- A repository-wide search finds zero `requests.post`/`requests.put`/
  `requests.delete` calls anywhere in the codebase — only
  `requests.get` (read-only), in `live/dhan/rest_client.py` and
  `live/dhan/clock_skew.py`.
- `DisabledDhanOrderExecutor` is constructed only in
  `tests/test_dhan_no_real_orders.py` — never in any production code
  path (`main.py`, `live/pipeline.py`, `live/workstation.py`,
  `mcp_server/server.py`).
- The MCP server (`mcp_server/server.py`) exposes 23 tools, all
  read-only or paper-only; no order-placement tool exists.
- Regression test: `tests/test_dhan_no_real_orders.py`, re-verified
  passing after every change made in this hardening campaign.

## Credentials

- The only credential this project reads is a Dhan broker API
  client ID and access token (`DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`),
  read lazily from the process environment at the moment of an actual
  Dhan call — never at import time, never auto-loaded from a `.env`
  file (no `python-dotenv`/`load_dotenv` call exists anywhere in this
  repository; you must export these yourself or use a secret manager).
- `DhanCredentials.__repr__` is overridden to print `client_id='***',
  access_token='***'` — verified by `tests/test_dhan_credential_security.py`.
- No log or print statement anywhere in `live/dhan/*.py` interpolates
  the raw client ID or access token. A `_redact_secret` helper strips
  the token from exception/reconnect-failure text before it is logged,
  as defense-in-depth against a third-party library ever embedding a
  URL or token in its own exception message.
- `.env.example` documents every credential this project reads, with
  the real values left blank. `.gitignore` covers `.env`, `.env.*`
  (except `.env.example`), `*.pem`, and `*.key`; none of those are
  tracked in this repository.
- `tests/test_dhan_credential_security.py` additionally asserts: no
  hardcoded credential literal in `live/dhan/*.py`, and no tracked
  file contains a JWT-shaped access-token pattern.

## Secret scan

A repository-wide grep for high-confidence secret patterns (AWS access
keys, PEM private-key headers, Slack/OpenAI/GitHub token formats) was
run against the full source tree (excluding `venv/`): zero matches
outside two obviously-fake test fixture tokens
(`tests/test_dhan_market_data_source.py`,
`tests/test_market_data_adapter_builders.py`, both literal strings
like `"fake-token-for-tests"`).

## Application-layer findings (prior audit, re-confirmed unchanged)

- **SQL injection**: every SQLite store parameterizes user-derived
  values in queries; table/column names in DDL (which cannot be
  parameterized in SQLite) are always this codebase's own hardcoded
  literals, never external input.
- **XSS**: dashboard HTML output consistently escapes user-influenced
  content (symbol names, rationale text, etc.) before interpolating it
  into a response.
- **Path traversal**: fixed in a prior phase; documented in
  `docs/SECURITY_REVIEW.md`.
- **No secrets in git history**: confirmed in the same prior review,
  unchanged since (no credential-bearing commit has been made since).

## Dependency vulnerability scan

Run with `pip-audit` against the full `venv/` (not just direct pins —
`pip-audit` walks every installed package, transitive dependencies
included) as part of this hardening campaign, most recently
**autonomous hardening cycle 17** (a re-scan; the prior scan, cited
below, was from an earlier release-gate pass). The re-scan surfaced 53
advisories across 8 packages — a large jump from the prior scan's 2,
reflecting newly-disclosed CVEs in the time between scans, not a
change this project made. Every one was triaged the same way: **is
this package's vulnerable code path ever actually reachable in this
project's own usage**, not merely "is it present in `venv/`."

| Package | Advisories | Applicable here? |
|---|---|---|
| `langchain` | PYSEC-2026-2192 (filesystem-path-confinement in agent file-search middleware and prompt/chain-config loaders) | **Not exploitable** — this project imports only `langchain_core`, `langchain_text_splitters`, `langchain_community`, and `langchain_chroma`; never the agent file-search middleware or configuration loaders (the vulnerable components). Bumped to the patched version anyway as defense-in-depth. |
| `chromadb` | PYSEC-2026-311, -3813, -3814, -3815 (code injection and cross-tenant authorization bypasses in chromadb's networked, multi-tenant HTTP server) | **Not exploitable** — used exclusively as an embedded, local, file-backed vector store (`langchain_chroma.Chroma(persist_directory=...)`, see `rag/retriever.py`, `rag/vector_store.py`). The vulnerable networked HTTP server is never started. No fix version listed by `pip-audit`; left pinned since the vulnerable surface does not exist in this deployment. |
| `torch` | PYSEC-2025-194 | **Not exploitable, and not even executed** — `grep`-confirmed zero direct import anywhere in project code (autonomous hardening cycle 17). Present only as a transitive dependency of one of chromadb's optional embedding-function extras; this project's own RAG embeddings go through `llm/provider.py::get_embeddings()`, which calls Ollama's `OllamaEmbeddings` over HTTP (confirmed by reading that function directly) — torch's own code never runs in this project's actual code path. |
| `pypdf` | PYSEC-2026-3018/3610/3611/3612/3613/3655/3656/3910/3911/3912/3913, CVE-2026-57204 | **Not exploitable, and not even executed** — `grep`-confirmed zero direct import anywhere in project code (cycle 17). Transitive only; this project's document ingestion path was not found to route through `pypdf` directly. |
| `aiohttp` | PYSEC-2026-2107 through -2113, -237, -3545/3546/3547 | **Not exploitable, and not even executed** — `grep`-confirmed zero direct import (cycle 17). Transitive-only (likely pulled in by `langchain-community`'s or `mcp`'s own optional async-HTTP extras, never invoked here — this project's own HTTP calls all go through the synchronous `requests` library, per this document's own "Live trading is structurally blocked" section above). |
| `langsmith` | CVE-2026-59152 | **Not exploitable** — transitive dependency of `langchain`, active only when LangChain tracing is explicitly enabled (`LANGCHAIN_TRACING_V2`/`LANGSMITH_API_KEY`); this project sets neither. |
| `pydantic-settings` | CVE-2026-58203 | **Not exploitable, and not even executed** — `grep`-confirmed zero direct import (cycle 17). This project's own config (`core/config.py::Settings`) is a plain `pydantic.BaseModel`, never `pydantic_settings.BaseSettings`; present only as some other package's transitive dependency. |
| `pip`, `setuptools` | PYSEC-2026-3721, PYSEC-2026-3447 | **Different category, not an application vulnerability** — these are the packaging/installer toolchain itself, not runtime dependencies this project's own code imports or executes. Relevant to supply-chain hygiene when installing (`pip install --upgrade pip` before `pip install -r requirements.txt` is good practice), not to this application's own attack surface once installed. |

No other package had a known vulnerability at scan time. This scan
reflects a point in time — dependencies should be re-scanned
periodically (`pip install pip-audit && pip-audit`), not treated as a
one-time clearance. The triage methodology above (direct-import
`grep`, then trace the actual code path for anything that IS imported)
is the reusable check for any future re-scan, not a one-off judgment
call specific to this list.

## LLM / RAG failure is non-fatal to the deterministic core

The optional Ollama-backed narration/RAG layer can fail (Ollama down,
unreachable, model missing) without affecting the deterministic
scan → decision → risk → paper-trade pipeline:

- `decision_engine/engine.py` and `research/summarizer.py` both wrap
  their LLM calls in a try/except that degrades to a
  `narrative_unavailable_reason` field rather than raising or blocking
  the decision.
- `analyze` and `review` are the two commands whose entire purpose is
  the AI step — they fail clearly (no silent fallback) if Ollama is
  unreachable, by design.
- No LLM output can ever place an order, resize a position, or change
  a price level — narration and RAG context are advisory text fields,
  never inputs to `risk/engine.py` or `paper/engine.py`.

## Configuration

- `risk/config.py`, `critic/config.py`, `decision_engine/config.py`,
  and `market_intelligence/config.py` are all frozen pydantic models
  with `Field(gt=/ge=/le=, description=...)` on every numeric field —
  an out-of-range or malformed value raises a clear `ValidationError`
  at construction, never silently falls back to a dangerous default.
- `scheduler/config.py`'s `ScheduleSlot` gained an explicit
  `__post_init__` validation this campaign (an inverted/zero-width
  `[after, before)` eligibility window, or a non-positive
  `frequency_minutes`, now raises `SchedulerConfigurationError`
  immediately — previously it would silently produce a slot that could
  never become due, a real, disclosed gap closed with a real fix and
  tests).
- `core/config.py`'s `Settings` (the LLM/RAG advisory-layer config) has
  no per-field range validation. This is an accepted limitation, not
  an oversight: `Settings` is constructed exactly once, with zero
  arguments (`get_settings() -> Settings()`), from nowhere that reads
  untrusted or dynamic input — there is no attack surface to defend
  against today. If a future change ever constructs `Settings` from
  CLI args, environment variables, or any other external input, this
  should be revisited.
- Every database-path environment variable override
  (`TRADING_*_DB_PATH`) is documented in `.env.example`.

## Reporting a concern

This is a personal research project, not a maintained public package.
If you fork or adapt this code for your own use, re-run
`pip-audit -r requirements.txt` and this document's own checks against
your fork before relying on it for anything beyond paper trading.
