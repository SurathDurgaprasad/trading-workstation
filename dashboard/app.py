"""Phase 13 §19 — a minimal local dashboard for the `paper-live` human-
approval workstation. Built ONLY after the CLI workflow (main.py's
`paper-live` command) was confirmed reliable, per spec.

Single-user, local-only, no new heavy dependency: Starlette + uvicorn are
already installed (transitive deps of the `mcp` package's HTTP transport),
so this adds nothing to requirements.txt. No database, no auth system, no
Kubernetes/cloud/Postgres/Redis/Kafka — one ASGI process, bound to
127.0.0.1 by default (see main.py's `dashboard` subcommand).

Every section reads through live/workstation.py — the SAME module
mcp_server/server.py's Phase 13 tools use — and the two POST actions
(approve/reject) call live.workstation.approve_pending_signal()/
reject_pending_signal(), which call the exact same
LiveSimPipeline.approve_pending()/reject_pending() the CLI's interactive Y/N
prompt calls. This module contains NO business logic of its own: no risk
math, no signal generation, no account arithmetic — only HTML rendering and
routing. Nothing here can execute a real order; no execute_trade/
place_order/broker-credential path exists anywhere in this codebase.

This dashboard does NOT itself advance the market feed (it never calls
LiveSimPipeline.process_next()) — that stays the CLI's job (`paper-live`),
to avoid two different processes racing to drive the same mock feed. The
dashboard is a read/act SURFACE over the persisted state the CLI (or a
script) advances; run `python main.py paper-live ...` in another terminal
to generate bars/signals for this page to show and act on.
"""

import html
from datetime import datetime, timezone
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

import live.workstation as workstation
from core.config import PROJECT_ROOT
from core.timeutil import as_utc_aware
from dashboard import intelligence

_REFRESH_SECONDS = 15

_schedule_config_path: str | None = None
"""Set once at startup by main.py's `run_dashboard_command` via
`configure()`, from the optional `--schedule-config` CLI flag. None (the
default -- e.g. under every existing test, which never calls
`configure()`) reproduces the page's original behavior exactly."""


def configure(*, schedule_config_path: str | None, fleet_runtime_dir: str | None = None, fleet_symbols: list[str] | None = None) -> None:
    """Live-market-readiness audit finding: the dashboard's own market-
    status banner never had a way to consult the SAME holiday list an
    operator may have already configured for the scheduler
    (scheduler/config.py's ScheduleConfig.holidays, YAML `--config`) --
    it only ever printed a generic "does not know holidays" disclaimer.
    Called once at process startup, never per-request (a dashboard GET
    must never trigger file I/O just to render the banner -- see
    `_market_status_banner`'s own docstring); the loaded holiday set is
    cached at module level for the life of the process.

    UI integration (Claude Design "Trading Workstation" approved canvas):
    `fleet_runtime_dir`/`fleet_symbols` are optional, same pattern as
    `schedule_config_path` -- when omitted (the default, e.g. every
    existing test), the Fleet tab honestly reports itself as not
    configured rather than fabricating fleet data. When given, they
    point the Fleet tab at the SAME `runtime/{SYMBOL}/...` layout
    `live/runtime_layout.py` and `fleet-supervise`/`fleet-summary`
    already use -- no new fleet data model is introduced here."""
    global _schedule_config_path, _cached_holidays, _fleet_runtime_dir, _fleet_symbols
    _schedule_config_path = schedule_config_path
    _cached_holidays = _load_holidays(schedule_config_path)
    _fleet_runtime_dir = fleet_runtime_dir
    _fleet_symbols = fleet_symbols or []


_fleet_runtime_dir: str | None = None
"""UI integration: set by `configure(fleet_runtime_dir=...)`. None (the
default) means the Fleet tab is not configured -- see `fleet_page()`."""

_fleet_symbols: list[str] = []
"""UI integration: set by `configure(fleet_symbols=...)`."""

_cached_holidays: frozenset | None = None
"""None (the default, e.g. every existing test that never calls
configure()) means "no calendar was ever consulted" -- deliberately
distinct from an explicitly-loaded, possibly-empty frozenset(). Collapsing
both to a bare frozenset() was a real bug caught by this fix's own tests
before it shipped (see main.py's identical fix and its own note)."""

_DEFAULT_SCHEDULE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "schedule.yaml"
"""Same default-path convention as main.py's identically-named constant
(kept as a separate copy, not a cross-import, since dashboard/app.py has
no existing dependency on main.py and shouldn't gain one for three
lines) -- an operator who forgets to pass --schedule-config still gets
holiday cross-checking if they've populated this conventional path."""


def _load_holidays(path: str | None) -> frozenset | None:
    resolved = path or (str(_DEFAULT_SCHEDULE_CONFIG_PATH) if _DEFAULT_SCHEDULE_CONFIG_PATH.exists() else None)
    if not resolved:
        return None
    from scheduler.config import ScheduleConfig

    return frozenset(ScheduleConfig.from_yaml_file(resolved).holidays)


def _market_status_banner() -> str:
    """Computed fresh, in-process, from wall-clock IST time only -- zero
    I/O, zero network call, safe on every page load (mission rule: a
    dashboard GET must never trigger a hidden market-data fetch). The
    holiday set itself (if any) was already loaded once at startup by
    `configure()`, not re-read from disk here.

    Real gap found via adversarial UI audit: NEITHER dashboard page showed
    whether the market was even open, forcing an operator to compute IST
    time and NSE session hours in their head before anything else on the
    page could be trusted. live.dhan.market_session.current_market_session
    already existed (used by the scheduler) but was never surfaced here.

    Honest about its own limitation, not just OPEN/PRE_OPEN/CLOSED: when
    no holiday calendar was configured (the default), this function has
    no way to know exchange holidays (see market_session.py's own
    documented limitation), so a holiday weekday during session hours
    would show OPEN -- stated explicitly rather than silently wrong. When
    `--schedule-config` WAS supplied, the state is cross-checked for real
    and a confirmed holiday correctly shows CLOSED."""
    from live.dhan.market_session import current_market_session

    session = current_market_session(holidays=_cached_holidays)
    state = session.state.value
    state_class = "tag-long" if state == "OPEN" else "tag-sim"
    if session.holiday_calendar_consulted:
        holiday_line = (
            f"NSE/BSE cash-market session hours (09:15-15:30 IST, weekdays), cross-checked against "
            f"{session.holiday_calendar_size} configured holiday date(s) from --schedule-config."
        )
    else:
        holiday_line = (
            "NSE/BSE cash-market session hours only (09:15-15:30 IST, weekdays) -- does NOT know exchange "
            "holidays (no --schedule-config was supplied); a holiday weekday during session hours would show OPEN."
        )
    return (
        '<div class="kv" style="max-width:640px;">'
        f'<div>Market status</div><div><span class="tag {state_class}">{state}</span></div>'
        f'<div>IST time</div><div>{session.as_of_ist.strftime("%Y-%m-%d %H:%M:%S")} ({session.as_of_ist.strftime("%A")})</div>'
        "</div>"
        f'<p class="muted">{holiday_line}</p>'
    )


def _broker_connectivity_banner() -> str:
    """Real gap found via news/market-intelligence architecture audit: the
    page-wide banner used to be a HARDCODED static string ("NOT connected
    to a live broker or feed"), unconditionally shown even while a genuine
    `paper-live --source dhan` session has a real, on_open-verified
    WebSocket connected -- the banner and the feed-status table just below
    it could contradict each other. Reads live.state_store's own
    feed_status rows (workstation.get_feed_status(), a LOCAL SQLite read,
    not a network call -- consistent with _market_status_banner()'s own
    "zero I/O to a live feed on page load" rule) to state the CURRENT
    truth instead of a fixed claim.

    LIVE PAPER-TRADING HARDENING mission, real gap found via dashboard
    truth audit: this fix's own OWN claim -- "a live feed IS connected"
    -- was itself STALE-blind, exactly the bug it was written to close
    for the OLD hardcoded-string version. A feed_status row's
    connection_state is whatever it was the LAST time a real session
    wrote it; once that session ends, the row is never updated again,
    so this banner kept asserting "IS connected" for HOURS after the
    process that connected it had exited (observed live: RELIANCE.NS's
    own row said CONNECTED while its data was already 3+ hours old, with
    zero python processes running). Now reuses _data_health_label() --
    the SAME staleness-aware composite the MARKET FEED table itself
    already uses -- so this banner can never claim "IS connected" for a
    feed that is, by the very definition this page uses one table down,
    not.

    "No real order can ever be placed here" stays unconditional -- that is
    a structural guarantee (no execute_trade/place_order/broker-credential
    path exists anywhere in this codebase, see this module's own
    docstring), true regardless of feed source, and is never the part that
    was wrong."""
    feed_status = workstation.get_feed_status()
    now = datetime.now(timezone.utc)
    healths = []
    for r in feed_status:
        if r.status != "LIVE":
            continue
        try:
            age_seconds = (now - datetime.fromisoformat(r.received_at)).total_seconds()
        except ValueError:
            age_seconds = None
        healths.append(_data_health_label(connection_state=r.connection_state, age_seconds=age_seconds)[0])

    if "CONNECTED" in healths:
        connectivity_text = "A LIVE broker feed IS connected (see the feed status table below)."
    elif "DEGRADED" in healths or "STALE" in healths:
        # Ambiguous case, distinct from an EXPLICIT disconnect signal below:
        # the row's own connection_state was CONNECTED, just aging -- a real
        # session likely ended without the process cleanly marking itself
        # disconnected, not a live signal of "currently disconnected".
        connectivity_text = (
            "A broker feed was connected but its last update is now stale "
            "(see the feed status table's own Data Health column below) -- no active live session appears to be running."
        )
    else:
        # No LIVE rows at all, or every one explicitly signals RECONNECTING/
        # DISCONNECTED/SOURCE_UNAVAILABLE -- an explicit, not merely aged, signal.
        connectivity_text = "NOT connected to a live broker or feed."
    return f'<div class="banner">SIMULATED PAPER TRADING &mdash; {connectivity_text} No real order can ever be placed here.</div>'


def _clock_skew_banner() -> str:
    """LIVE SYSTEM HARDENING mission, Part 11: real gap found -- clock skew
    (local machine vs Dhan server time) was measurable ONLY via the CLI's
    `readiness-check --deep`, never visible on the dashboard an operator
    would actually be watching during a live session. A live-confirmed
    ~130s skew on this machine silently biases every freshness/staleness
    check (see market_data/quality.py's from_bar_timestamp), so hiding it
    from the primary operator surface was a real observability gap.

    Reads live.workstation.get_clock_skew() -- a local SQLite read only,
    consistent with _market_status_banner()'s/_broker_connectivity_banner()'s
    own "zero network I/O on page load" rule. The actual measurement is
    taken elsewhere (readiness-check --deep, or paper-live --source dhan
    at session startup) and persisted; this function only ever displays
    the last-known reading, honestly labeled with how long ago it was
    taken so an operator can judge whether it's still representative."""
    record = workstation.get_clock_skew()
    if record is None:
        return (
            '<div class="kv" style="max-width:640px;">'
            '<div>Clock skew</div><div><span class="tag tag-sim">UNKNOWN</span></div>'
            "</div>"
            '<p class="muted">Never measured in this environment. Run <code>readiness-check --deep</code> or start a '
            "<code>paper-live --source dhan</code> session to measure real local-vs-Dhan-server clock skew.</p>"
        )
    measured_at = as_utc_aware(datetime.fromisoformat(record.measured_at))
    age_seconds = (datetime.now(timezone.utc) - measured_at).total_seconds()
    age_text = f"{age_seconds:,.0f}s ago" if age_seconds < 120 else f"{age_seconds / 60:,.1f} min ago"
    staleness_note = (
        " -- this reading itself is over 30 minutes old and may not reflect current conditions; skew is measured "
        "once per session/check, not continuously." if age_seconds > 1800 else ""
    )
    tag_class = {"PASS": "tag-long", "WARNING": "tag-warn", "FAIL": "tag-short"}.get(record.classification, "tag-sim")
    return (
        '<div class="kv" style="max-width:640px;">'
        f'<div>Clock skew</div><div><span class="tag {tag_class}">{html.escape(record.classification)}</span> '
        f"{html.escape(f'{record.skew_seconds:+.1f}s')}</div>"
        f"<div>Measured</div><div>{html.escape(age_text)}{html.escape(staleness_note)}</div>"
        "</div>"
        f'<p class="muted">{html.escape(record.detail)}</p>'
    )


def _scientific_verdict_banner() -> str:
    """Live-market-readiness audit finding: nowhere on this dashboard
    stated the actual, already-completed strategy research conclusion.
    The closest existing analog -- /intelligence's own "Profitability
    evidence" section -- reports a verdict over a much smaller, live
    decision_engine prediction sample (often INSUFFICIENT_DATA), which is
    a DIFFERENT finding and could easily be misread as "not enough data
    yet, might turn positive" by an operator who never saw the real
    research. The actual, decisive finding -- a real 41-symbol universe,
    5 years, 368+ backtested TrendMomentumBaseline trades, cross-checked
    against buy-and-hold and random-entry Monte Carlo baselines, plus a
    full follow-up mission testing exit and entry variants -- is stated
    here, on every page (via _page()), so an operator can never mistake
    this platform for a demonstrated profitable trading system. Static
    text: this is a completed, historical research finding, not a number
    that changes with today's market, so it is not queried from any
    store. See docs/SCIENTIFIC_FINAL_REPORT.md,
    docs/RESEARCH_FOUNDATION_FINAL_OUTPUT.md, and
    docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md for the full evidence."""
    return (
        '<div class="banner verdict-banner">'
        "<strong>SCIENTIFIC STRATEGY VERDICT: NO DEMONSTRATED EDGE.</strong> "
        "TrendMomentumBaseline (the active strategy) was backtested against a real 41-symbol universe over 5 years "
        "(368+ trades): negative mean return, underperforms buy-and-hold, underperformed by 96% of random-entry "
        "Monte Carlo iterations. A follow-up research program testing exit and entry variants found the same "
        "result. Do not interpret any signal, decision, or prediction shown on this dashboard as evidence of "
        "profitability. See docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md for the full evidence."
        "</div>"
    )


_NAV_ITEMS = (
    ("/", "Overview"),
    ("/signals", "Signals"),
    ("/portfolio", "Portfolio"),
    ("/fleet", "Fleet"),
    ("/system", "System"),
    ("/research", "Research"),
)


def _nav_bar(active_path: str) -> str:
    links = "".join(
        f'<a href="{href}" style="padding:8px 14px;font-size:13px;font-weight:600;text-decoration:none;'
        f'border-bottom:2px solid {"#4DA3FF" if href == active_path else "transparent"};'
        f'color:{"#F2F4F7" if href == active_path else "#66717D"};">{label}</a>'
        for href, label in _NAV_ITEMS
    )
    return (
        '<div style="display:flex;align-items:center;height:44px;padding:0 20px;border-bottom:1px solid #252D35;'
        f'background:#0B0E11;gap:4px;overflow-x:auto;">{links}'
        '<a href="/intelligence" style="margin-left:auto;padding:8px 14px;font-size:12px;color:#66717D;text-decoration:none;">Legacy intelligence view &rarr;</a>'
        "</div>"
    )


def _top_bar() -> str:
    return (
        '<div style="display:flex;align-items:center;height:56px;padding:0 20px;border-bottom:1px solid #252D35;'
        'background:#0B0E11;gap:24px;">'
        '<div style="display:flex;flex-direction:column;line-height:1.1;">'
        '<div style="font-size:14px;font-weight:600;letter-spacing:0.04em;">TRADING INTELLIGENCE</div>'
        '<div style="font-size:10px;color:#66717D;letter-spacing:0.08em;">RESEARCH &amp; PAPER-TRADING WORKSTATION</div>'
        "</div>"
        '<div style="margin-left:auto;font-size:10px;font-weight:600;letter-spacing:0.06em;padding:4px 9px;'
        'border-radius:4px;border:1px solid #4DA3FF55;color:#4DA3FF;background:#4DA3FF14;">PAPER</div>'
        "</div>"
    )


def _kill_switch_banner() -> str:
    """Shown on the live-workstation tabs only (Overview/Signals/
    Portfolio/System -- the ones live.workstation.get_live_engine()'s
    account/kill-switch state is actually about), NOT injected into the
    shared `_page()` shell: `/intelligence`/`/health` are a genuinely
    different subsystem (the shadow-run/decision_engine research
    pipeline's own account, dashboard/intelligence.py's own
    STATE_DB_PATH read) and already have their own equivalent (see
    intelligence_page()'s own kill_switch_section). A real regression
    was found and fixed here: calling get_live_engine() from every page
    (including /health, /intelligence -- which never touched it before)
    crashed those pages' own tests with a genuine
    sqlite3.ProgrammingError ("SQLite objects created in a thread can
    only be used in that same thread") the moment Starlette's
    TestClient dispatched a request to a different thread than the one
    that first cached the module-level live engine -- exactly the
    cross-thread hazard tests/test_dashboard.py's own
    `_isolated_live_engine` fixture already documents and works around
    for ITS pages, but /health and /intelligence's own test fixtures
    never needed to, because those pages never called this before.
    Reads workstation.get_live_sim_status() -- the SAME real, persisted
    kill-switch state /approve and /reject already check before
    acting."""
    status = workstation.get_live_sim_status()
    if not status["kill_switch_active"]:
        return ""
    reason = html.escape(status["kill_switch_reason"] or "")
    return f'<div class="banner kill-active">KILL SWITCH ACTIVE &mdash; {reason} &mdash; no new signal will be approved or executed.</div>'


def _risk_halt_banner() -> str:
    """Shown on the live-workstation tabs only -- same reasoning as
    `_kill_switch_banner()`. Reads workstation.get_risk_halt_reasons(),
    the real risk.engine.RiskEngine.account_level_halt_reasons() output,
    never fabricated."""
    risk_halt_reasons = workstation.get_risk_halt_reasons()
    if not risk_halt_reasons:
        return ""
    reasons_text = ", ".join(html.escape(r) for r in risk_halt_reasons)
    return (
        f'<div class="banner kill-active">RISK HALT ACTIVE &mdash; {reasons_text} &mdash; '
        f"a new signal would be REJECTED by risk.engine's own circuit breaker (separate from the kill switch above).</div>"
    )


def _fleet_mode_banner() -> str:
    """Dashboard truthfulness fix (OpenAI Intelligence Integration mission,
    Phase 14 / real defect disclosed in docs/LIVE_INTELLIGENCE_FORENSICS_
    2026-09-16.md #7): Overview/Signals/Portfolio/System read the FIXED
    default single-workstation DBs (live/workstation.py's module-level
    LIVE_STATE_DB_PATH etc.), never the per-symbol `runtime/<SYMBOL>/`
    stores a `fleet-supervise` session actually writes to -- verified live
    on 2026-09-16: these tabs showed week-old rows from a previous
    single-symbol session while a real 15-symbol fleet ran, correctly
    badged STALE (never fabricated) but misleading by omission (a viewer
    could easily miss that STALE here means "wrong data source", not
    merely "a few minutes old").

    Full aggregation across N independent per-symbol paper accounts into
    one Overview is a genuine architecture change (which account's
    equity/P&L is "the" number when there are 15 independent $100,000
    paper accounts? do open positions list per-symbol or merge?) -- not
    attempted here while a real live session is running, to avoid
    introducing an untested change into the exact pages operators are
    watching. This banner is the safe, additive fix available right now:
    an unmissable pointer to the ONE page that IS fleet-aware, on every
    page that is NOT, whenever fleet mode is actually configured (never
    shown otherwise -- a single-symbol workstation session is unaffected
    and sees nothing new)."""
    if _fleet_runtime_dir is None or not _fleet_symbols:
        return ""
    return (
        '<div class="banner kill-active">FLEET MODE ACTIVE &mdash; this page reads the default single-workstation '
        "database, NOT the running fleet's per-symbol runtime stores. "
        '<a href="/fleet">See the Fleet tab</a> for real data from the currently running symbols.</div>'
    )


def _page(body: str, *, active_path: str = "/") -> str:
    """UI integration (Claude Design "Trading Workstation" approved
    canvas): visual shell only -- dark charcoal/near-black background,
    Inter for UI text, IBM Plex Mono for numeric/financial values,
    restrained blue accent, the same green/red/amber/blue semantic
    colors the approved design specifies. Every banner below is the
    SAME real, pre-existing function (broker connectivity, clock skew,
    scientific verdict, market status) -- only their visual container
    changed, never their content or the real data source behind them.
    Still meta-refreshes (this project has no client-side framework and
    no WebSocket layer; see `/api/state` for the one piece of this page
    that DOES update without a full reload)."""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Trading Workstation (PAPER)</title>
<meta http-equiv="refresh" content="{_REFRESH_SECONDS}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: Inter, -apple-system, Segoe UI, sans-serif; background: #0B0E11; color: #F2F4F7; margin: 0; padding: 0; }}
  a {{ color: #4DA3FF; }}
  .content {{ padding: 24px 20px 40px; max-width: 1400px; }}
  .banner {{ background: #7a1f1f; color: #fff; padding: 10px 16px; font-weight: bold; margin: 0; }}
  .kill-active {{ background: #FF4D5A; color: #1A0505; }}
  .verdict-banner {{ background: #1A1508; color: #E7B84B; border-bottom: 1px solid #3a3316; font-weight: normal; padding: 10px 20px; }}
  .verdict-banner strong {{ font-weight: 700; }}
  h2 {{ border-bottom: 1px solid #252D35; padding-bottom: 6px; margin-top: 28px; font-size: 15px; font-weight: 600; }}
  h3 {{ color: #9AA4AF; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #252D35; font-size: 13px; }}
  th {{ color: #66717D; font-weight: 600; font-size: 10px; letter-spacing: 0.05em; text-transform: uppercase; }}
  td {{ font-family: 'IBM Plex Mono', monospace; }}
  td.label {{ font-family: Inter, sans-serif; font-weight: 600; }}
  .tag {{ display: inline-block; padding: 3px 9px; border-radius: 4px; font-size: 11px; font-weight: 600; font-family: 'IBM Plex Mono', monospace; }}
  .tag-mock {{ background: #1A2128; color: #9AA4AF; border: 1px solid #252D35; }}
  .tag-sim {{ background: #1A2128; color: #9AA4AF; border: 1px solid #252D35; }}
  .tag-long {{ background: #35C98A14; color: #35C98A; border: 1px solid #35C98A55; }}
  .tag-short {{ background: #F05D5E14; color: #F05D5E; border: 1px solid #F05D5E55; }}
  .tag-warn {{ background: #E7B84B14; color: #E7B84B; border: 1px solid #E7B84B55; }}
  form.inline {{ display: inline; }}
  button {{ padding: 7px 16px; border-radius: 5px; border: 1px solid #252D35; font-weight: 600; font-size: 12px; cursor: pointer; letter-spacing: 0.02em; }}
  button.approve {{ background: #35C98A14; color: #35C98A; border-color: #35C98A55; }}
  button.reject {{ background: #F05D5E14; color: #F05D5E; border-color: #F05D5E55; }}
  button.killswitch {{ background: #FF4D5A; color: #1A0505; border-color: #FF4D5A; }}
  button.reset {{ background: #11161B; color: #9AA4AF; }}
  input[type=text] {{ background: #0B0E11; border: 1px solid #252D35; color: #F2F4F7; padding: 6px 10px; border-radius: 5px; font-family: Inter, sans-serif; }}
  .muted {{ color: #66717D; font-size: 12px; }}
  .kv {{ display: grid; grid-template-columns: 220px 1fr; row-gap: 6px; max-width: 480px; font-size: 13px; }}
  .kv > div:nth-child(odd) {{ color: #66717D; }}
  .card {{ border: 1px solid #252D35; border-radius: 8px; padding: 16px; background: #11161B; }}
  .pill {{ display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 4px; }}
  .dot {{ width: 6px; height: 6px; border-radius: 50%; display: inline-block; }}
</style>
</head>
<body>
{_top_bar()}
{_nav_bar(active_path)}
{_broker_connectivity_banner()}
{_clock_skew_banner()}
{_scientific_verdict_banner()}
{_market_status_banner()}
<div class="content">
{body}
<p class="muted">Auto-refreshes every {_REFRESH_SECONDS}s. This page does not advance the market itself &mdash;
run <code>python main.py paper-live --symbol ... --interval ... --period ...</code> (or <code>fleet-supervise</code> for
multiple symbols) in a terminal to process bars and generate signals.</p>
</div>
</body>
</html>"""


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def _data_health_label(*, connection_state: str | None, age_seconds: float | None) -> tuple[str, str]:
    """LIVE SYSTEM HARDENING mission, Part 3 (live-data degradation
    policy): composes the mission's own desired operator-facing
    vocabulary -- CONNECTED / DEGRADED / STALE / RECONNECTING /
    DISCONNECTED / SOURCE_UNAVAILABLE -- purely from what feed_status
    ALREADY records (connection_state, now richer than a plain bool when
    the source exposes one -- see LiveSimPipeline._connection_state_label;
    and received_at, already shown as "Data Age"). No new persisted
    state, no new enforcement: the REAL gate against stale data acting
    on a new decision remains live/freshness.py's FreshnessPolicy inside
    the pipeline itself (proven live: a genuine STALE_SIGNAL_SUPPRESSED
    event was observed this session) -- this function is DISPLAY ONLY,
    a second, cruder read of the same underlying signal for an operator
    glancing at the dashboard, not a competing decision-maker.

    Thresholds are honest approximations, not a claim of matching the
    pipeline's own exact interval-derived threshold (feed_status does
    not record which interval a symbol is running at): 30s is
    FreshnessPolicy's own minimum_threshold floor (meaningful regardless
    of interval); 120s is that floor's default multiplier=2.0 applied to
    paper-live's own --interval default (1m) -- both real, existing
    numbers from live/freshness.py, not fabricated here. A caller
    running a longer interval will see DEGRADED/STALE reported more
    eagerly than their actual configured threshold -- erring toward
    caution, never toward hiding a real problem."""
    conn = (connection_state or "").upper()
    if conn == "FAILED":
        return "SOURCE_UNAVAILABLE", "tag-short"
    if conn == "RECONNECTING":
        return "RECONNECTING", "tag-warn"
    if conn in ("DISCONNECTED", "CONNECTING", "CLOSED", ""):
        return "DISCONNECTED", "tag-short"
    # conn == "CONNECTED" from here.
    if age_seconds is None:
        return "CONNECTED", "tag-long"
    if age_seconds > 120:
        return "STALE", "tag-short"
    if age_seconds > 30:
        return "DEGRADED", "tag-warn"
    return "CONNECTED", "tag-long"


def _decision_id_cell(entry) -> str:
    if entry.decision_id:
        return html.escape(entry.decision_id)
    return "<span class='muted'>&mdash;</span>"


def _feed_row(record) -> str:
    source_class = "tag-mock" if record.source == "MOCK" else "tag-long"  # reuse the LONG/green tag color for a real source, distinct from mock's blue
    status_class = "tag-sim" if record.status in ("SIMULATED", "HISTORICAL") else "tag-long"
    try:
        age_seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(record.received_at)).total_seconds()
        age_text = f"{age_seconds:,.1f}s"
    except ValueError:
        age_seconds = None
        age_text = "unknown"
    conn = record.connection_state or "UNKNOWN"
    conn_class = "tag-long" if conn == "CONNECTED" else "tag-short"
    health_label, health_class = _data_health_label(connection_state=record.connection_state, age_seconds=age_seconds)
    # AUTONOMOUS LIVE PAPER-TRADING HARDENING mission, dashboard truth
    # audit: this table had no price at all -- a real gap against the
    # mission's own "live prices" checklist item. last_price is None
    # for any row written before this column existed (old rows are
    # never backfilled, see state_store._ensure_column) -- shown
    # honestly as "n/a", never a fabricated 0 or blank.
    price_text = f"{record.last_price:,.2f}" if record.last_price is not None else "n/a"
    return (
        f"<tr><td>{html.escape(record.symbol)}</td>"
        f"<td><span class='tag {source_class}'>{html.escape(record.source)}</span></td>"
        f"<td><span class='tag {status_class}'>{html.escape(record.status)}</span></td>"
        f"<td><span class='tag {conn_class}'>{html.escape(conn)}</span></td>"
        f"<td><span class='tag {health_class}'>{html.escape(health_label)}</span></td>"
        f"<td>{price_text}</td>"
        f"<td>{html.escape(record.bar_timestamp)}</td>"
        f"<td>{age_text}</td></tr>"
    )


def _feed_health(record) -> tuple[str, str]:
    """Same grading `_feed_row` uses, exposed standalone for the
    Overview watchlist (UI integration) -- one call site, not a second
    competing implementation."""
    try:
        age_seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(record.received_at)).total_seconds()
    except ValueError:
        age_seconds = None
    return _data_health_label(connection_state=record.connection_state, age_seconds=age_seconds)


async def overview(request: Request) -> HTMLResponse:
    """UI integration (Claude Design "Trading Workstation" approved
    canvas) -- Overview tab. A real "watchlist" made of exactly the
    symbols this session has actually observed (live.workstation.
    get_feed_status() rows), each with its real last-known price and
    the SAME data-health grading the old MARKET FEED table used --
    never an arbitrary hardcoded symbol list. "Attention" is built
    entirely from real, already-existing signals (kill switch, risk
    halt, stale/disconnected feeds, critic rejections, pending
    approvals) -- nothing here is invented for the UI."""
    status = workstation.get_live_sim_status()
    pending = workstation.get_pending_approvals()
    feed_status = workstation.get_feed_status()
    critic_rejections = workstation.get_critic_rejections(limit=25)
    health = _collect_health(check_ollama=False)

    pending_by_symbol = {r.symbol: r for r in pending}

    def _watchlist_row(record) -> str:
        health_label, health_class = _feed_health(record)
        price_text = f"{record.last_price:,.2f}" if record.last_price is not None else "&mdash;"
        sig = pending_by_symbol.get(record.symbol)
        sig_badge = (
            f"<span class='tag tag-{sig.signal.side.value.lower()}' style='margin-left:6px;'>{sig.signal.side.value}</span>"
            if sig is not None else ""
        )
        return (
            f'<div style="display:flex;flex-direction:column;gap:2px;padding:8px 10px;border-radius:6px;'
            f'border-left:2px solid {"#4DA3FF" if sig is not None else "transparent"};">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-size:12px;font-weight:600;">{html.escape(record.symbol)}</span>{sig_badge}</div>'
            f'<div style="display:flex;justify-content:space-between;font-family:\'IBM Plex Mono\',monospace;font-size:11px;">'
            f'<span style="color:#9AA4AF;">{price_text}</span>'
            f'<span class="tag {health_class}" style="padding:1px 6px;">{html.escape(health_label)}</span></div></div>'
        )

    watchlist_html = "".join(_watchlist_row(r) for r in feed_status) or (
        '<p class="muted">No symbol has been observed yet &mdash; run <code>python main.py paper-live ...</code> '
        "or <code>fleet-supervise</code> to start tracking one.</p>"
    )

    attention_items: list[str] = []
    if status["kill_switch_active"]:
        attention_items.append(_attention_card("TRADING HALTED", "Kill switch active", "All new paper orders are blocked.", "#FF4D5A"))
    risk_halt_reasons = workstation.get_risk_halt_reasons()
    if risk_halt_reasons:
        attention_items.append(_attention_card("RISK HALT", "Risk circuit breaker active", ", ".join(html.escape(r) for r in risk_halt_reasons), "#E7B84B"))
    for r in pending:
        attention_items.append(_attention_card(
            "APPROVAL REQUIRED", html.escape(r.symbol),
            f"{r.signal.side.value} signal awaiting human approval, R:R {r.signal.risk_reward:.1f}", "#E7B84B",
        ))
    for record in feed_status:
        label, _cls = _feed_health(record)
        if label in ("STALE", "DEGRADED", "DISCONNECTED", "RECONNECTING", "SOURCE_UNAVAILABLE"):
            attention_items.append(_attention_card("DATA WARNING", html.escape(record.symbol), f"Feed health: {label}.", "#E7B84B"))
    if critic_rejections:
        attention_items.append(_attention_card(
            "CRITIC REJECTIONS", f"{len(critic_rejections)} recorded",
            "See Signals tab for the most recent deterministic critic rejections.", "#8B95A1",
        ))
    attention_html = "".join(attention_items) or '<div class="card" style="text-align:center;color:#66717D;font-size:12px;">NO ACTION REQUIRED</div>'

    account = workstation.get_account_state()
    system_summary = f"""
<div class="card" style="cursor:pointer;" onclick="location.href='/system'">
  <div style="display:flex;align-items:center;gap:8px;font-size:12px;font-weight:600;margin-bottom:10px;">
    <span class="dot" style="background:{_status_color(health['overall'])};"></span>SYSTEM &middot; {html.escape(health['overall'])}
  </div>
  <div style="display:flex;flex-direction:column;gap:6px;font-size:11px;color:#9AA4AF;">
    <div style="display:flex;justify-content:space-between;"><span>Kill switch</span><span>{'ACTIVE' if status['kill_switch_active'] else 'ARMED'}</span></div>
    <div style="display:flex;justify-content:space-between;"><span>Pending approvals</span><span>{status['pending_approvals_count']}</span></div>
    <div style="display:flex;justify-content:space-between;"><span>Open positions</span><span>{status['open_positions_count']}</span></div>
    <div style="display:flex;justify-content:space-between;"><span>Equity</span><span>{_fmt_money(account.equity)}</span></div>
  </div>
</div>"""

    body = f"""
{_kill_switch_banner()}
{_risk_halt_banner()}
{_fleet_mode_banner()}
<div style="display:grid;grid-template-columns:220px minmax(0,1fr) 280px;gap:20px;align-items:start;">
  <div style="display:flex;flex-direction:column;gap:2px;min-width:0;">
    <div style="font-size:10px;font-weight:700;letter-spacing:0.06em;color:#66717D;margin-bottom:8px;">WATCHLIST &mdash; observed this session</div>
    {watchlist_html}
  </div>
  <div style="min-width:0;">
    <p><a href="/intelligence">Market intelligence &amp; prediction performance &rarr;</a></p>
    <div class="card">
      <div style="font-size:13px;font-weight:600;margin-bottom:10px;">Reconciliation: {'OK' if status['reconciliation_ok'] else 'FAILED'}</div>
      <p class="muted">This Overview reads the SAME real, persisted paper-live workstation state as the Signals/Portfolio/System tabs &mdash;
      nothing here is a separate or simulated data source. See <a href="/signals">Signals</a> for the full pending-approval table and
      <a href="/portfolio">Portfolio</a> for account/positions/risk detail.</p>
    </div>
  </div>
  <div style="display:flex;flex-direction:column;gap:20px;min-width:0;">
    <div>
      <div style="font-size:13px;font-weight:600;margin-bottom:10px;">Attention</div>
      {attention_html}
    </div>
    {system_summary}
  </div>
</div>
"""
    return HTMLResponse(_page(body, active_path="/"))


def _attention_card(kind: str, title: str, detail: str, color: str) -> str:
    return (
        f'<div style="padding:12px 14px;border-radius:8px;background:#151B21;border-left:3px solid {color};margin-bottom:8px;">'
        f'<div style="font-size:10px;font-weight:700;letter-spacing:0.04em;color:{color};margin-bottom:4px;">{html.escape(kind)}</div>'
        f'<div style="font-size:13px;font-weight:600;margin-bottom:2px;">{title}</div>'
        f'<div style="font-size:12px;color:#9AA4AF;">{detail}</div></div>'
    )


def _status_color(status: str) -> str:
    return {"HEALTHY": "#35C98A", "DEGRADED": "#E7B84B", "SAFE_STOP": "#E7B84B", "FAILED": "#FF4D5A"}.get(status, "#8B95A1")


async def signals_page(request: Request) -> HTMLResponse:
    """UI integration -- Signals tab: the exact same real pending-
    approval data the old `/` page showed (live.workstation.
    get_pending_approvals()), plus the critic-rejection ledger, now with
    a link into a per-signal Trade Plan detail page
    (`/signals/{signal_id}`)."""
    status = workstation.get_live_sim_status()
    pending = workstation.get_pending_approvals()
    critic_rejections = workstation.get_critic_rejections(limit=25)

    market_rows = "".join(
        f"<tr><td class='label'>{html.escape(r.symbol)}</td><td><span class='tag tag-{r.signal.side.value.lower()}'>{r.signal.side.value}</span></td>"
        f"<td>{r.signal.reference_price:.2f}</td><td>{r.signal.generated_at}</td></tr>"
        for r in pending
    ) or "<tr><td colspan='4' class='muted'>No pending signals &mdash; nothing to show until paper-live generates one.</td></tr>"

    pending_rows = "".join(
        f"<tr><td class='label'><a href='/signals/{html.escape(r.signal_id)}'>{html.escape(r.signal_id[:12])}</a></td><td class='label'>{html.escape(r.symbol)}</td>"
        f"<td><span class='tag tag-{r.signal.side.value.lower()}'>{r.signal.side.value}</span></td>"
        f"<td>{r.signal.stop_price:.2f}</td><td>{r.signal.target_price:.2f}</td><td>{r.requested_quantity}</td>"
        f"<td>{r.signal.risk_reward:.1f}</td>"
        f"<td>{html.escape(r.expires_at)}</td>"
        f"<td>"
        f"<form class='inline' method='post' action='/approve'><input type='hidden' name='signal_id' value='{html.escape(r.signal_id)}'>"
        f"<button class='approve' type='submit'>APPROVE</button></form> "
        f"<form class='inline' method='post' action='/reject'><input type='hidden' name='signal_id' value='{html.escape(r.signal_id)}'>"
        f"<button class='reject' type='submit'>REJECT</button></form>"
        f"</td></tr>"
        for r in pending
    ) or "<tr><td colspan='9' class='muted'>No signals pending human approval.</td></tr>"

    critic_rejection_rows = "".join(
        f"<tr><td>{html.escape(r.rejected_at)}</td><td class='label'>{html.escape(r.symbol)}</td>"
        f"<td><span class='tag tag-short'>{html.escape(r.verdict)}</span></td>"
        f"<td>{html.escape(r.reasons[0]) if r.reasons else ''}</td>"
        f"<td>{html.escape(r.signal_id[:12])}</td></tr>"
        for r in critic_rejections
    ) or "<tr><td colspan='5' class='muted'>No signal has ever been rejected by the deterministic critic.</td></tr>"

    body = f"""
{_kill_switch_banner()}
{_risk_halt_banner()}
{_fleet_mode_banner()}
<h2>SIGNALS <span class="tag tag-mock">from pending approvals</span></h2>
<p class="muted">Derived from the latest signal seen for each symbol currently awaiting approval.</p>
<table><tr><th>Symbol</th><th>Direction</th><th>Reference Price</th><th>As Of</th></tr>{market_rows}</table>

<h2>SIGNALS / PENDING APPROVAL ({status['pending_approvals_count']})</h2>
<p class="muted">Click a Signal ID for the full trade plan, evidence, and risk assessment.</p>
<table><tr><th>Signal ID</th><th>Symbol</th><th>Dir.</th><th>Stop</th><th>Target</th><th>Qty</th><th>R:R</th><th>Expires</th><th>Action</th></tr>{pending_rows}</table>

<h2>CRITIC REJECTIONS (most recent 25)</h2>
<p class="muted">Signals the deterministic critic (critic.engine.evaluate, independent of decision_engine.rules.classify) blocked BEFORE risk sizing or any paper order was attempted &mdash; only present when this session's paper-live was started without --skip-critic.</p>
<table><tr><th>Rejected At</th><th>Symbol</th><th>Verdict</th><th>Reason</th><th>Signal ID</th></tr>{critic_rejection_rows}</table>
"""
    return HTMLResponse(_page(body, active_path="/signals"))


async def signal_detail_page(request: Request) -> HTMLResponse:
    """UI integration -- the design's "Trade Plan" detail view, backed
    entirely by real fields: strategy.signal.Signal (entry/stop/target/
    risk_reward/reason_codes), live.state_store.PendingApprovalRecord
    (requested_quantity/state/history -- history IS a real, persisted
    signal timeline), and a read-only recompute of the risk breakdown
    via the new live.workstation.get_risk_decision_for_pending() (same
    pure-function pattern live/prediction_recorder.py already uses).
    AI interpretation is honestly reported as NOT AVAILABLE for this
    path -- see this module's own integration report: the live
    paper-live loop's AI explanation (main.py::_try_ai_explain) is
    never persisted anywhere, only printed to the CLI at approval time,
    so there is no real value here to show without fabricating one."""
    signal_id = request.path_params["signal_id"]
    pending = {r.signal_id: r for r in workstation.get_pending_approvals()}
    record = pending.get(signal_id)
    if record is None:
        body = f"<p class='muted'>No pending signal with id starting {html.escape(signal_id[:12])} &mdash; it may have already been approved, rejected, or expired. See <a href='/signals'>Signals</a>.</p>"
        return HTMLResponse(_page(body, active_path="/signals"))

    sig = record.signal
    risk_decision = workstation.get_risk_decision_for_pending(record)

    evidence_rows = "".join(f"<li>{html.escape(_reason_code_label(rc.value))}</li>" for rc in sig.reason_codes) or "<li class='muted'>(none recorded)</li>"

    timeline_rows = "".join(
        f"<tr><td>{html.escape(ts)}</td><td class='label'>{html.escape(state)}</td></tr>"
        for state, ts in record.history
    ) or "<tr><td colspan='2' class='muted'>(no history recorded)</td></tr>"

    if risk_decision is not None:
        veto_text = ", ".join(v.value for v in risk_decision.veto_reasons) or "None"
        risk_block = f"""
<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;font-size:12px;padding:12px;border:1px solid #252D35;border-radius:8px;margin-bottom:18px;font-family:'IBM Plex Mono',monospace;">
  <div><div style="color:#66717D;font-size:10px;">POSITION SIZE</div>{risk_decision.position_size.quantity if risk_decision.position_size else 'n/a'} shares</div>
  <div><div style="color:#66717D;font-size:10px;">TOTAL RISK</div>{_fmt_money(risk_decision.risk_amount) if risk_decision.risk_amount is not None else 'n/a'} ({f'{risk_decision.risk_percent:.2f}%' if risk_decision.risk_percent is not None else 'n/a'})</div>
  <div><div style="color:#66717D;font-size:10px;">EXPOSURE</div>{f'{risk_decision.exposure.exposure_pct:.1f}%' if risk_decision.exposure is not None else 'n/a'}</div>
  <div><div style="color:#66717D;font-size:10px;">VETO REASONS</div>{html.escape(veto_text)}</div>
</div>
<p class="muted">Risk breakdown above is a live, read-only recompute of risk.engine.RiskEngine.evaluate(signal, account) &mdash; the exact same pure function the real approval path calls, run again here for display only (see live/workstation.py::get_risk_decision_for_pending). It cannot and does not change the approval, quantity, stop, or target.</p>"""
    else:
        risk_block = "<p class='muted'>Risk breakdown not available.</p>"

    capital = (record.requested_quantity * sig.reference_price) if record.requested_quantity else None
    body = f"""
{_kill_switch_banner()}
{_risk_halt_banner()}
{_fleet_mode_banner()}
<p><a href="/signals">&larr; back to Signals</a></p>
<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px;">
  <div>
    <div style="font-size:18px;font-weight:700;">{html.escape(sig.symbol)}</div>
    <div style="font-family:'IBM Plex Mono',monospace;font-size:20px;font-weight:600;margin-top:4px;">{sig.reference_price:.2f}</div>
  </div>
  <div style="display:flex;gap:8px;">
    <span class="tag tag-sim">{html.escape(record.state)}</span>
    <span class="tag tag-{sig.side.value.lower()}">{sig.side.value}</span>
  </div>
</div>

<h2>TRADE PLAN</h2>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:22px;padding:12px;border:1px solid #252D35;border-radius:8px;font-family:'IBM Plex Mono',monospace;font-size:13px;">
  <div><div style="color:#66717D;font-size:10px;">ACTION</div>{sig.side.value} (BUY)</div>
  <div><div style="color:#66717D;font-size:10px;">ORDER TYPE</div>MARKET (next bar open)</div>
  <div><div style="color:#66717D;font-size:10px;">STATUS</div>{html.escape(record.state)}</div>
  <div><div style="color:#66717D;font-size:10px;">ENTRY (reference)</div>{sig.reference_price:.2f}</div>
  <div><div style="color:#F05D5E;font-size:10px;">STOP</div>{sig.stop_price:.2f}</div>
  <div><div style="color:#35C98A;font-size:10px;">TARGET</div>{sig.target_price:.2f}</div>
  <div><div style="color:#66717D;font-size:10px;">QUANTITY</div>{record.requested_quantity} shares</div>
  <div><div style="color:#66717D;font-size:10px;">REQUIRED CAPITAL</div>{_fmt_money(capital) if capital is not None else 'n/a'}</div>
  <div><div style="color:#66717D;font-size:10px;">R:R</div>1 : {sig.risk_reward:.2f}</div>
</div>
<p class="muted">No limit/stop order types exist &mdash; approved signals fill at market on the next bar. Expires (APPROVAL_EXPIRED) at {html.escape(record.expires_at)} if not approved in time.</p>

<h2>TECHNICAL EVIDENCE</h2>
<p class="muted">Deterministic reason codes from strategy.signal.Signal.reason_codes &mdash; the actual basis for this signal, not an AI narrative.</p>
<ul>{evidence_rows}</ul>

<h2>RISK ASSESSMENT</h2>
{risk_block}

<h2>AI INTERPRETATION</h2>
<p class="muted">NOT AVAILABLE for this signal. The live paper-live approval loop's optional AI explanation
(main.py's <code>_try_ai_explain</code>, shown only in the CLI at approval time) is never persisted to any
store for this execution path, so there is no real value to show here &mdash; shown honestly as unavailable
rather than fabricated. (Decisions generated via <code>decide</code>/<code>shadow-run</code> DO persist a real
narrative; see <a href="/research">Research</a> for a symbol that has one.)</p>

<h2>SIGNAL TIMELINE</h2>
<table><tr><th>Time</th><th>State</th></tr>{timeline_rows}</table>

<h2>EXIT CONDITIONS</h2>
<p class="muted">If approved and filled, this becomes an open position that closes automatically on either level being hit:
target {sig.target_price:.2f} &rarr; exit_reason TARGET, or stop {sig.stop_price:.2f} &rarr; exit_reason STOP
(paper.models.Position.exit_reason / backtesting.trade.ExitReason -- the same real field Portfolio's own Open Positions table reads).
Not approved before {html.escape(record.expires_at)} &rarr; state APPROVAL_EXPIRED, the signal never enters a position at all.</p>
"""
    return HTMLResponse(_page(body, active_path="/signals"))


def _reason_code_label(code: str) -> str:
    return code.replace("_", " ").capitalize()


async def portfolio_page(request: Request) -> HTMLResponse:
    """UI integration -- Portfolio &amp; Risk tab: the same real ACCOUNT/
    RISK/POSITIONS/JOURNAL data the old `/` page showed, restyled.
    Per-position "current price"/"P&L" are a pure arithmetic readout
    (current - entry) * qty of two already-real numbers (Position.
    entry_price and the matching feed_status.last_price) -- not a new
    trading computation, and shown as "n/a" when no live price for that
    symbol has been observed."""
    status = workstation.get_live_sim_status()
    positions = workstation.get_positions()
    account = workstation.get_account_state()
    risk = workstation.get_risk_state()
    journal = workstation.get_trade_journal()
    feed_status = {r.symbol: r for r in workstation.get_feed_status()}

    def _position_row(p) -> str:
        feed = feed_status.get(p.symbol)
        current = feed.last_price if feed is not None else None
        if current is not None:
            pnl = (current - p.entry_price) * p.quantity
            pnl_color = "#35C98A" if pnl >= 0 else "#F05D5E"
            current_text = f"{current:,.2f}"
            pnl_text = f"{'+' if pnl >= 0 else ''}{_fmt_money(pnl)}"
        else:
            current_text, pnl_text, pnl_color = "n/a", "n/a", "#9AA4AF"
        return (
            f"<tr><td class='label'>{html.escape(p.symbol)}</td><td>{p.quantity}</td><td>{p.entry_price:.2f}</td>"
            f"<td>{current_text}</td><td>{p.stop_price:.2f} / {p.target_price:.2f}</td>"
            f"<td style='color:{pnl_color};'>{pnl_text}</td><td>{p.entry_time}</td></tr>"
        )

    position_rows = "".join(_position_row(p) for p in positions) or "<tr><td colspan='7' class='muted'>No open positions.</td></tr>"

    journal_rows = "".join(
        f"<tr><td>{e.created_at}</td><td class='label'>{html.escape(e.symbol)}</td><td>{html.escape(e.outcome.value)}</td>"
        f"<td>{html.escape(e.signal_id[:12])}</td><td>{_decision_id_cell(e)}</td></tr>"
        for e in sorted(journal, key=lambda e: e.created_at, reverse=True)[:25]
    ) or "<tr><td colspan='5' class='muted'>No journal entries yet.</td></tr>"

    body = f"""
{_kill_switch_banner()}
{_risk_halt_banner()}
{_fleet_mode_banner()}
<h2>ACCOUNT</h2>
<div class="kv">
<div>Initial Capital</div><div>{_fmt_money(account.initial_capital)}</div>
<div>Cash</div><div>{_fmt_money(account.cash)}</div>
<div>Equity</div><div>{_fmt_money(account.equity)}</div>
<div>Realized P&amp;L</div><div>{_fmt_money(account.realized_pnl)}</div>
<div>Open P&amp;L</div><div>{_fmt_money(account.unrealized_pnl)}</div>
<div>Daily P&amp;L</div><div>{_fmt_money(account.daily_pnl)}</div>
<div>Drawdown</div><div>{account.current_drawdown_pct:.2f}%</div>
<div>Consecutive Losses</div><div>{account.consecutive_losses}</div>
<div>Reconciliation</div><div>{'OK' if status['reconciliation_ok'] else 'FAILED'}</div>
</div>

<h2>RISK</h2>
<div class="kv">
<div>Consecutive Losses</div><div>{risk['consecutive_losses']} / {risk['max_consecutive_losses']} (hard limit {risk['consecutive_loss_hard_limit']})</div>
<div>Drawdown</div><div>{risk['current_drawdown_pct']:.2f}% / max {risk['max_drawdown_pct']:.2f}%</div>
<div>Daily P&amp;L</div><div>{_fmt_money(risk['daily_pnl'])} / max loss {risk['max_daily_loss_pct']:.2f}%</div>
<div>Open Positions</div><div>{risk['open_positions']}</div>
</div>

<h2>OPEN POSITIONS ({len(positions)})</h2>
<p class="muted">Current price/P&amp;L are read from this symbol's own last observed feed price (live.workstation.get_feed_status()) &mdash; "n/a" when no live price has been observed for that symbol.</p>
<table><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Current</th><th>Stop / Target</th><th>P&amp;L</th><th>Entry Time</th></tr>{position_rows}</table>

<h2>JOURNAL (most recent 25)</h2>
<table><tr><th>Time</th><th>Symbol</th><th>Outcome</th><th>Signal</th><th>Decision ID</th></tr>{journal_rows}</table>
"""
    return HTMLResponse(_page(body, active_path="/portfolio"))


async def fleet_page(request: Request) -> HTMLResponse:
    """UI integration -- Fleet tab: real data from live/fleet_summary.py
    (this project's own existing multi-symbol fleet-reporting module,
    reused verbatim -- not a second fleet-monitoring implementation),
    read against an operator-configured --fleet-runtime-dir. Per-symbol
    DATA health reuses each symbol's own isolated state.db feed_status
    row (live/runtime_layout.py's own isolation, same _feed_health()
    grading the rest of this dashboard uses). PROCESS is a genuinely
    separate signal (adversarial hardening pass, 2026-09-18): the
    worker's own heartbeat.json age, read directly off disk -- real,
    cross-process, never fabricated -- but deliberately NOT the same
    claim as "the OS process itself is alive" (the dashboard still
    cannot inspect another process's PID/liveness directly; only
    fleet-supervise's own console output can answer THAT). Shown as a
    raw age, not an invented ALIVE/STALE judgment (see the inline
    comment where it's computed for why). Never conflated with DATA
    health -- a fresh heartbeat proves the worker's loop is running, not
    that its feed is connected or its data is current."""
    if _fleet_runtime_dir is None or not _fleet_symbols:
        body = (
            '<h2>FLEET</h2>'
            '<p class="muted">Not configured. Start the dashboard with <code>--fleet-runtime-dir</code> and '
            '<code>--fleet-watchlist-file</code> (or <code>--fleet-symbols</code>) to show real fleet-supervisor data here. '
            "See <code>python main.py fleet-supervise</code>/<code>fleet-summary</code>.</p>"
        )
        return HTMLResponse(_page(body, active_path="/fleet"))

    from live.fleet_summary import summarize_fleet_session
    from live.runtime_layout import symbol_runtime_paths
    from live.state_store import LiveStateStore

    summary = summarize_fleet_session(_fleet_runtime_dir, _fleet_symbols)

    rows = []
    healthy = 0
    degraded = 0
    exceptions = []
    for s in summary.per_symbol:
        paths = symbol_runtime_paths(_fleet_runtime_dir, s.symbol)
        # Adversarial hardening pass (2026-09-18): a genuine, narrow
        # PROCESS signal, structurally distinct from DATA health above --
        # this is the worker's own heartbeat.json (live/heartbeat.py),
        # readable cross-process since it's just a file on disk. Shown as
        # a raw age, deliberately NOT classified into an ALIVE/STALE
        # judgment: unlike bar-data freshness (which reuses live/
        # freshness.py's real, established 30s/120s thresholds), no
        # existing threshold for heartbeat staleness exists anywhere in
        # this project to reuse, and inventing one here would be exactly
        # the "new threshold merely to make the dashboard look better"
        # this pass was told not to do. An operator sees the real number
        # and judges for themselves -- never fabricated, never conflated
        # with "the feed/data is healthy" (see the module docstring
        # above: process alive != feed healthy != data fresh).
        process_text = "NO HEARTBEAT"
        if paths.heartbeat_path.exists():
            try:
                import json as _json
                heartbeat_data = _json.loads(paths.heartbeat_path.read_text())
                written_at = datetime.fromisoformat(heartbeat_data["written_at"])
                heartbeat_age = (datetime.now(timezone.utc) - written_at).total_seconds()
                process_text = f"heartbeat {heartbeat_age:,.0f}s ago (pid={heartbeat_data.get('pid', '?')})"
            except (OSError, ValueError, KeyError):
                process_text = "heartbeat file unreadable"
        data_label, data_class = "NOT AVAILABLE", "tag-sim"
        if paths.state_db.exists():
            store = LiveStateStore(paths.state_db)
            try:
                rows_status = store.list_feed_status()
            finally:
                store.close()
            own = next((r for r in rows_status if r.symbol == s.symbol), None)
            if own is not None:
                data_label, data_class = _feed_health(own)
        # 15-symbol live-fleet validation mission found a real defect: an
        # earlier version required data_label in ("CONNECTED", "LIVE")
        # only, and a continuously-healthy fleet oscillated "0 / 15
        # HEALTHY" -> "15 / 15" within 36 seconds, because `--interval 1m`
        # legitimately swings a feed's own last-bar age between ~0s and
        # ~60s every cycle, repeatedly crossing _data_health_label's 30s
        # DEGRADED floor. A LATER fix folded DEGRADED into "healthy" to
        # stop the false alarm -- but that made DEGRADED indistinguishable
        # from genuinely fresh data in the rollup count, which is its own
        # truthfulness problem (adversarial hardening pass, 2026-09-18):
        # HEALTHY and DEGRADED are two different things by this project's
        # OWN definition (_data_health_label's docstring) and must be
        # counted separately, not collapsed either direction. Neither
        # count changes the 30s/120s thresholds themselves (still the
        # real, existing live/freshness.py-derived numbers, never
        # fabricated) -- only how the two real buckets are ROLLED UP.
        is_healthy = s.log_found and data_label in ("CONNECTED", "LIVE")
        is_degraded = s.log_found and data_label == "DEGRADED"
        if is_healthy:
            healthy += 1
        elif is_degraded:
            degraded += 1
        else:
            exceptions.append((s.symbol, f"log_found={s.log_found}, db_found={s.db_found}, data={data_label}"))
        pnl_color = "#35C98A" if s.net_pnl >= 0 else "#F05D5E"
        rows.append(
            f"<tr><td class='label'>{html.escape(s.symbol)}</td>"
            f"<td><span class='tag {data_class}'>{html.escape(data_label)}</span></td>"
            f"<td><span class='tag tag-sim'>{html.escape(process_text)}</span></td>"
            f"<td>{s.bars_processed}</td><td>{s.signals}</td><td>{s.trades}</td>"
            f"<td style='color:{pnl_color};'>{s.net_pnl:+,.2f}</td></tr>"
        )

    exception_html = "".join(
        f'<div style="padding:12px 16px;border-radius:8px;border-left:3px solid #E7B84B;background:#151B21;margin-bottom:8px;">'
        f'<div style="font-size:10px;font-weight:700;letter-spacing:0.04em;color:#E7B84B;margin-bottom:3px;">EXCEPTION &mdash; {html.escape(sym)}</div>'
        f'<div style="font-size:13px;">{html.escape(reason)}</div></div>'
        for sym, reason in exceptions
    )

    total = len(summary.per_symbol)
    rollup_color = "#35C98A" if healthy == total else ("#E7B84B" if healthy + degraded == total else "#F05D5E")
    degraded_text = f", {degraded} DEGRADED" if degraded else ""
    body = f"""
<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:14px;">
  <div style="font-size:15px;font-weight:600;">Fleet</div>
  <div style="font-size:13px;font-weight:600;color:{rollup_color};">{healthy} / {total} HEALTHY{degraded_text}</div>
</div>
<p class="muted">Runtime dir: {html.escape(str(_fleet_runtime_dir))}. "PROCESS" shows the worker's own heartbeat.json age (real, read directly
off disk) &mdash; NOT a direct OS-process-liveness check (the dashboard is a separate process from fleet-supervise and cannot inspect
another process's PID; only fleet-supervise's own console output can answer that). A fresh heartbeat proves the worker's own loop is
running; it says nothing about whether its FEED is connected or its DATA is current &mdash; those are the separate "Data" column.
Bars/Signals/Trades/P&amp;L are read via live/fleet_summary.py, the same module <code>fleet-summary</code> uses.
HEALTHY means data age is under 30s (this project's own FreshnessPolicy floor); DEGRADED means the feed and worker are alive and
data IS arriving, just not within the last 30s (normal, expected sawtooth for a 1-minute bar cadence) &mdash; shown as its own count,
never silently folded into HEALTHY or treated as a fault.</p>
{exception_html}
<table><tr><th>Symbol</th><th>Data</th><th>Process</th><th>Bars</th><th>Signals</th><th>Trades</th><th>Net P&amp;L</th></tr>{"".join(rows)}</table>
"""
    return HTMLResponse(_page(body, active_path="/fleet"))


def _collect_health(*, check_ollama: bool = True) -> dict:
    """`check_ollama=False` (used by the Overview page's own summary
    card, which every page load renders) skips the one real network
    probe collect_system_health() can make -- a localhost Ollama
    connection attempt -- so the primary landing page never blocks on
    it. The System tab (an operator's own explicit request to see
    health) keeps the full, real check, exactly like the pre-existing
    `/health` route always has."""
    from core.health import collect_system_health

    db_paths = {
        "experiments": PROJECT_ROOT / "data" / "experiments.db",
        "decision_engine": intelligence.DECISIONS_DB_PATH,
        "live_state": intelligence.STATE_DB_PATH,
        "promotion_gate": PROJECT_ROOT / "data" / "promotion_gate.db",
        "paper": intelligence.PAPER_DB_PATH,
        "scheduler": intelligence.SCHEDULER_DB_PATH,
        "predictions": intelligence.PREDICTIONS_DB_PATH,
        "research": intelligence.RESEARCH_DB_PATH,
        "scanner": intelligence.SCANNER_DB_PATH,
        "regime": PROJECT_ROOT / "data" / "market_regime.db",
    }
    health = collect_system_health(db_paths=db_paths, probe_dir=PROJECT_ROOT, check_ollama=check_ollama)
    return {
        "overall": health.overall.value,
        "components": [{"name": c.name, "status": c.status.value, "detail": c.detail} for c in health.components],
    }


def _ai_status_section() -> str:
    """OpenAI Intelligence Integration mission, Phase 14: honest AI status.

    Reads settings + the real llm/budget.py ledger only -- never claims AI
    is "active" beyond what those actually show, and never makes a network
    call from a page load (no models.retrieve() here; that's `ai-health`'s
    job, run deliberately from the CLI). Never renders the API key or any
    request/response content -- the ledger schema has no column for either."""
    import os

    from core.config import LLMProvider, get_settings
    from llm import budget

    settings = get_settings()
    provider = settings.llm_provider.value
    is_openai = settings.llm_provider == LLMProvider.OPENAI
    key_configured = bool(os.environ.get("OPENAI_API_KEY"))

    if is_openai:
        available = "AVAILABLE" if (key_configured and settings.openai_enabled) else "UNAVAILABLE"
        avail_class = "tag-long" if available == "AVAILABLE" else "tag-warn"
    else:
        available = "NOT ACTIVE"
        avail_class = "tag-sim"

    summary = budget.summarize_today()
    last_call = summary["last_call"]
    last_call_row = (
        f"{html.escape(last_call['ts_utc'])} &mdash; {html.escape(last_call['status'])} "
        f"({html.escape(str(last_call['model']))}, {last_call['latency_ms']:.0f}ms)"
        if last_call is not None and last_call["latency_ms"] is not None
        else (f"{html.escape(last_call['ts_utc'])} &mdash; {html.escape(last_call['status'])}" if last_call is not None else "none recorded")
    )

    return f"""
<h2>AI INTELLIGENCE STATUS</h2>
<p class="muted">Advisory-only layer (decision narration, signal explanation, research summaries, decision review) &mdash;
never in the live trading/critic/risk/execution path. Real data from llm/provider.py's active provider and the
llm/budget.py call ledger, not a static claim.</p>
<table>
<tr><td class="label">AI Provider</td><td>{html.escape(provider)}</td></tr>
<tr><td class="label">Model</td><td>{html.escape(settings.openai_model if is_openai else settings.chat_model)}</td></tr>
<tr><td class="label">Status</td><td><span class="tag {avail_class}">{available}</span></td></tr>
<tr><td class="label">OPENAI_API_KEY configured</td><td>{'yes' if key_configured else 'no'}</td></tr>
<tr><td class="label">Calls today</td><td>{summary['calls_today']} ({summary['successes_today']} succeeded)</td></tr>
<tr><td class="label">Last call</td><td>{last_call_row}</td></tr>
</table>
<p class="muted">Run <code>python main.py ai-health</code> for a live connectivity check (no completion cost).</p>
"""


async def system_page(request: Request) -> HTMLResponse:
    """UI integration -- System tab: the SAME core.health.
    collect_system_health() the existing `/health` route already uses
    (one shared health source, not a second implementation), plus the
    MARKET FEED table the old `/` page showed and the kill-switch
    control panel."""
    health = _collect_health()
    feed_status = workstation.get_feed_status()
    status = workstation.get_live_sim_status()

    tag_class = {"HEALTHY": "tag-long", "DEGRADED": "tag-warn", "FAILED": "tag-short", "DISABLED": "tag-sim", "UNKNOWN": "tag-sim"}
    health_rows = "".join(
        f"<tr><td class='label'>{html.escape(c['name'])}</td>"
        f"<td><span class='tag {tag_class.get(c['status'], 'tag-sim')}'>{html.escape(c['status'])}</span></td>"
        f"<td class='muted' style='font-family:Inter,sans-serif;'>{html.escape(c['detail'])}</td></tr>"
        for c in health["components"]
    )

    feed_rows = "".join(_feed_row(r) for r in feed_status) or (
        "<tr><td colspan='8' class='muted'>No market data processed yet in this session &mdash; "
        "run <code>python main.py paper-live ...</code> to start a feed.</td></tr>"
    )

    overall_class = tag_class.get(health["overall"], "tag-sim") if health["overall"] != "SAFE_STOP" else "tag-warn"
    kill_form = (
        '<form class="inline" method="post" action="/kill-switch/reset">'
        '<button class="reset" type="submit">Reset kill switch</button></form>'
        if status["kill_switch_active"] else
        '<form class="inline" method="post" action="/kill-switch/activate">'
        '<input type="text" name="reason" placeholder="reason (optional)">'
        '<button class="killswitch" type="submit">Activate kill switch</button></form>'
    )

    body = f"""
{_kill_switch_banner()}
{_risk_halt_banner()}
{_fleet_mode_banner()}
<h2>SYSTEM HEALTH</h2>
<p>Overall status: <span class="tag {overall_class}">{html.escape(health['overall'])}</span></p>
<table><tr><th>Component</th><th>Status</th><th>Detail</th></tr>{health_rows}</table>
<p class="muted">Same source as <code>python main.py health</code> and <a href="/health">/health</a> (core/health.py).</p>

{_ai_status_section()}

<h2>MARKET FEED</h2>
<p class="muted">The last bar actually delivered by whatever is driving the feed (the paper-live CLI, in another process) &mdash; never fabricated here.</p>
<table><tr><th>Symbol</th><th>Source</th><th>Status</th><th>Connection</th><th>Data Health</th><th>Last Price</th><th>Last Bar</th><th>Data Age</th></tr>{feed_rows}</table>

<h2>KILL SWITCH <span class="tag tag-sim">{'ACTIVE' if status['kill_switch_active'] else 'INACTIVE'}</span></h2>
<p class="muted">Halts all new paper order submission immediately. Existing open positions remain until manually closed.</p>
{kill_form}
"""
    return HTMLResponse(_page(body, active_path="/system"))


async def research_page(request: Request) -> HTMLResponse:
    """UI integration -- Research tab: a thin symbol picker over the
    SAME watchlist source the Overview tab uses (real, observed
    symbols), linking into the existing, unmodified `/intelligence/
    {{symbol}}` decision-detail page rather than duplicating its logic
    -- that page already shows real scanner evidence, research (news/
    sector/AI summary), and prediction history."""
    feed_status = workstation.get_feed_status()
    symbols = sorted({r.symbol for r in feed_status})
    if not symbols:
        try:
            from market_data.universe import MarketUniverse

            watchlist_path = PROJECT_ROOT / "market_data" / "watchlists" / "starter_nse.yaml"
            if watchlist_path.exists():
                symbols = list(MarketUniverse.from_yaml_file(str(watchlist_path)).symbols)
        except Exception:  # noqa: BLE001 -- Research page must render even if the optional starter watchlist is missing/malformed
            symbols = []

    chips = "".join(
        f'<a href="/intelligence/{html.escape(sym)}" style="padding:6px 12px;border-radius:5px;font-size:12px;font-weight:600;'
        f'text-decoration:none;border:1px solid #252D35;color:#9AA4AF;">{html.escape(sym)}</a>'
        for sym in symbols
    ) or '<p class="muted">No symbols observed yet, and no starter watchlist found.</p>'

    body = f"""
<h2>RESEARCH</h2>
<p class="muted">Select a symbol for its full decision history, scanner evidence, research (news/sector/AI summary), and
prediction history &mdash; all real, persisted data from <a href="/intelligence">Market Intelligence</a>, unchanged.</p>
<div style="display:flex;gap:6px;margin-bottom:20px;flex-wrap:wrap;">{chips}</div>
"""
    return HTMLResponse(_page(body, active_path="/research"))


async def api_state(request: Request) -> JSONResponse:
    """UI integration -- Live Data UX requirement ("do not refresh the
    entire page; update only changed values"). A small, read-only JSON
    snapshot of exactly the same real fields the top status bar and
    Overview watchlist already render server-side -- polled by a small
    vanilla-JS snippet to update ONLY those DOM nodes in place, no
    framework, no WebSocket (this project has neither), no full page
    reload. Same local-SQLite-only, zero-network-fetch discipline as
    every other read in this module."""
    status = workstation.get_live_sim_status()
    feed_status = workstation.get_feed_status()
    prices = []
    for r in feed_status:
        label, _cls = _feed_health(r)
        prices.append({"symbol": r.symbol, "price": r.last_price, "health": label})
    return JSONResponse({
        "kill_switch_active": status["kill_switch_active"],
        "pending_approvals_count": status["pending_approvals_count"],
        "open_positions_count": status["open_positions_count"],
        "prices": prices,
        "as_of": datetime.now(timezone.utc).isoformat(),
    })


async def approve(request: Request) -> RedirectResponse:
    form = await request.form()
    signal_id = form.get("signal_id", "")
    if signal_id:
        workstation.approve_pending_signal(signal_id, reason="approved via dashboard")
    return RedirectResponse("/", status_code=303)


async def reject(request: Request) -> RedirectResponse:
    form = await request.form()
    signal_id = form.get("signal_id", "")
    if signal_id:
        workstation.reject_pending_signal(signal_id, reason="rejected via dashboard")
    return RedirectResponse("/", status_code=303)


async def kill_switch_activate(request: Request) -> RedirectResponse:
    form = await request.form()
    reason = form.get("reason") or f"dashboard activation at {datetime.now(timezone.utc).isoformat()}"
    workstation.activate_kill_switch(reason=reason)
    return RedirectResponse("/", status_code=303)


async def kill_switch_reset(request: Request) -> RedirectResponse:
    workstation.reset_kill_switch()
    return RedirectResponse("/", status_code=303)


async def intelligence_page(request: Request) -> HTMLResponse:
    """Phase 26 -- a READ-ONLY snapshot of the Phase 18-25 intelligence
    pipeline's last persisted scan/decision/prediction state. No market
    data fetch, no LLM call, and no store write happens on this GET --
    see dashboard/intelligence.py's own module docstring. Nothing here
    can place an order; there is no action route on this page at all."""
    scan = intelligence.get_latest_scan()
    learning_snapshot = intelligence.get_learning_snapshot()
    paper_snapshot = intelligence.get_paper_execution_snapshot()
    scheduler_snapshot = intelligence.get_scheduler_status_snapshot()
    kill_switch = intelligence.get_kill_switch_status()

    # Same "impossible to miss" posture as the root `/` page's own kill
    # switch banner -- this page shows the shadow-run/--paper-execute
    # account (the one this project's risk-halt/kill-switch fixes concern),
    # so it must never be silent about the switch that gates it. Found
    # missing entirely via a real, running-dashboard adversarial UI audit.
    kill_banner = ""
    if kill_switch["active"]:
        reason = html.escape(kill_switch["reason"] or "")
        kill_banner = f'<div class="banner kill-active">KILL SWITCH ACTIVE &mdash; {reason} &mdash; no new signal will be approved or executed.</div>'
    kill_switch_section = f"<h2>KILL SWITCH <span class=\"tag tag-sim\">{'ACTIVE' if kill_switch['active'] else 'INACTIVE'}</span></h2>"

    if scan is None:
        candidates_section = (
            "<p class='muted'>No scan has been run yet &mdash; run "
            "<code>python main.py scan --symbols ...</code> first.</p>"
        )
    else:
        scan_meta = (
            "<div class='kv'>"
            f"<div>As of</div><div>{html.escape(scan.as_of.isoformat())}</div>"
            f"<div>Universe</div><div>{html.escape(scan.universe_mode)} ({scan.universe_size} symbols)</div>"
            f"<div>Config version</div><div>{html.escape(scan.config_version)}</div>"
            f"<div>Candidates</div><div>{len(scan.candidates)}</div>"
            "</div>"
        )
        candidate_rows = []
        for candidate in scan.candidates:
            decision = intelligence.get_latest_decision(candidate.symbol)
            if decision is not None:
                decision_class = "tag-long" if decision.label.value == "BUY" else "tag-sim"
                decision_cell = (
                    f"<span class='tag {decision_class}'>{html.escape(decision.label.value)}</span> "
                    f"<span class='muted'>{html.escape(decision.as_of.isoformat())}</span>"
                )
                # Phase 32: data_source/data_status only exist on a Decision whose
                # market_context was populated (currently only shadow-run does this --
                # standalone `decide` does not build a MarketContext at all) -- shown
                # honestly as "n/a", never fabricated, when absent.
                if decision.market_context is not None and decision.market_context.data_status is not None:
                    status_class = "tag-long" if decision.market_context.data_status == "LIVE" else "tag-sim"
                    data_cell = f"<span class='tag {status_class}'>{html.escape(decision.market_context.data_source or '')} / {html.escape(decision.market_context.data_status)}</span>"
                else:
                    data_cell = "<span class='muted'>n/a</span>"
                # Phase 34: decision_engine.confidence's real, deterministic score --
                # never fabricated when absent (a Decision predating Phase 34, or
                # NO_ACTION with no scanner_evidence, has confidence=None).
                confidence_cell = f"{decision.confidence:.0%}" if decision.confidence is not None else "<span class='muted'>n/a</span>"
            else:
                decision_cell = "<span class='muted'>no decision recorded</span>"
                data_cell = "<span class='muted'>n/a</span>"
                confidence_cell = "<span class='muted'>n/a</span>"
            candidate_rows.append(
                f"<tr><td><a href='/intelligence/{html.escape(candidate.symbol)}'>{html.escape(candidate.symbol)}</a></td>"
                f"<td>{candidate.composite_score:+.2f}</td>"
                f"<td>{candidate.trend_score:+.2f}</td>"
                f"<td>{candidate.momentum_score:+.2f}</td>"
                f"<td>{decision_cell}</td>"
                f"<td>{confidence_cell}</td>"
                f"<td>{data_cell}</td></tr>"
            )
        candidates_table = "".join(candidate_rows) or "<tr><td colspan='7' class='muted'>No candidates in the latest scan.</td></tr>"
        candidates_section = (
            f"{scan_meta}"
            f"<table><tr><th>Symbol</th><th>Composite</th><th>Trend</th><th>Momentum</th><th>Latest Decision</th><th>Confidence</th><th>Data Source/Status</th></tr>{candidates_table}</table>"
        )

    if learning_snapshot is None:
        learning_section = (
            "<p class='muted'>No evaluated predictions yet &mdash; run "
            "<code>python main.py predict --symbol ...</code> then <code>python main.py evaluate</code> first.</p>"
        )
    else:
        ps = learning_snapshot["prediction_summary"]
        prediction_summary_kv = (
            "<div class='kv'>"
            f"<div>Active (unresolved)</div><div>{ps.active}</div>"
            f"<div>Target hit</div><div>{ps.target_hit}</div>"
            f"<div>Stop hit</div><div>{ps.stop_hit}</div>"
            f"<div>Expired</div><div>{ps.expired}</div>"
            f"<div>Insufficient data</div><div>{ps.insufficient_data}</div>"
            "</div>"
        )
        strategy_rows = "".join(
            f"<tr><td>{html.escape(s.config_version)}</td><td>{s.total}</td><td>{s.resolved}</td>"
            f"<td>{f'{s.win_rate:.1%}' if s.win_rate is not None else 'n/a'}</td>"
            f"<td>{f'{s.average_return:+.2%}' if s.average_return is not None else 'n/a'}</td></tr>"
            for s in learning_snapshot["strategy_comparison"]
        ) or "<tr><td colspan='5' class='muted'>(none)</td></tr>"
        quality = learning_snapshot["signal_quality"]
        mfe_text = f"{quality.average_favorable_excursion:+.2%}" if quality.average_favorable_excursion is not None else "n/a"
        mae_text = f"{quality.average_adverse_excursion:+.2%}" if quality.average_adverse_excursion is not None else "n/a"
        real_calibration_rows = "".join(
            f"<tr><td>{html.escape(c.bucket_label)}</td><td>{c.total}</td><td>{c.resolved}</td>"
            f"<td>{f'{c.win_rate:.1%}' if c.win_rate is not None else 'n/a'}</td>"
            f"<td>{f'{c.average_return:+.2%}' if c.average_return is not None else 'n/a'}</td></tr>"
            for c in learning_snapshot["real_calibration"]
        ) or "<tr><td colspan='5' class='muted'>(no decisions with a recorded confidence score yet)</td></tr>"
        p = learning_snapshot["profitability"]
        verdict_class = "tag-long" if p.verdict.value == "POSITIVE_PERFORMANCE" else ("tag-short" if p.verdict.value == "NEGATIVE_PERFORMANCE" else "tag-sim")
        profitability_section = (
            "<h3 style='font-size:14px;color:#9aa4b2;'>Profitability evidence &mdash; NOT a profitability claim, a verdict over recorded evidence only</h3>"
            "<div class='kv'>"
            f"<div>Verdict</div><div><span class='tag {verdict_class}'>{html.escape(p.verdict.value)}</span></div>"
            f"<div>Sample size (resolved)</div><div>{p.sample_size}</div>"
            f"<div>Win rate</div><div>{f'{p.win_rate:.1%} (95% CI {p.win_rate_ci_low:.1%}-{p.win_rate_ci_high:.1%})' if p.win_rate is not None else 'n/a'}</div>"
            f"<div>Expectancy (per trade)</div><div>{f'{p.expectancy:+.2%}' if p.expectancy is not None else 'n/a'}</div>"
            f"<div>Profit factor</div><div>{f'{p.profit_factor:.2f}' if p.profit_factor is not None else 'n/a'}</div>"
            f"<div>Max drawdown</div><div>{f'{p.max_drawdown:.2%}' if p.max_drawdown is not None else 'n/a'}</div>"
            f"<div>Mean return 95% CI</div><div>{f'[{p.mean_return_ci_low:+.2%}, {p.mean_return_ci_high:+.2%}]' if p.mean_return_ci_low is not None else 'n/a'}</div>"
            "</div>"
            f"<ul>{''.join(f'<li class=\"muted\">{html.escape(line)}</li>' for line in p.reasoning)}</ul>"
        )
        learning_section = (
            f"<p class='muted'>{learning_snapshot['total']} evaluated prediction(s) considered.</p>"
            "<h3 style='font-size:14px;color:#9aa4b2;'>Predictions by outcome</h3>"
            f"{prediction_summary_kv}"
            f"<table><tr><th>Config Version</th><th>Total</th><th>Resolved</th><th>Win Rate</th><th>Avg Return</th></tr>{strategy_rows}</table>"
            "<h3 style='font-size:14px;color:#9aa4b2;'>Confidence calibration (real decision_engine.confidence score)</h3>"
            f"<table><tr><th>Bucket</th><th>Total</th><th>Resolved</th><th>Win Rate</th><th>Avg Return</th></tr>{real_calibration_rows}</table>"
            "<div class='kv'>"
            f"<div>Resolved (signal quality)</div><div>{quality.resolved}</div>"
            f"<div>Avg favorable excursion</div><div>{mfe_text}</div>"
            f"<div>Avg adverse excursion</div><div>{mae_text}</div>"
            "</div>"
            f"{profitability_section}"
        )

    if paper_snapshot is None:
        paper_section = (
            "<p class='muted'>No paper-execution account exists yet &mdash; run "
            "<code>python main.py shadow-run --paper-execute --initial-capital ... --paper-db ... --state-db ...</code> "
            "(or `schedule tick/loop --paper-execute`) first. This is a DIFFERENT account/database than the "
            "paper-live workstation on the page above.</p>"
        )
    else:
        account = paper_snapshot["account"]
        account_kv = (
            "<div class='kv'>"
            f"<div>Equity</div><div>{_fmt_money(account.equity)}</div>"
            f"<div>Cash</div><div>{_fmt_money(account.cash)}</div>"
            f"<div>Realized PnL</div><div>{_fmt_money(account.realized_pnl)}</div>"
            f"<div>Open positions</div><div>{account.open_positions}</div>"
            f"<div>Current drawdown</div><div>{account.current_drawdown_pct:.2f}%</div>"
            f"<div>Consecutive losses</div><div>{account.consecutive_losses}</div>"
            f"<div>Total trades</div><div>{account.total_trades}</div>"
            "</div>"
        )

        pending_rows = "".join(
            f"<tr><td>{html.escape(o.symbol)}</td><td><span class='tag tag-{'long' if o.side.value == 'LONG' else 'short'}'>{html.escape(o.side.value)}</span></td>"
            f"<td>{o.quantity}</td><td>{_fmt_money(o.requested_price)}</td><td>{_fmt_money(o.stop_price)}</td>"
            f"<td>{_fmt_money(o.target_price)}</td><td>{html.escape(o.created_at.isoformat())}</td></tr>"
            for o in paper_snapshot["pending_orders"]
        ) or "<tr><td colspan='7' class='muted'>(none)</td></tr>"
        pending_table = f"<table><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Requested</th><th>Stop</th><th>Target</th><th>Submitted</th></tr>{pending_rows}</table>"

        open_rows = "".join(
            f"<tr><td>{html.escape(p.symbol)}</td><td>{p.quantity}</td><td>{_fmt_money(p.entry_price)}</td>"
            f"<td>{_fmt_money(p.stop_price)}</td><td>{_fmt_money(p.target_price)}</td><td>{html.escape(p.entry_time.isoformat())}</td></tr>"
            for p in paper_snapshot["open_positions"]
        ) or "<tr><td colspan='6' class='muted'>(none)</td></tr>"
        open_table = f"<table><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Stop</th><th>Target</th><th>Entry Time</th></tr>{open_rows}</table>"

        closed_rows = "".join(
            f"<tr><td>{html.escape(p.symbol)}</td><td>{_fmt_money(p.entry_price)}</td>"
            f"<td>{_fmt_money(p.exit_price) if p.exit_price is not None else 'n/a'}</td>"
            f"<td>{html.escape(p.exit_reason.value) if p.exit_reason is not None else 'n/a'}</td>"
            f"<td>{html.escape(p.exit_time.isoformat()) if p.exit_time is not None else 'n/a'}</td></tr>"
            for p in paper_snapshot["closed_positions"]
        ) or "<tr><td colspan='5' class='muted'>(none)</td></tr>"
        closed_table = f"<table><tr><th>Symbol</th><th>Entry</th><th>Exit</th><th>Exit Reason</th><th>Exit Time</th></tr>{closed_rows}</table>"

        journal_rows = "".join(
            f"<tr><td>{html.escape(e.symbol)}</td><td>{html.escape(e.outcome.value)}</td><td>{html.escape(e.updated_at.isoformat())}</td>"
            f"<td>{_decision_id_cell(e)}</td></tr>"
            for e in paper_snapshot["journal_entries"]
        ) or "<tr><td colspan='4' class='muted'>(none)</td></tr>"
        journal_table = (
            "<table><tr><th>Symbol</th><th>Outcome</th><th>Last Updated</th><th>Decision ID</th></tr>"
            f"{journal_rows}</table>"
            "<p class='muted'>Decision ID (LIVE SYSTEM HARDENING mission): traces this order back to the exact "
            "decision_engine Decision that produced it -- cross-reference against a Decision Store lookup for "
            "the full rationale/composite score. &mdash; means this signal never went through decision_engine "
            "(e.g. a plain live/pipeline.py Strategy).</p>"
        )

        paper_section = (
            f"<p class='muted'>Real, persisted paper.engine.PaperTradingEngine state at {html.escape(str(intelligence.PAPER_DB_PATH))} "
            "&mdash; a DIFFERENT account/database than the paper-live workstation on the page above. No real broker order can ever "
            "originate from this data.</p>"
            "<p class='muted'>AUTONOMOUS LIVE PAPER-TRADING HARDENING mission, dashboard truth audit: Equity/Realized PnL/Total "
            "trades below are a SINGLE CUMULATIVE ledger across every symbol this engine has ever been run against via "
            "<code>shadow-run --paper-execute</code> or <code>schedule ... --paper-execute</code> &mdash; historical replay/testing runs "
            "and genuine live-market-hours runs are not distinguished IF they share the same <code>--paper-db</code> file. Check the "
            "Submitted/Entry Time columns below before reading these totals as a live NSE/BSE track record; a symbol and date range "
            "far from today's live session (e.g. an older test run) contributes to the same numbers.</p>"
            "<p class='muted'>Adversarial hardening pass (2026-09-18): <code>account</code> is a structurally single-row table "
            "(schema CHECK id=1) shared by every run against the SAME db file &mdash; its Equity/Realized PnL cannot be un-mixed "
            "after the fact without recomputation, so a schema tag alone cannot fix this retroactively. The REAL structural fix, "
            "already fully supported and zero-risk, is to point historical/testing runs and genuine live runs at "
            "<em>separate</em> <code>--paper-db</code>/<code>--state-db</code> files (exactly how the paper-live workstation "
            "above already uses a different database than this page) and set <code>TRADING_PAPER_DB_PATH</code> to the live-only "
            "one before starting this dashboard &mdash; not a code change, an operational convention this page cannot enforce for "
            "you.</p>"
            f"{account_kv}"
            "<h3 style='font-size:14px;color:#9aa4b2;'>Pending orders</h3>"
            f"{pending_table}"
            "<h3 style='font-size:14px;color:#9aa4b2;'>Open positions</h3>"
            f"{open_table}"
            "<h3 style='font-size:14px;color:#9aa4b2;'>Recently closed positions</h3>"
            f"{closed_table}"
            "<h3 style='font-size:14px;color:#9aa4b2;'>Recent journal entries</h3>"
            f"{journal_table}"
        )

    if scheduler_snapshot is None:
        scheduler_section = (
            "<p class='muted'>No scheduler run history yet &mdash; run "
            "<code>python main.py schedule tick</code> or <code>schedule loop</code> first.</p>"
        )
    else:
        active_lock = scheduler_snapshot["active_lock"]
        if active_lock is None:
            active_kv = "<div class='kv'><div>Currently running</div><div><span class='tag tag-sim'>no</span></div></div>"
        else:
            active_kv = (
                "<div class='kv'>"
                "<div>Currently running</div><div><span class='tag tag-long'>yes</span></div>"
                f"<div>Slot</div><div>{html.escape(active_lock.slot_name)}</div>"
                f"<div>Started</div><div>{html.escape(active_lock.started_at.isoformat())}</div>"
                "</div>"
            )
        run_rows = "".join(
            f"<tr><td>{html.escape(r.slot_name)}</td>"
            f"<td><span class='tag {'tag-long' if r.status.value == 'COMPLETED' else ('tag-short' if r.status.value == 'FAILED' else 'tag-sim')}'>{html.escape(r.status.value)}</span></td>"
            f"<td>{html.escape(r.started_at.isoformat())}</td>"
            f"<td>{html.escape(r.finished_at.isoformat()) if r.finished_at is not None else 'n/a'}</td>"
            f"<td>{html.escape(r.error) if r.error is not None else html.escape(r.detail)}</td></tr>"
            for r in scheduler_snapshot["recent_runs"]
        ) or "<tr><td colspan='5' class='muted'>(none)</td></tr>"
        run_table = f"<table><tr><th>Slot</th><th>Status</th><th>Started</th><th>Finished</th><th>Detail/Error</th></tr>{run_rows}</table>"
        scheduler_section = (
            f"<p class='muted'>Real, persisted scheduler run history at {html.escape(str(intelligence.SCHEDULER_DB_PATH))}.</p>"
            f"{active_kv}"
            "<h3 style='font-size:14px;color:#9aa4b2;'>Recent runs</h3>"
            f"{run_table}"
        )

    body = f"""
{kill_banner}
<p><a href="/">&larr; back to paper-live workstation</a></p>
<div class="banner">READ-ONLY SNAPSHOT of the last scan/research/decide/predict/evaluate/learn runs &mdash; not live, and no order of any kind can be placed from this page.</div>
{kill_switch_section}

<h2>MARKET INTELLIGENCE &mdash; LATEST SCAN</h2>
{candidates_section}

<h2>PREDICTION PERFORMANCE</h2>
{learning_section}

<h2>PAPER EXECUTION</h2>
{paper_section}

<h2>SCHEDULER</h2>
{scheduler_section}
"""
    return HTMLResponse(_page(body))


async def decision_detail_page(request: Request) -> HTMLResponse:
    """Phase 35 -- the full picture for ONE symbol: decision history
    (label/confidence/rationale), scanner evidence, research evidence
    (news/sector/AI summary), and prediction history (entry/stop/target/
    outcome). Read-only, same no-fetch discipline as intelligence_page --
    every field here is something scan/research/decide/predict/evaluate
    already persisted, nothing computed fresh on this GET."""
    symbol = request.path_params["symbol"].strip().upper()
    decisions = intelligence.get_decision_history(symbol)
    research_reports = intelligence.get_research_history(symbol)
    prediction_history = intelligence.get_prediction_history(symbol)

    from market_data.universe import exchange_for_symbol

    exchange = exchange_for_symbol(symbol)

    if not decisions:
        decision_section = f"<p class='muted'>No decision recorded for {html.escape(symbol)} yet &mdash; run <code>python main.py decide --symbol {html.escape(symbol)}</code> first.</p>"
        evidence_section = ""
    else:
        latest = decisions[0]
        decision_class = "tag-long" if latest.label.value == "BUY" else "tag-sim"
        confidence_text = f"{latest.confidence:.0%}" if latest.confidence is not None else "n/a"
        data_source_text = (
            f"{html.escape(latest.market_context.data_source or '')} / {html.escape(latest.market_context.data_status or '')}"
            if latest.market_context is not None and latest.market_context.data_status is not None
            else "n/a"
        )
        rationale_items = "".join(f"<li>{html.escape(line)}</li>" for line in latest.rationale)
        history_rows = "".join(
            f"<tr><td>{html.escape(d.as_of.isoformat())}</td>"
            f"<td><span class='tag {'tag-long' if d.label.value == 'BUY' else 'tag-sim'}'>{html.escape(d.label.value)}</span></td>"
            f"<td>{f'{d.confidence:.0%}' if d.confidence is not None else 'n/a'}</td>"
            f"<td>{html.escape(d.config_version)}</td></tr>"
            for d in decisions
        )
        # Mission requirement (new UI/UX workstream, Section 6/13 -- "the user
        # must understand that the LLM did not secretly make the trade
        # decision" / "AI activity transparency"): Decision.narrative and
        # narrative_unavailable_reason are real, persisted fields (populated by
        # `decide`/`shadow-run --with-ai`) that were never rendered anywhere in
        # this dashboard -- found missing via adversarial UI audit. Rendered in
        # its OWN, clearly-labeled section, visually separate from the
        # deterministic rationale above -- never merged into one block, so an
        # operator can never mistake AI narration for the actual decision basis.
        if latest.narrative is not None:
            ai_section = (
                "<h3 style='font-size:14px;color:#9aa4b2;'>AI EXPLANATION <span class='tag tag-mock'>LLM narration -- not the decision basis</span></h3>"
                f"<p>{html.escape(latest.narrative)}</p>"
            )
        elif latest.narrative_unavailable_reason is not None:
            ai_section = (
                "<h3 style='font-size:14px;color:#9aa4b2;'>AI EXPLANATION</h3>"
                f"<p class='muted'>{html.escape(latest.narrative_unavailable_reason)}</p>"
            )
        else:
            ai_section = (
                "<h3 style='font-size:14px;color:#9aa4b2;'>AI EXPLANATION</h3>"
                "<p class='muted'>Not requested for this decision -- run with <code>--with-ai</code> to include one.</p>"
            )
        decision_section = f"""
<div class="kv">
<div>Latest label</div><div><span class='tag {decision_class}'>{html.escape(latest.label.value)}</span></div>
<div>Confidence</div><div>{confidence_text}</div>
<div>Confidence explanation</div><div>{html.escape(latest.confidence_explanation or 'n/a')}</div>
<div>As of</div><div>{html.escape(latest.as_of.isoformat())}</div>
<div>Config version</div><div>{html.escape(latest.config_version)}</div>
<div>Data source/status</div><div>{data_source_text}</div>
</div>
<h3 style='font-size:14px;color:#9aa4b2;'>DETERMINISTIC RATIONALE <span class='tag tag-long'>decision_engine.rules.classify -- the actual basis for the label above</span></h3>
<ul>{rationale_items}</ul>
{ai_section}
<h3 style='font-size:14px;color:#9aa4b2;'>Decision history ({len(decisions)})</h3>
<table><tr><th>As Of</th><th>Label</th><th>Confidence</th><th>Config Version</th></tr>{history_rows}</table>
"""
        if latest.scanner_evidence is not None:
            c = latest.scanner_evidence
            explanation_items = "".join(f"<li>{html.escape(line)}</li>" for line in c.explanation)
            evidence_section = f"""
<h2>SCANNER EVIDENCE</h2>
<div class="kv">
<div>Composite</div><div>{c.composite_score:+.2f}</div>
<div>Trend</div><div>{c.trend_score:+.2f}</div>
<div>Momentum</div><div>{c.momentum_score:+.2f}</div>
<div>Breakout</div><div>{c.breakout_score:+.4f}</div>
<div>Relative strength</div><div>{f'{c.relative_strength_score:+.4f}' if c.relative_strength_score is not None else 'n/a'}</div>
<div>Sector strength</div><div>{f'{c.sector_strength_score:+.4f}' if c.sector_strength_score is not None else 'n/a'}</div>
<div>Last close</div><div>{c.last_close:.2f}</div>
</div>
<ul>{explanation_items}</ul>
"""
        else:
            evidence_section = "<h2>SCANNER EVIDENCE</h2><p class='muted'>None recorded on the latest decision.</p>"

    if not research_reports:
        research_section = f"<p class='muted'>No research recorded for {html.escape(symbol)} yet &mdash; run <code>python main.py research --symbol {html.escape(symbol)}</code> first.</p>"
    else:
        latest_research = research_reports[0]
        news_items = "".join(
            f"<li>[{html.escape(item.published_at.isoformat())}] ({html.escape(item.source)}) {html.escape(item.title)}</li>"
            for item in latest_research.news
        ) or "<li class='muted'>(no news items)</li>"
        sector_text = html.escape(latest_research.sector.sector or "UNKNOWN") if latest_research.sector is not None else "n/a"
        ai_summary_text = html.escape(latest_research.ai_summary.summary) if latest_research.ai_summary is not None else "not available"
        research_section = f"""
<div class="kv">
<div>Sector</div><div>{sector_text}</div>
<div>As of</div><div>{html.escape(latest_research.as_of.isoformat())}</div>
</div>
<p><strong>AI summary (narration only):</strong> {ai_summary_text}</p>
<p><strong>News ({len(latest_research.news)}):</strong></p>
<ul>{news_items}</ul>
"""

    if not prediction_history:
        prediction_section = f"<p class='muted'>No shadow predictions recorded for {html.escape(symbol)} yet &mdash; run <code>python main.py predict --symbol {html.escape(symbol)}</code> after a BUY decision.</p>"
    else:
        prediction_rows = []
        for prediction, evaluation in prediction_history:
            outcome_text = html.escape(evaluation.outcome.value) if evaluation is not None else "not yet evaluated"
            return_text = f"{evaluation.actual_return:+.2%}" if evaluation is not None and evaluation.actual_return is not None else "n/a"
            outcome_class = "tag-long" if evaluation is not None and evaluation.outcome.value == "TARGET_HIT" else "tag-sim"
            rd = prediction.risk_decision
            qty_text = str(rd.position_size.quantity) if (rd is not None and rd.position_size is not None) else "n/a"
            capital_text = f"{rd.account_equity:,.0f}" if rd is not None else "n/a"

            ca = prediction.critic_assessment
            if ca is None:
                # Never fabricated: a prediction recorded before the critic
                # existed, or with --skip-critic, genuinely has no verdict.
                critic_cell = "<span class='muted'>n/a</span>"
            else:
                critic_class = "tag-long" if ca.verdict.value == "APPROVE" else ("tag-short" if ca.verdict.value == "REJECT" else "tag-sim")
                critic_cell = f"<span class='tag {critic_class}'>{html.escape(ca.verdict.value)}</span>"
                if ca.verdict.value != "APPROVE":
                    reasons_text = "; ".join(ca.reasons)
                    critic_cell += f"<br><span class='muted' style='font-size:11px;'>{html.escape(reasons_text)}</span>"

            prediction_rows.append(
                f"<tr><td>{html.escape(prediction.created_at.isoformat())}</td>"
                f"<td>{prediction.entry_price:.2f}</td><td>{prediction.stop_price:.2f}</td><td>{prediction.target_price:.2f}</td>"
                f"<td>{qty_text}</td><td>{capital_text}</td><td>{critic_cell}</td>"
                f"<td><span class='tag {outcome_class}'>{outcome_text}</span></td><td>{return_text}</td></tr>"
            )
        prediction_section = f"<table><tr><th>Created</th><th>Entry</th><th>Stop</th><th>Target</th><th>Qty</th><th>Capital</th><th>Critic</th><th>Outcome</th><th>Return</th></tr>{''.join(prediction_rows)}</table>"

    body = f"""
<p><a href="/intelligence">&larr; back to market intelligence</a></p>
<div class="banner">READ-ONLY DECISION DETAIL for {html.escape(symbol)} ({html.escape(exchange)}) &mdash; no order of any kind can be placed from this page.</div>

<h2>DECISION</h2>
{decision_section}

{evidence_section}

<h2>RESEARCH EVIDENCE</h2>
{research_section}

<h2>PREDICTION HISTORY</h2>
{prediction_section}
"""
    return HTMLResponse(_page(body))


async def health_page(request: Request) -> HTMLResponse:
    """Final-product-hardening: the SAME `core.health.collect_system_health`
    `main.py health` calls -- the mission's own explicit requirement that
    the dashboard and CLI consume one shared health source, not two
    independently-drifting implementations. Zero write, same
    zero-I/O-beyond-disk-and-localhost-Ollama posture as every other
    check this function runs -- no market-data fetch happens here either."""
    from core.health import ComponentStatus, OverallStatus, collect_system_health

    db_paths = {
        "experiments": PROJECT_ROOT / "data" / "experiments.db",
        "decision_engine": intelligence.DECISIONS_DB_PATH,
        "live_state": intelligence.STATE_DB_PATH,
        "promotion_gate": PROJECT_ROOT / "data" / "promotion_gate.db",
        "paper": intelligence.PAPER_DB_PATH,
        "scheduler": intelligence.SCHEDULER_DB_PATH,
        "predictions": intelligence.PREDICTIONS_DB_PATH,
        "research": intelligence.RESEARCH_DB_PATH,
        "scanner": intelligence.SCANNER_DB_PATH,
        "regime": PROJECT_ROOT / "data" / "market_regime.db",
    }
    health = collect_system_health(db_paths=db_paths, probe_dir=PROJECT_ROOT, check_ollama=True)

    tag_class = {
        ComponentStatus.HEALTHY: "tag-long", ComponentStatus.DEGRADED: "tag-warn",
        ComponentStatus.FAILED: "tag-short", ComponentStatus.DISABLED: "tag-sim", ComponentStatus.UNKNOWN: "tag-sim",
    }
    overall_class = {
        OverallStatus.HEALTHY: "tag-long", OverallStatus.DEGRADED: "tag-warn",
        OverallStatus.SAFE_STOP: "tag-warn", OverallStatus.FAILED: "tag-short",
    }[health.overall]

    rows = "".join(
        f'<tr><td>{html.escape(c.name)}</td>'
        f'<td><span class="tag {tag_class[c.status]}">{html.escape(c.status.value)}</span></td>'
        f'<td>{html.escape(c.detail)}</td></tr>'
        for c in health.components
    )
    body = f"""
<h2>SYSTEM HEALTH</h2>
<p>Overall status: <span class="tag {overall_class}">{html.escape(health.overall.value)}</span></p>
<table>
<tr><th>Component</th><th>Status</th><th>Detail</th></tr>
{rows}
</table>
<p class="muted">Same source as <code>python main.py health</code> (core/health.py). Read-only; the one network
call this page can make is to a local Ollama daemon, never a market-data provider.</p>
"""
    return HTMLResponse(_page(body))


app = Starlette(routes=[
    Route("/", overview, methods=["GET"]),
    Route("/signals", signals_page, methods=["GET"]),
    Route("/signals/{signal_id}", signal_detail_page, methods=["GET"]),
    Route("/portfolio", portfolio_page, methods=["GET"]),
    Route("/fleet", fleet_page, methods=["GET"]),
    Route("/system", system_page, methods=["GET"]),
    Route("/research", research_page, methods=["GET"]),
    Route("/api/state", api_state, methods=["GET"]),
    Route("/approve", approve, methods=["POST"]),
    Route("/reject", reject, methods=["POST"]),
    Route("/kill-switch/activate", kill_switch_activate, methods=["POST"]),
    Route("/kill-switch/reset", kill_switch_reset, methods=["POST"]),
    Route("/intelligence", intelligence_page, methods=["GET"]),
    Route("/intelligence/{symbol}", decision_detail_page, methods=["GET"]),
    Route("/health", health_page, methods=["GET"]),
])
