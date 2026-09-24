# Public release audit — 2026-09-24

This document records the public-release preparation pass performed on this
repository: what was checked, what was found, what was changed, and the exact state of
every gate at the point this document was written. It does not contain, and must never
be edited to contain, any secret value.

## Release identity

| | |
|---|---|
| Release date | 2026-09-24 |
| Release commit | `cf879fe741db48b2e4d6893688260ff564f30806` |
| Release tag | `v1.0.0-research-archive` |
| Default branch | `main` (kept in sync with `final-product-hardening` throughout, ff-only merges) |
| Repository | `SurathDurgaprasad/trading-workstation` |
| Owner | `SurathDurgaprasad` |

## Repository structure (top-level, after this pass)

```
README.md, LICENSE, SECURITY.md, CONTRIBUTING.md, CHANGELOG.md, ARCHITECTURE.md
INSTALLATION.md, USER_GUIDE.md, OPERATIONS_GUIDE.md, TROUBLESHOOTING.md
PROJECT_GOAL_AND_ROADMAP.md
FINAL_*.md, AUDIT_*.{md,json}, TRADING_*.{md,json}  (dated historical audits/reports, kept — see "What was intentionally kept in place")
.github/workflows/tests.yml
.env.example, .gitignore, .mcp.json, pytest.ini, requirements.txt
main.py, app.py (compat entry point)
agents/, backtesting/, config/, core/, critic/, dashboard/, decision_engine/,
experiments/, graph.py, learning/, live/, llm/, market/, market_data/,
market_intelligence/, mcp_server/, ml_research/, paper/, predictions/, quant_research/,
rag/, research/, risk/, scheduler/, schemas/, state.py, strategy/
docs/          — 40+ reports, docs/research/ (per-hypothesis preregistrations),
                 docs/phases/ (42 numbered-phase HTML reports), docs/audits/,
                 docs/design/ (a design-mockup provenance artifact)
tests/         — 2779 tests, no live/paid dependency
```

## 1. Security audit — current working tree

**Method**: (a) `detect-secrets` (Yelp, v1.5.0) run against the full tracked file set
and separately against the full working tree; (b) a hand-written regex sweep for
AWS/GitHub/Slack/Google/OpenAI key formats, PEM private-key headers, Bearer tokens,
JWTs, and generic `password=`/`secret=`/`api_key=` assignments; (c) the project's own
existing credential-security regression tests
(`tests/test_dhan_credential_security.py`, 9 tests, all passing).

**Result: zero real credentials found.** `detect-secrets` flagged exactly two files,
both confirmed false positives before this report was written:

| File | Finding | Disposition |
|---|---|---|
| `AUDIT_BASELINE.json` (2 lines) | "Hex High Entropy String" | Real git commit SHAs (`head_sha`, `first_commit.sha`) — not secrets, and independently visible via `git log` regardless |
| `tests/test_llm_provider_openai.py` (1 line) | "Base64 High Entropy String" | A deliberately fake, obviously-labeled test fixture (`"sk-THIS-VALUE-MUST-NEVER-APPEAR-IN-ANY-LOG-..."`) used to prove the real key is never logged |

`.env` (the one file that could contain real local credentials) is confirmed present
only in the local, untracked working directory, correctly excluded by `.gitignore`
(`git check-ignore -v .env` confirms), never tracked (`git ls-files .env` returns
nothing), and never committed at any point in this repository's history (§2).

## 2. Security audit — full git history (325+ commits)

**Method**: this pass did not rely on the working tree alone. Three independent,
overlapping methods were used against `git log --all`:

1. Targeted pickaxe searches (`git log --all -S<pattern>`) for: `.env`-style filenames
   ever added, `DHAN_ACCESS_TOKEN=<value>`, `sk-` (OpenAI-shaped), `ghp_` (GitHub),
   `AKIA` (AWS), `BEGIN PRIVATE KEY`, `BEGIN RSA PRIVATE KEY`, `Bearer <token>`, JWT
   (`eyJhbGci...`), `password=`, `client_secret=`, `refresh_token=`, and SSH private-key
   filenames (`id_rsa`/`id_ed25519`/`id_ecdsa`).
2. A comprehensive, line-by-line regex sweep across the **entire** `git log --all -p`
   diff text (every added/removed line in every commit, ~12.7MB of patch text) against
   17 credential-pattern regexes covering the same categories as above.
3. A filename-based history search (`git log --all --diff-filter=A --name-only`) for
   any file ever added matching `.env`/`.pem`/`.key`/`.p12`/`.pfx`/`.db`/`.sqlite`/
   `credential`/`secret`/`password` in its name.

**Result: zero real credentials found anywhere in this repository's history.** The one
match from method 1 (`DHAN_ACCESS_TOKEN=` pickaxe hit, commit `24e975d`) was confirmed
by direct inspection to be documentation prose *describing* the search pattern, not a
credential. The one filename match from method 3
(`tests/test_dhan_credential_security.py`) is the test file itself.

## 3. Private-data audit

| Finding | Location | Disposition |
|---|---|---|
| A real personal email address | `AUDIT_BASELINE.json`, `contributors` field | **Fixed this pass** — email redacted, name-only kept |
| Hardcoded local Windows absolute paths (`C:\Users\<name>\...`) | 9 research scripts under `audit/` | **Fixed this pass** — replaced with a portable `Path(__file__).resolve().parents[3]` derivation; verified all 9 still compile and the full suite still passes |
| Git commit-author email | Every commit's own metadata (325+ commits) | **Not changed** — this is the repository owner's own name/email on their own project, standard for a personal open-source repository, and not a "leaked" secret in the same sense as a credential. Rewriting 325 commits' author metadata was judged disproportionate for a cosmetic concern and was not requested. Flagged here so the decision is visible, not silent. |
| `AUDIT_GAPS.md` | Root | Considered for removal (a 2026-09-13 gap-tracker snapshot); **kept** — a later, current report (`docs/FULL_SYSTEM_RED_TEAM_2026-09-22.md`) explicitly cites it as "an existing, current, comprehensive gap tracker," so treating it as safely disposable would have been incorrect |
| "Trading Workstation.dc.html" (a design-tool export, zero incoming references) | Root | **Moved** to `docs/design/dashboard_redesign_mockup.dc.html` — zero risk (nothing referenced it), improves root-directory legibility |
| `PHASE_1_EXECUTION_LOG.md` (zero incoming references) | Root | **Moved** to `docs/research/ML_PHASE1_EXECUTION_LOG.md`, alongside its own preregistration |

No personal phone numbers, brokerage account numbers, physical addresses, or IP
addresses were found anywhere in the tracked tree.

### A note on other root-level historical reports

Several dated audit/report files (`FINAL_ADVERSARIAL_ENGINEERING_AUDIT.md`,
`FINAL_FAILURE_MODE_ANALYSIS.md`, `FINAL_PRODUCT_*.md`, `TRADING_*.{md,json}`,
`AUDIT_BASELINE.json`) remain at the repository root rather than being relocated into
`docs/`. This was a deliberate choice, not an oversight: several of them (notably
`FINAL_FAILURE_MODE_ANALYSIS.md`, referenced from 23 other files, and
`PHASE_1_IMPLEMENTATION_SPEC.md`, referenced from 11) are heavily cross-linked from
elsewhere in the repository, and moving them would have required updating every one of
those references under real time pressure — a real risk of introducing a broken
portfolio link, which would look worse than the root directory having more files in it
than a minimal template. Each of these files was individually confirmed, this pass, to
contain no credential and no private data (§1, §3).

## 4. Credential architecture

- `.env.example` documents every credential this project reads
  (`DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN`, `AI_PROVIDER`/`OPENAI_API_KEY`/etc., 9
  `TRADING_*_DB_PATH` overrides), with every value left blank — confirmed by
  `tests/test_dhan_credential_security.py::test_env_example_file_has_no_real_looking_values`.
- `.gitignore` covers `.env`, `.env.*` (with an explicit `!.env.example` exception),
  `*.pem`, `*.key` — confirmed by
  `tests/test_dhan_credential_security.py::test_gitignore_covers_env_files_and_key_material`.
- No code anywhere reads a `.env` file automatically (no `load_dotenv()` call exists in
  this repository) — every credential is read from the process environment only, lazily,
  at the moment of a real external call.
- `python main.py readiness-check` reports credential *presence* without ever printing
  a value — verified directly this pass (real command run, real output inspected).

## 5. Database and log audit

No database file (`*.db`) and no log file (`*.log`) is tracked by git — confirmed via
`git ls-files data/` (empty) and the `.gitignore` rules `data/*.db` and `*.log`. Every
store is created fresh, locally, on first use; there is nothing to sanitize because
nothing of this kind was ever committed.

## 6. Test results

- **Full suite**: `pytest -q` → **2779 passed, 0 failed** (578.64s / 9m38s), 2
  warnings (a benign Windows-temp-file `PermissionError` during one test's own thread
  cleanup, and a third-party `chromadb` deprecation warning — neither affects
  pass/fail status).
- **Dedicated safety/credential tests** (run explicitly, separately, this pass):
  `tests/test_dhan_no_real_orders.py`, `tests/test_dhan_credential_security.py`,
  `tests/test_ai_output_cannot_carry_trading_authority.py` — **26/26 passed**.
- No test in the suite requires a live connection or a real credential; the suite runs
  standalone by design.

## 7. Documentation audit

New documents added this pass, each satisfying one explicit release requirement:
`docs/SAFETY.md`, `docs/LIMITATIONS.md`, `docs/CAPABILITIES.md`,
`docs/RESEARCH_METHODOLOGY.md`, `docs/RESEARCH_RESULTS.md`, `docs/LIVE_VALIDATION.md`,
`docs/OPERATIONS.md`. `README.md` was fully rewritten as a portfolio-facing README
(what/why/architecture/research method/result/safety/how-to-run/limitations, in that
order, in the first screen). `ARCHITECTURE.md` was extended (not rewritten) with a
DATA/RESEARCH/DECISION/RISK/EXECUTION/OBSERVABILITY categorization, documentation of
the previously-undocumented advisory LLM layer, and a Mermaid pipeline diagram.

## 8. Dependency audit

`requirements.txt` was reviewed for currency; no dependency was added or removed this
pass. The existing, detailed CVE-applicability triage in `SECURITY.md` (pip-audit
against the full `venv/`, most recently "autonomous hardening cycle 17") was **not
re-run** this pass — it remains the most recent scan on record and is not represented
here as current-as-of-today. Recommendation, carried over from `SECURITY.md` itself:
re-run `pip-audit` periodically, not treat any past scan as a one-time clearance.

## 9. CI audit

`.github/workflows/tests.yml` (new this pass): runs the full offline `pytest` suite
plus the dedicated real-order safety tests, on `windows-latest` (the only platform this
project has been developed/tested on — chosen for honesty over convenience; it does not
claim Linux/macOS support). Requires no secrets, contacts no external service, places no
order. Triggered on push/PR to `main`, `pull_request`, and manual dispatch.

**Verified, not just configured**: the first real run of this workflow on GitHub's own
`windows-latest` runner (triggered by this release's own push to `main`, run
`35969027003`) completed with **`success`** in 6m37s — a genuine, independent
confirmation (fresh clone, fresh `pip install`, no local caches) that the full 2779-test
suite passes from a clean environment, not only on the machine this project was
developed on.

## 10. Public-visibility verification

**Not yet performed as of this document's writing** — the repository remains
**PRIVATE**. See the accompanying final report for the exact reason this step was
deliberately held back for one explicit human confirmation before being taken, despite
this mission's own instruction to operate autonomously through to publication.

## 11. Known remaining limitations of this release

- Cross-platform (Linux/macOS) support is a reasoned code-level claim, not an
  empirically verified one (§9, and `docs/OPERATIONS.md`).
- The dependency vulnerability scan in `SECURITY.md` is not current-as-of-today (§8).
- `AUDIT_GAPS.md`, several `FINAL_*.md`/`TRADING_*.md` root files, and
  `PROJECT_GOAL_AND_ROADMAP.md` are point-in-time snapshots from earlier in the
  project's history and are not automatically kept in sync with later documents;
  README.md's documentation index says so explicitly ("where a later document disagrees
  with an earlier one, the later document ... is authoritative").
- git commit-author metadata (name + real personal email) remains visible across
  325+ commits once the repository is public — a disclosed, deliberate non-fix (§3).

## 12. Intentionally excluded artifacts (never committed, not part of this release)

- Every local SQLite database under `data/` (account state, predictions, scanner
  history, experiment registries, live-session correlation stores) — regenerable local
  state, several containing real historical live-session data not intended for public
  redistribution.
- `data/market/**/*.csv` and `.meta.json` — cached third-party (Yahoo Finance) OHLCV
  data; redistributing bulk third-party market data was judged out of scope.
- `data/dhan/` (the Dhan instrument master) and `audit/edge_feasibility/bhavcopy_cache/`
  (raw NSE F&O bhavcopy archives) — third-party data with unclear bulk-redistribution
  terms; the derived, committed artifact (`POINT_IN_TIME_SNAPSHOTS.csv`) is kept
  instead.
- `.env`, any `*.pem`/`*.key` — never existed as tracked files; excluded on principle.
- `runtime/`, `vectorstore/`, `evidence_run/`, `.hypothesis/`, `.pytest_cache/`,
  `__pycache__/` — generated/local-only, standard exclusions.
