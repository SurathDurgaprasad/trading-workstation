# Dashboard & UI/UX Hardening

Strategy science mission, Phase 15. Substantial dashboard hardening already
happened earlier this session (the kill-switch banner and market-status
banner on every page, the `/intelligence` page's kill-switch visibility,
the AI-explanation/deterministic-rationale separation on the decision
detail page, and Phase 11's broker-connectivity banner fix). This phase's
distinct contribution: **the first real-browser verification of this
dashboard's history** — every prior check of `dashboard/app.py` was via
pytest's `starlette.testclient.TestClient` (httpx-backed, no real rendering
engine). This phase actually launched the dashboard and drove it through a
real browser.

## What was verified

Seeded a scratch live-sim/live-state DB pair (never the real
`data/live_sim_trading.db`/`data/live_state.db`) with a real pending
approval (via `LiveSimPipeline` against real cached AAPL data, the same
mechanism `tests/test_dashboard.py`'s own fixture uses), a live-looking
`DHAN`/`LIVE`/`CONNECTED` feed-status row, and a `MOCK`/`SIMULATED` one.
Launched `python main.py dashboard` against that seeded state and drove it
through the Browser pane:

- **Root page**: renders correctly with the seeded pending approval,
  correctly shows Phase 11's broker-connectivity banner as "A LIVE broker
  feed IS connected" (matching the seeded DHAN/LIVE/CONNECTED row), the
  market-status banner, and the feed-status table with correct MOCK/DHAN
  and SIMULATED/LIVE tag colors.
- **REJECT workflow**: clicked the real REJECT button on the seeded
  pending approval — the signal correctly disappeared from both the
  "Signals" and "Pending Approval" sections after the POST-then-redirect,
  confirmed via the page's own text content, not just an HTTP status code.
- **Kill switch activate/reset**: clicked "Activate kill switch" — the
  page immediately showed the full-width, high-contrast red "KILL SWITCH
  ACTIVE" banner with the activation timestamp and reason, exactly as
  designed. Clicked "Reset kill switch" — correctly returned to the
  INACTIVE state. Both actions verified against real HTTP round-trips
  through a real browser, not a test client.
- **`/intelligence` page**: renders the real market-intelligence scan
  table (real project data — this page reads `dashboard/intelligence.py`'s
  own DB paths, which are NOT the scratch demo paths used for the root
  page's live-sim state, so this legitimately exercised the actual
  persisted scan/decision/paper-execution/scheduler history from this
  project's own prior work), with kill-switch visibility, a read-only
  banner, and correctly-separated market-intelligence/prediction-
  performance/paper-execution/scheduler sections.
- **`/intelligence/{symbol}` decision detail page**: clicked through to a
  real symbol (KOTAKBANK.NS) — confirmed the DETERMINISTIC RATIONALE and
  AI EXPLANATION sections render as visually and structurally separate
  blocks (matching `tests/test_dashboard_intelligence.py`'s own
  assertions), real news items with source/timestamp attribution, and a
  correctly-labeled "AI summary (narration only): not available" state for
  a decision that was never run with `--with-ai`.

## Result

No new UI/UX bugs found. Every control exercised (REJECT, kill-switch
activate, kill-switch reset, navigation between all three page types)
behaved correctly and matched what the existing test suite already
asserted — this phase adds real-browser confirmation to that existing
test-level evidence, not a correction to it. One tooling note, not a
dashboard issue: the headless browser occasionally needed a short
`wait` before a screenshot to avoid a blank paint frame immediately after
navigation/interaction — a browser-automation timing artifact, unrelated
to the dashboard's own rendering (`get_page_text`/the accessibility tree
were unaffected and consistently correct throughout).
