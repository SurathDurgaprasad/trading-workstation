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

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

import live.workstation as workstation
from dashboard import intelligence

_REFRESH_SECONDS = 15


def _page(body: str) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Paper-Live Workstation (SIMULATED)</title>
<meta http-equiv="refresh" content="{_REFRESH_SECONDS}">
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; background: #0f1115; color: #e6e6e6; margin: 0; padding: 24px; }}
  .banner {{ background: #7a1f1f; color: #fff; padding: 10px 16px; font-weight: bold; border-radius: 4px; margin-bottom: 16px; }}
  .kill-active {{ background: #b30000; }}
  h2 {{ border-bottom: 1px solid #333; padding-bottom: 4px; margin-top: 28px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #262a33; font-size: 14px; }}
  th {{ color: #9aa4b2; font-weight: 600; }}
  .tag {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }}
  .tag-mock {{ background: #33415c; color: #a9c1ff; }}
  .tag-sim {{ background: #33415c; color: #a9c1ff; }}
  .tag-long {{ background: #14432a; color: #7be8a4; }}
  .tag-short {{ background: #4a1f1f; color: #ff9d9d; }}
  form.inline {{ display: inline; }}
  button {{ padding: 6px 14px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; }}
  button.approve {{ background: #1f7a3f; color: #fff; }}
  button.reject {{ background: #7a1f1f; color: #fff; }}
  button.killswitch {{ background: #b30000; color: #fff; }}
  button.reset {{ background: #33415c; color: #fff; }}
  input[type=text] {{ background: #1a1d24; border: 1px solid #333; color: #e6e6e6; padding: 4px 8px; border-radius: 3px; }}
  .muted {{ color: #8a93a3; font-size: 12px; }}
  .kv {{ display: grid; grid-template-columns: 220px 1fr; row-gap: 4px; max-width: 480px; }}
</style>
</head>
<body>
<div class="banner">SIMULATED PAPER TRADING &mdash; NOT connected to a live broker or feed. No real order can ever be placed here.</div>
{body}
<p class="muted">Auto-refreshes every {_REFRESH_SECONDS}s. This page does not advance the market itself &mdash;
run <code>python main.py paper-live --symbol ... --interval ... --period ...</code> in a terminal to process bars and generate signals.</p>
</body>
</html>"""


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


async def index(request: Request) -> HTMLResponse:
    status = workstation.get_live_sim_status()
    pending = workstation.get_pending_approvals()
    positions = workstation.get_positions()
    account = workstation.get_account_state()
    risk = workstation.get_risk_state()
    journal = workstation.get_trade_journal()
    feed_status = workstation.get_feed_status()

    kill_banner = ""
    if status["kill_switch_active"]:
        reason = html.escape(status["kill_switch_reason"] or "")
        kill_banner = f'<div class="banner kill-active">KILL SWITCH ACTIVE &mdash; {reason} &mdash; no new signal will be approved or executed.</div>'

    kill_form = (
        '<form class="inline" method="post" action="/kill-switch/reset">'
        '<button class="reset" type="submit">Reset kill switch</button></form>'
        if status["kill_switch_active"] else
        '<form class="inline" method="post" action="/kill-switch/activate">'
        '<input type="text" name="reason" placeholder="reason (optional)">'
        '<button class="killswitch" type="submit">Activate kill switch</button></form>'
    )

    market_rows = "".join(
        f"<tr><td>{html.escape(r.symbol)}</td><td><span class='tag tag-{r.signal.side.value.lower()}'>{r.signal.side.value}</span></td>"
        f"<td>{r.signal.reference_price:.2f}</td><td>{r.signal.generated_at}</td></tr>"
        for r in pending
    ) or "<tr><td colspan='4' class='muted'>No pending signals &mdash; nothing to show until paper-live generates one.</td></tr>"

    pending_rows = "".join(
        f"<tr><td>{html.escape(r.signal_id[:12])}</td><td>{html.escape(r.symbol)}</td>"
        f"<td><span class='tag tag-{r.signal.side.value.lower()}'>{r.signal.side.value}</span></td>"
        f"<td>{r.signal.stop_price:.2f}</td><td>{r.signal.target_price:.2f}</td><td>{r.requested_quantity}</td>"
        f"<td>{html.escape(r.expires_at)}</td>"
        f"<td>"
        f"<form class='inline' method='post' action='/approve'><input type='hidden' name='signal_id' value='{html.escape(r.signal_id)}'>"
        f"<button class='approve' type='submit'>APPROVE</button></form> "
        f"<form class='inline' method='post' action='/reject'><input type='hidden' name='signal_id' value='{html.escape(r.signal_id)}'>"
        f"<button class='reject' type='submit'>REJECT</button></form>"
        f"</td></tr>"
        for r in pending
    ) or "<tr><td colspan='8' class='muted'>No signals pending human approval.</td></tr>"

    position_rows = "".join(
        f"<tr><td>{html.escape(p.symbol)}</td><td>{p.quantity}</td><td>{p.entry_price:.2f}</td>"
        f"<td>{p.stop_price:.2f}</td><td>{p.target_price:.2f}</td><td>{p.entry_time}</td></tr>"
        for p in positions
    ) or "<tr><td colspan='6' class='muted'>No open positions.</td></tr>"

    journal_rows = "".join(
        f"<tr><td>{e.created_at}</td><td>{html.escape(e.symbol)}</td><td>{html.escape(e.outcome.value)}</td>"
        f"<td>{html.escape(e.signal_id[:12])}</td></tr>"
        for e in sorted(journal, key=lambda e: e.created_at, reverse=True)[:25]
    ) or "<tr><td colspan='4' class='muted'>No journal entries yet.</td></tr>"

    def _feed_row(record) -> str:
        source_class = "tag-mock" if record.source == "MOCK" else "tag-long"  # reuse the LONG/green tag color for a real source, distinct from mock's blue
        status_class = "tag-sim" if record.status in ("SIMULATED", "HISTORICAL") else "tag-long"
        try:
            age_seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(record.received_at)).total_seconds()
            age_text = f"{age_seconds:,.1f}s"
        except ValueError:
            age_text = "unknown"
        conn = record.connection_state or "UNKNOWN"
        conn_class = "tag-long" if conn == "CONNECTED" else "tag-short"
        return (
            f"<tr><td>{html.escape(record.symbol)}</td>"
            f"<td><span class='tag {source_class}'>{html.escape(record.source)}</span></td>"
            f"<td><span class='tag {status_class}'>{html.escape(record.status)}</span></td>"
            f"<td><span class='tag {conn_class}'>{html.escape(conn)}</span></td>"
            f"<td>{html.escape(record.bar_timestamp)}</td>"
            f"<td>{age_text}</td></tr>"
        )

    feed_rows = "".join(_feed_row(r) for r in feed_status) or (
        "<tr><td colspan='6' class='muted'>No market data processed yet in this session &mdash; "
        "run <code>python main.py paper-live ...</code> to start a feed.</td></tr>"
    )

    body = f"""
{kill_banner}
<p><a href="/intelligence">Market intelligence &amp; prediction performance &rarr;</a></p>
<h2>KILL SWITCH <span class="tag tag-sim">{'ACTIVE' if status['kill_switch_active'] else 'INACTIVE'}</span></h2>
{kill_form}

<h2>MARKET FEED</h2>
<p class="muted">The last bar actually delivered by whatever is driving the feed (the paper-live CLI, in another process) &mdash; never fabricated here.</p>
<table><tr><th>Symbol</th><th>Source</th><th>Status</th><th>Connection</th><th>Last Bar</th><th>Data Age</th></tr>{feed_rows}</table>

<h2>SIGNALS <span class="tag tag-mock">from pending approvals</span></h2>
<p class="muted">Derived from the latest signal seen for each symbol currently awaiting approval.</p>
<table><tr><th>Symbol</th><th>Direction</th><th>Reference Price</th><th>As Of</th></tr>{market_rows}</table>

<h2>SIGNALS / PENDING APPROVAL ({status['pending_approvals_count']})</h2>
<table><tr><th>Signal ID</th><th>Symbol</th><th>Direction</th><th>Stop</th><th>Target</th><th>Qty</th><th>Expires</th><th>Action</th></tr>{pending_rows}</table>

<h2>POSITIONS ({len(positions)} open)</h2>
<table><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Stop</th><th>Target</th><th>Entry Time</th></tr>{position_rows}</table>

<h2>ACCOUNT</h2>
<div class="kv">
<div>Cash</div><div>{_fmt_money(account.cash)}</div>
<div>Equity</div><div>{_fmt_money(account.equity)}</div>
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

<h2>JOURNAL (most recent 25)</h2>
<table><tr><th>Time</th><th>Symbol</th><th>Outcome</th><th>Signal</th></tr>{journal_rows}</table>
"""
    return HTMLResponse(_page(body))


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

    body = f"""
<p><a href="/">&larr; back to paper-live workstation</a></p>
<div class="banner">READ-ONLY SNAPSHOT of the last scan/research/decide/predict/evaluate/learn runs &mdash; not live, and no order of any kind can be placed from this page.</div>

<h2>MARKET INTELLIGENCE &mdash; LATEST SCAN</h2>
{candidates_section}

<h2>PREDICTION PERFORMANCE</h2>
{learning_section}
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
        decision_section = f"""
<div class="kv">
<div>Latest label</div><div><span class='tag {decision_class}'>{html.escape(latest.label.value)}</span></div>
<div>Confidence</div><div>{confidence_text}</div>
<div>Confidence explanation</div><div>{html.escape(latest.confidence_explanation or 'n/a')}</div>
<div>As of</div><div>{html.escape(latest.as_of.isoformat())}</div>
<div>Config version</div><div>{html.escape(latest.config_version)}</div>
<div>Data source/status</div><div>{data_source_text}</div>
</div>
<p><strong>Rationale:</strong></p>
<ul>{rationale_items}</ul>
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
            prediction_rows.append(
                f"<tr><td>{html.escape(prediction.created_at.isoformat())}</td>"
                f"<td>{prediction.entry_price:.2f}</td><td>{prediction.stop_price:.2f}</td><td>{prediction.target_price:.2f}</td>"
                f"<td><span class='tag {outcome_class}'>{outcome_text}</span></td><td>{return_text}</td></tr>"
            )
        prediction_section = f"<table><tr><th>Created</th><th>Entry</th><th>Stop</th><th>Target</th><th>Outcome</th><th>Return</th></tr>{''.join(prediction_rows)}</table>"

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


app = Starlette(routes=[
    Route("/", index, methods=["GET"]),
    Route("/approve", approve, methods=["POST"]),
    Route("/reject", reject, methods=["POST"]),
    Route("/kill-switch/activate", kill_switch_activate, methods=["POST"]),
    Route("/kill-switch/reset", kill_switch_reset, methods=["POST"]),
    Route("/intelligence", intelligence_page, methods=["GET"]),
    Route("/intelligence/{symbol}", decision_detail_page, methods=["GET"]),
])
