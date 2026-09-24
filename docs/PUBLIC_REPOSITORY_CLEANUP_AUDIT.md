# Public repository forensic cleanup audit — 2026-09-24

A follow-up to [`docs/PUBLIC_RELEASE_AUDIT.md`](PUBLIC_RELEASE_AUDIT.md) (the original
public-release security/documentation pass). That pass deliberately deferred a full
root-directory reorganization under real time pressure. This document records the
dedicated forensic cleanup pass that completed it: every tracked file and folder in the
(already public) repository was audited against a single test — does this genuinely
belong in a professional public research/engineering portfolio — and moved, removed, or
left in place accordingly. **No live network access was used or attempted during this
pass** (no Dhan, no Yahoo Finance, no OpenAI, no external market-data provider) — this
was a pure repository-content audit.

## Files/folders audited

**625 tracked files** at the start of this pass (`git ls-files | wc -l`), across every
top-level directory. The two largest, least-previously-scrutinized directories —
`docs/` (109 files) and `audit/` (54 files) — were each given a dedicated,
file-by-file forensic pass (purpose, references, unique-evidence check, redundancy
check) rather than a spot-check. Every other directory (`.claude/`, `.cursor/`,
`live/`, `dashboard/`, `mcp_server/`, `scheduler/`, `agents/`, `llm/`, `rag/`,
`experiments/`, `quant_research/`, `research/`, `ml_research/`, root-level Python
entry points, configuration files) was audited directly against real import/reference
tracing (`git grep`, per-module import-count checks).

## Files kept

The overwhelming majority. Specifically:

- **All 107 non-canonical files in `docs/`** (39 top-level reports, 42 `docs/phases/`
  HTML phase reports, 27 `docs/research/` preregistrations, 1 `docs/design/` file) —
  a dedicated file-by-file audit found **zero literal duplicates and zero
  empty/broken/placeholder files**. Every file family that superficially looked like a
  duplicate set (the four "final output" mission reports, the five "Indian trading
  brain" reports, the two 2026-09-22 red-team documents, the "intelligence" audit
  cluster) turned out on inspection to be a genuine chronological/complementary chain,
  each document explicitly citing its predecessor and covering a distinct date, phase,
  or question.
- **52 of 54 files in `audit/`** — real, cited, reproducible research tooling and
  evidence (Python scripts with the portable-path fix already applied, results
  reports, and their underlying CSV/TSV data) backing the derivatives-research and
  edge-feasibility (point-in-time universe, mean-reversion closure) findings cited
  throughout `docs/EDGE_DISCOVERY_FINAL_REPORT.md`, `docs/RESEARCH_RESULTS.md`, and
  `docs/MASTER_KNOWN_ISSUES.md`.
- **All engineering source directories** (`live/`, `dashboard/`, `mcp_server/`,
  `scheduler/`, `agents/`, `llm/`, `rag/`, `experiments/`, `quant_research/`,
  `research/`, `ml_research/`, `backtesting/`, `strategy/`, and the rest) — a
  per-module import-count check (`git grep -l "import <module>"`) confirmed every one
  is genuinely imported/used somewhere in the codebase; none is dead. `rag/` and
  `build_vector_db.py` specifically were checked against the "is this a real,
  documented, dependency" test — both are: `build_vector_db.py` (0 internal imports,
  as expected — it is a standalone setup script, not a library module) is referenced
  from `ARCHITECTURE.md`, a real error message in `rag/errors.py`, and a test.
- `.claude/launch.json` and `.mcp.json` — small, functional, accurate configuration
  files that document real, working capabilities (the dashboard dev-server launch
  command; the real MCP tool server module) — kept as genuinely useful to a
  contributor, not personal scratch state.
- All 197 test files — the audit found no duplicate, obsolete, or machine-specific
  test worth removing.

## Files removed

| Path | Reason |
|---|---|
| `.cursor/commands/review.md` | Generic AI-editor boilerplate ("Review the selected code. Find bugs...") — zero project-specific content, zero reusable value |
| `.cursor/skills/fastapi-standards/SKILL.md` | Generic engineering-standards boilerplate, not specific to this project |
| `.cursor/skills/langgraph-architecture/SKILL.md` | Personal AI-editor scratch state |
| `.cursor/skills/local-llm-standards/SKILL.md` | Personal AI-editor scratch state |
| `.cursor/skills/multi-agent-debate-pattern/SKILL.md` | Personal AI-editor scratch state |
| `.cursor/skills/python-engineering-standards/SKILL.md` | Generic platitudes ("Follow SOLID principles," "Use descriptive names") — no unique content |
| `.cursor/skills/trading-domain-standards/SKILL.md` | **Actively inaccurate** — describes a `STRONG_BUY/BUY/WAIT/SELL/STRONG_SELL` decision taxonomy that does not match the real, documented system (`decision_engine/` actually uses `BUY/WATCH/AVOID/EXIT/NO_ACTION` — see README/ARCHITECTURE.md). Removing stale, misleading documentation, not just clutter. |
| `.cursor/skills/vector-db-standards/SKILL.md` | Generic AI-editor scratch state |
| `.cursorignore` | References subsystems that do not exist in this project (`qdrant_storage/`, `models/`, `checkpoints/` — this project uses ChromaDB, not Qdrant, and has neither a `models/` nor `checkpoints/` directory), which could actively mislead a reader about the actual architecture |
| `audit/edge_feasibility/EVIDENCE.csv` | Header-only template, zero data rows, never referenced anywhere in the repository (including within `audit/` itself); `EVALUATION_AUDIT.md` documents that the per-hypothesis evidence pass this file was scaffolded for was never completed |

**10 files removed total.** No source code, no test, and no research report/evidence
file was removed.

## Files moved

| Old path (root) | New path | Reference count fixed |
|---|---|---|
| `FINAL_ADVERSARIAL_ENGINEERING_AUDIT.md` | `docs/FINAL_ADVERSARIAL_ENGINEERING_AUDIT.md` | 1 |
| `FINAL_PRODUCT_AUDIT.md` | `docs/FINAL_PRODUCT_AUDIT.md` | 2 |
| `FINAL_PRODUCT_CAPABILITY_MATRIX.md` | `docs/FINAL_PRODUCT_CAPABILITY_MATRIX.md` | 4 |
| `FINAL_PRODUCT_READINESS_REPORT.md` | `docs/FINAL_PRODUCT_READINESS_REPORT.md` | 7 |
| `FINAL_RELEASE_CANDIDATE_REPORT.md` | `docs/FINAL_RELEASE_CANDIDATE_REPORT.md` | 1 |
| `FINAL_RELEASE_REMAINING_WORK.md` | `docs/FINAL_RELEASE_REMAINING_WORK.md` | 3 |
| `AUDIT_BASELINE.json` | `docs/AUDIT_BASELINE.json` | 4 |
| `AUDIT_GAPS.md` | `docs/AUDIT_GAPS.md` | 3 |
| `TRADING_INTELLIGENCE_GAP_ANALYSIS.md` | `docs/TRADING_INTELLIGENCE_GAP_ANALYSIS.md` | 3 |
| `TRADING_STRATEGY_READINESS.md` | `docs/TRADING_STRATEGY_READINESS.md` | 4 |
| `PHASE_1_IMPLEMENTATION_SPEC.md` | `docs/research/PHASE_1_IMPLEMENTATION_SPEC.md` | 11 |
| `PHASE_1_REPORT.md` | `docs/research/PHASE_1_REPORT.md` | 1 |
| `TRADING_FEATURE_CATALOG.json` | `docs/research/TRADING_FEATURE_CATALOG.json` | 1 |

**13 files moved.** All done with `git mv` (preserves file history). Every real
markdown hyperlink (`[text](path)` syntax) pointing at any of these 13 files was
found via `git grep` and fixed — 6 actual hyperlinks needed a path change (in
`README.md` ×4, `docs/MARKET_DATA_SOURCES.md`, `docs/RESEARCH_RESULTS.md`); the
remainder of the ~60 total `git grep` hits on these filenames were plain-text prose
citations inside already-frozen historical reports (e.g. `ml_research/*.py`'s own
code comments citing "`PHASE_1_IMPLEMENTATION_SPEC.md` Section 9") or references
between two files that both moved into the same new directory, where a bare-filename
reference continues to resolve correctly without any edit. **A full, automated
markdown-link checker was then run against all 127 tracked `.md` files in the
repository** (every `[text](path)` link, relative-path resolution checked against the
actual filesystem) — zero broken links remained afterward, other than the two
self-referential forward links to this document, which resolve as of this commit.

Two files that were candidates for the same treatment were deliberately **kept at
root** rather than moved:

- **`FINAL_FAILURE_MODE_ANALYSIS.md`** — 23 inbound references, the highest of any
  file in the repository. This is a genuinely core engineering document (53
  evidence-labeled FAILURE→DETECTION→RESPONSE→RECOVERY scenarios), arguably as
  load-bearing as `ARCHITECTURE.md` or `SECURITY.md`. Moving it carried real risk of
  missing one of 23 references under this pass's own scope; keeping it at root next
  to the other primary engineering documents is a defensible presentation choice, not
  an oversight.
- **`PROJECT_GOAL_AND_ROADMAP.md`** — the project's own founding vision/blueprint
  document (2,176 lines, the earliest-dated file in the repository), 10 inbound
  references including from `README.md` itself. Kept at root alongside `README.md` as
  the project's own stated "authoritative intent doc," consistent with how a reader
  would expect to find it.

## Files consolidated

**None.** The `docs/` and `audit/` forensic passes found zero literal duplicates —
every file that superficially resembled another turned out, on reading, to cover a
distinct date, phase, hypothesis, or question. No consolidation was performed because
none was needed; inventing a merge to reduce the file count would have destroyed real
distinctions between reports, which this pass's own instructions explicitly warned
against.

## Research evidence preserved

All of it. Specifically preserved without modification: all 27 `docs/research/`
hypothesis preregistrations, all 42 `docs/phases/` numbered-phase reports, all 39
top-level `docs/` research/validation/red-team reports, and all 52 kept files in
`audit/` (research scripts, results reports, and their underlying CSV/TSV data —
including `POINT_IN_TIME_SNAPSHOTS.csv`, the specific derived, redistribution-safe
artifact this project's own `.gitignore` and `docs/CAPABILITIES.md` already call out
as replacing the raw, gitignored NSE bhavcopy cache). The "69 tested, 0 promoted"
claim in `README.md`/`docs/RESEARCH_RESULTS.md`/`docs/LIMITATIONS.md` remains fully
traceable to this preserved evidence.

## Security

Re-scanned after every material change in this pass:

- `git ls-files -z | xargs -0 grep -lF 'C:\Users'` — one hit, `docs/PUBLIC_RELEASE_AUDIT.md`,
  confirmed to be that document's own prose *describing* the pattern it searched for
  (a placeholder `<name>`, not a real path) — the same, already-explained false
  positive as every prior pass in this repository's history.
- `detect-secrets scan` against all 13 moved files — zero new findings; the only
  matches are the same two already-confirmed real-git-SHA false positives in
  `docs/AUDIT_BASELINE.json` carried over from its prior audit.
- No credential, personal email, or machine-specific path was found in any file
  touched by this pass.

## Tests

Full suite re-run after this cleanup, both locally and on GitHub's own public CI:

- **Local**: `2779 passed, 0 failed` (this cleanup pass touched no source or test
  file — only documentation/config files were moved or removed — so no test count
  change was expected or occurred).
- **CI** (run `35976444458`, commit `b68dac8`, the commit this cleanup pass is
  itself part of): **`success`** — `2656 passed, 123 skipped, 0 failed` (409.81s) for
  the full suite, and `46 passed` (31.12s) for the dedicated safety-test step
  (`test_dhan_no_real_orders.py`, `test_dhan_credential_security.py`,
  `test_ai_output_cannot_carry_trading_authority.py`, `test_approval_security.py`,
  `test_mcp_live_workstation.py`). `2656 + 123 = 2779`, matching the local total; the
  123 skips are the same expected, already-documented local-cache-dependent tests.

## Documentation updated

- `README.md` — 4 links repointed to the new `docs/` paths.
- `docs/MARKET_DATA_SOURCES.md`, `docs/RESEARCH_RESULTS.md` — 1 link each repointed.
- `docs/PUBLIC_RELEASE_AUDIT.md` — its own now-outdated "root-level historical
  reports" section and top-level structure listing were corrected in place (not
  deleted) to point to this document as the current, authoritative record, preserving
  the original reasoning trail rather than erasing it.
- This document (`docs/PUBLIC_REPOSITORY_CLEANUP_AUDIT.md`) — new.

## Known limitations (carried over, unchanged by this pass)

Everything already disclosed in `docs/PUBLIC_RELEASE_AUDIT.md` §11 remains true and is
not repeated here. Nothing this pass did introduced a new limitation.

## Public status

The repository remains **PUBLIC** throughout and after this pass — this cleanup never
changed visibility, and no step in it required doing so.

## Final repository state

All changes in this pass are committed to `final-product-hardening`, fast-forward
merged to `main`, and pushed to `origin` — see the commit this document is itself
committed alongside for the exact hash (this document is written and committed as
part of the same change as the file moves/removals it describes, so its own commit
hash is that commit).
