"""Phase 26 -- the new /intelligence dashboard route. Uses Starlette's
TestClient (httpx-backed, no real sockets), matching tests/test_dashboard.py's
own established pattern exactly. Every fixture writes real Phase 18-25
store objects to tmp_path databases and points dashboard.intelligence's
module-level path constants at them via monkeypatch -- no real network,
no real Ollama call, no real market-data fetch anywhere in this file
(dashboard.intelligence's own functions never call fetch_ohlcv/
invoke_structured/check_ollama_availability at all, so there is nothing
to fake).
"""

from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

from decision_engine.models import Decision, DecisionLabel, RiskContext
from decision_engine.store import DecisionStore
from market_intelligence.models import CandidateScore, ScanReport
from market_intelligence.store import ScanHistoryStore
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord
from predictions.store import PredictionStore


@pytest.fixture(autouse=True)
def _isolated_intelligence_dbs(monkeypatch, tmp_path):
    import dashboard.intelligence as intelligence_module

    monkeypatch.setattr(intelligence_module, "SCANNER_DB_PATH", tmp_path / "scanner.db")
    monkeypatch.setattr(intelligence_module, "RESEARCH_DB_PATH", tmp_path / "research.db")
    monkeypatch.setattr(intelligence_module, "DECISIONS_DB_PATH", tmp_path / "decisions.db")
    monkeypatch.setattr(intelligence_module, "PREDICTIONS_DB_PATH", tmp_path / "predictions.db")
    monkeypatch.setattr(intelligence_module, "PAPER_DB_PATH", tmp_path / "paper.db")
    monkeypatch.setattr(intelligence_module, "SCHEDULER_DB_PATH", tmp_path / "scheduler_runs.db")
    monkeypatch.setattr(intelligence_module, "STATE_DB_PATH", tmp_path / "live_state.db")
    yield tmp_path


@pytest.fixture
def client():
    from dashboard.app import app

    return TestClient(app)


def _candidate(symbol: str = "AAPL", composite: float = 1.5) -> CandidateScore:
    return CandidateScore(
        symbol=symbol, as_of=datetime(2024, 6, 1), last_close=190.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=composite,
        explanation=["fake"],
    )


def _save_scan(db_path, *candidates: CandidateScore):
    store = ScanHistoryStore(db_path)
    store.save_report(ScanReport(
        scan_id="scan-1", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), universe_mode="watchlist",
        universe_size=len(candidates), benchmark_symbol=None, benchmark_unavailable_reason=None,
        config_version="cfg1", candidates=list(candidates), excluded=[],
    ))
    store.close()


def _save_decision(db_path, symbol: str, label: DecisionLabel, candidate: CandidateScore | None, market_context=None):
    store = DecisionStore(db_path)
    store.save_decision(Decision(
        decision_id=f"dec-{symbol}", symbol=symbol, as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=label,
        rationale=["fake rationale"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=market_context, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()


def _save_prediction_and_evaluation(predictions_db, symbol: str, decision_id: str, outcome: PredictionOutcomeState, actual_return: float | None):
    store = PredictionStore(predictions_db)
    store.save_prediction(PredictionRecord(
        prediction_id=f"pred-{symbol}", decision_id=decision_id, symbol=symbol, created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 6, 1),
        horizon_bars=20, interval="1d",
    ))
    store.save_evaluation(PredictionEvaluation(
        evaluation_id=f"eval-{symbol}", prediction_id=f"pred-{symbol}", evaluated_at=datetime.now(timezone.utc),
        outcome=outcome, bars_observed=5, exit_time=None, exit_price=None, actual_return=actual_return,
        max_favorable_excursion=0.1, max_adverse_excursion=0.02, detail="test",
    ))
    store.close()


# --- empty state --------------------------------------------------------------


def test_intelligence_page_empty_state_when_nothing_persisted(client):
    response = client.get("/intelligence")
    assert response.status_code == 200
    assert "No scan has been run yet" in response.text
    assert "No evaluated predictions yet" in response.text
    assert "No paper-execution account exists yet" in response.text
    assert "No scheduler run history yet" in response.text
    assert "READ-ONLY SNAPSHOT" in response.text


# --- populated scan + decisions -------------------------------------------------


def test_intelligence_page_shows_latest_scan_and_decision(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_scan(tmp_path / "scanner.db", candidate)
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, candidate)

    response = client.get("/intelligence")

    assert "AAPL" in response.text
    assert "+1.75" in response.text
    assert "BUY" in response.text
    assert "cfg1" in response.text


def test_intelligence_page_shows_data_source_and_status_when_present(client, _isolated_intelligence_dbs):
    """Phase 32: a decision whose market_context was populated (e.g. by
    shadow-run) must surface its data_source/data_status on the page --
    the honest "is this live or historical" answer the roadmap's own
    safety rule asks for."""
    from market.context import MarketContext

    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_scan(tmp_path / "scanner.db", candidate)
    context = MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=190.0, data_source="DHAN", data_status="LIVE")
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, candidate, market_context=context)

    response = client.get("/intelligence")

    assert "DHAN / LIVE" in response.text


def test_intelligence_page_shows_confidence_when_present(client, _isolated_intelligence_dbs):
    """Phase 34: a decision's real decision_engine.confidence score must
    be shown -- never fabricated when absent."""
    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_scan(tmp_path / "scanner.db", candidate)

    store = DecisionStore(tmp_path / "decisions.db")
    store.save_decision(Decision(
        decision_id="dec-AAPL", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), confidence=0.8, confidence_explanation="4 of 5 agree",
        narrative=None, narrative_unavailable_reason=None,
    ))
    store.close()

    response = client.get("/intelligence")
    assert "80%" in response.text


def test_intelligence_page_shows_n_a_when_market_context_absent(client, _isolated_intelligence_dbs):
    """A decision with no market_context at all (e.g. from standalone
    `decide`, which does not build one) must show an honest "n/a" --
    never a fabricated source/status."""
    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_scan(tmp_path / "scanner.db", candidate)
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, candidate)  # market_context=None

    response = client.get("/intelligence")

    assert "n/a" in response.text


def test_intelligence_page_handles_a_candidate_with_no_decision_gracefully(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    _save_scan(tmp_path / "scanner.db", _candidate("MSFT"))
    # deliberately no decision saved for MSFT

    response = client.get("/intelligence")

    assert response.status_code == 200
    assert "MSFT" in response.text
    assert "no decision recorded" in response.text


# --- learning snapshot -----------------------------------------------------------


def test_intelligence_page_shows_learning_snapshot(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, _candidate("AAPL"))
    _save_prediction_and_evaluation(tmp_path / "predictions.db", "AAPL", "dec-AAPL", PredictionOutcomeState.TARGET_HIT, 0.10)

    response = client.get("/intelligence")

    assert "1 evaluated prediction(s) considered." in response.text
    assert "cfg1" in response.text
    assert "100.0%" in response.text  # win rate: 1/1 resolved, all wins


def test_intelligence_page_shows_profitability_evidence_insufficient_data_for_one_prediction(client, _isolated_intelligence_dbs):
    """Phase 41: a single resolved prediction is nowhere near the
    evidence threshold -- the page must show INSUFFICIENT_DATA, never a
    profitability claim from one data point."""
    tmp_path = _isolated_intelligence_dbs
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, _candidate("AAPL"))
    _save_prediction_and_evaluation(tmp_path / "predictions.db", "AAPL", "dec-AAPL", PredictionOutcomeState.TARGET_HIT, 0.10)

    response = client.get("/intelligence")

    assert "Profitability evidence" in response.text
    assert "INSUFFICIENT_DATA" in response.text
    assert "NOT a profitability claim" in response.text


def test_intelligence_page_shows_active_vs_resolved_prediction_counts(client, _isolated_intelligence_dbs):
    """Mission requirement (Section 16 -- 'PREDICTIONS: active/resolved/
    accuracy') found genuinely missing via self-audit: a prediction whose
    latest evaluation is genuinely ACTIVE (still unresolved) was
    previously invisible on the dashboard -- the section only ever showed
    "N evaluated prediction(s) considered" with no breakdown of how many
    of those are still pending vs. actually resolved."""
    tmp_path = _isolated_intelligence_dbs
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, _candidate("AAPL"))
    _save_decision(tmp_path / "decisions.db", "MSFT", DecisionLabel.BUY, _candidate("MSFT"))
    _save_prediction_and_evaluation(tmp_path / "predictions.db", "AAPL", "dec-AAPL", PredictionOutcomeState.TARGET_HIT, 0.10)
    _save_prediction_and_evaluation(tmp_path / "predictions.db", "MSFT", "dec-MSFT", PredictionOutcomeState.ACTIVE, None)

    response = client.get("/intelligence")

    assert "Predictions by outcome" in response.text
    assert "<div>Active (unresolved)</div><div>1</div>" in response.text
    assert "<div>Target hit</div><div>1</div>" in response.text
    assert "<div>Stop hit</div><div>0</div>" in response.text


# --- HTML escaping -----------------------------------------------------------------


def test_intelligence_page_escapes_symbol_names(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    malicious_symbol = "<script>alert(1)</script>"
    _save_scan(tmp_path / "scanner.db", _candidate(malicious_symbol))

    response = client.get("/intelligence")

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_intelligence_page_links_to_the_decision_detail_page(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    _save_scan(tmp_path / "scanner.db", _candidate("AAPL"))

    response = client.get("/intelligence")
    assert "href='/intelligence/AAPL'" in response.text


# --- Phase 35: /intelligence/{symbol} decision detail page -----------------------


def _save_research(db_path, symbol: str, *, news=None, sector=None, ai_summary=None):
    from research.models import ResearchReport
    from research.store import ResearchStore

    store = ResearchStore(db_path)
    store.save_report(ResearchReport(
        report_id=f"report-{symbol}", symbol=symbol, as_of=datetime(2024, 6, 1, tzinfo=timezone.utc),
        news=news or [], sector=sector, ai_summary=ai_summary, ai_summary_unavailable_reason=None if ai_summary else "skipped",
    ))
    store.close()


def test_decision_detail_page_no_decision_yet(client, _isolated_intelligence_dbs):
    response = client.get("/intelligence/AAPL")
    assert response.status_code == 200
    assert "No decision recorded for AAPL" in response.text


def test_decision_detail_page_shows_decision_confidence_and_rationale(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, candidate)

    response = client.get("/intelligence/AAPL")

    assert response.status_code == 200
    assert "AAPL" in response.text
    assert "BUY" in response.text
    assert "fake rationale" in response.text
    assert "SCANNER EVIDENCE" in response.text


# --- AI narrative transparency -------------------------------------------------
#
# Real gap found via adversarial UI audit (new mission workstream, Section 6/13
# -- "the user must understand that the LLM did not secretly make the trade
# decision" / "AI activity transparency"): Decision.narrative and
# Decision.narrative_unavailable_reason are real, persisted fields (populated
# by `decide --with-ai` / `shadow-run --with-ai`, decision_engine/engine.py:
# include_narrative), but decision_detail_page never rendered either one --
# confirmed by grepping dashboard/app.py for ".narrative": zero matches before
# this fix. An operator running with --with-ai had no way to see the AI's own
# explanation on the dashboard at all, let alone see it clearly separated from
# the deterministic rationale above it.


def test_decision_detail_page_shows_ai_narrative_when_present(client, _isolated_intelligence_dbs):
    from decision_engine.models import Decision, RiskContext
    from decision_engine.store import DecisionStore

    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    store = DecisionStore(tmp_path / "decisions.db")
    store.save_decision(Decision(
        decision_id="dec-AAPL", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["deterministic rationale line"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(),
        narrative="The AI's own plain-language explanation of this BUY.", narrative_unavailable_reason=None,
    ))
    store.close()

    response = client.get("/intelligence/AAPL")

    assert "AI EXPLANATION" in response.text
    assert "The AI&#x27;s own plain-language explanation of this BUY." in response.text or "The AI's own plain-language explanation of this BUY." in response.text
    # The deterministic rationale must still be present and visually distinct
    # from the AI narrative -- the user must never confuse the two.
    assert "deterministic rationale line" in response.text
    assert "DETERMINISTIC" in response.text


def test_decision_detail_page_shows_narrative_unavailable_reason(client, _isolated_intelligence_dbs):
    from decision_engine.models import Decision, RiskContext
    from decision_engine.store import DecisionStore

    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    store = DecisionStore(tmp_path / "decisions.db")
    store.save_decision(Decision(
        decision_id="dec-AAPL", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["deterministic rationale line"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(),
        narrative=None, narrative_unavailable_reason="AI narrative unavailable: Ollama connection refused",
    ))
    store.close()

    response = client.get("/intelligence/AAPL")

    assert "AI EXPLANATION" in response.text
    assert "Ollama connection refused" in response.text


def test_decision_detail_page_shows_narrative_not_requested_when_both_absent(client, _isolated_intelligence_dbs):
    # _save_decision's own default: narrative=None, narrative_unavailable_reason=None
    # -- the ordinary case for a decision made WITHOUT --with-ai. Must say so
    # honestly, never silently omit the section or imply a failure occurred.
    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL", composite=1.75)
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, candidate)

    response = client.get("/intelligence/AAPL")

    assert "AI EXPLANATION" in response.text
    assert "not requested" in response.text.lower() or "--with-ai" in response.text


def test_decision_detail_page_shows_decision_history_most_recent_first(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    store = DecisionStore(tmp_path / "decisions.db")
    for i, label in enumerate([DecisionLabel.WATCH, DecisionLabel.BUY]):
        store.save_decision(Decision(
            decision_id=f"dec-{i}", symbol="AAPL", as_of=datetime(2024, 6, 1 + i, tzinfo=timezone.utc), label=label,
            rationale=["fake"], config_version="cfg1", scanner_evidence=_candidate("AAPL"), research_evidence=None,
            market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
        ))
    store.close()

    response = client.get("/intelligence/AAPL")
    assert "Decision history (2)" in response.text


def test_decision_detail_page_shows_research_news_and_sector(client, _isolated_intelligence_dbs):
    from research.models import NewsItem, SectorInfo

    tmp_path = _isolated_intelligence_dbs
    _save_research(
        tmp_path / "research.db", "AAPL",
        news=[NewsItem(title="Apple announces new product", summary="fake summary", source="Reuters", published_at=datetime(2024, 6, 1, tzinfo=timezone.utc), url=None)],
        sector=SectorInfo(symbol="AAPL", sector="Technology", industry="Consumer Electronics", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc)),
    )

    response = client.get("/intelligence/AAPL")

    assert "Apple announces new product" in response.text
    assert "Technology" in response.text


def test_decision_detail_page_no_research_yet(client, _isolated_intelligence_dbs):
    response = client.get("/intelligence/AAPL")
    assert "No research recorded for AAPL" in response.text


def test_decision_detail_page_shows_prediction_history(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    _save_prediction_and_evaluation(tmp_path / "predictions.db", "AAPL", "dec-AAPL", PredictionOutcomeState.TARGET_HIT, 0.15)

    response = client.get("/intelligence/AAPL")

    assert "TARGET_HIT" in response.text
    assert "+15.00%" in response.text


def test_decision_detail_page_shows_the_persisted_trade_plan_when_present(client, _isolated_intelligence_dbs):
    """Mission auditability requirement: the dashboard's prediction
    history must show quantity/capital when a prediction was recorded
    with --initial-capital, and honestly say "n/a" when it wasn't."""
    from decision_engine.models import Decision, RiskContext
    from market.context import MarketContext
    from risk.account import new_account
    from risk.sizing import size_decision

    tmp_path = _isolated_intelligence_dbs
    candidate = _candidate("AAPL")
    decision = Decision(
        decision_id="dec-AAPL", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version="cfg1", scanner_evidence=candidate, research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    )
    market_context = MarketContext(symbol="AAPL", as_of=datetime(2024, 6, 1), price=100.0, atr_14=2.5)
    risk_decision = size_decision(decision, market_context=market_context, account=new_account(20_000.0))

    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(PredictionRecord(
        prediction_id="pred-sized", decision_id="dec-AAPL", symbol="AAPL", created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 6, 1),
        horizon_bars=20, interval="1d", risk_decision=risk_decision,
    ))
    store.close()

    response = client.get("/intelligence/AAPL")
    assert str(risk_decision.position_size.quantity) in response.text
    assert "20,000" in response.text


def test_decision_detail_page_no_predictions_yet(client, _isolated_intelligence_dbs):
    response = client.get("/intelligence/AAPL")
    assert "No shadow predictions recorded for AAPL" in response.text


def _decision_and_signal_for_critic(symbol: str = "AAPL"):
    from decision_engine.models import Decision, RiskContext
    from market.context import MarketContext
    from research.models import ResearchReport
    from risk.sizing import build_signal_for_buy

    candidate = _candidate(symbol)
    research = ResearchReport(report_id="r1", symbol=symbol, as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), news=[], sector=None, ai_summary=None, ai_summary_unavailable_reason=None)
    decision = Decision(
        decision_id=f"dec-{symbol}", symbol=symbol, as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version="cfg1", scanner_evidence=candidate, research_evidence=research,
        market_context=MarketContext(symbol=symbol, as_of=datetime(2024, 6, 1), price=100.0, atr_14=2.5),
        risk_context=RiskContext.unknown(), confidence=0.8, confidence_explanation="fake",
        narrative=None, narrative_unavailable_reason=None,
    )
    signal = build_signal_for_buy(decision, decision.market_context)
    return decision, signal


def test_decision_detail_page_shows_critic_na_when_no_assessment_was_recorded(client, _isolated_intelligence_dbs):
    """Never fabricated: a prediction recorded before the critic existed,
    or with --skip-critic, genuinely has no verdict to show."""
    tmp_path = _isolated_intelligence_dbs
    _save_prediction_and_evaluation(tmp_path / "predictions.db", "AAPL", "dec-AAPL", PredictionOutcomeState.TARGET_HIT, 0.15)

    response = client.get("/intelligence/AAPL")
    assert "n/a" in response.text


def test_decision_detail_page_shows_a_real_approve_verdict(client, _isolated_intelligence_dbs):
    from critic.engine import evaluate as critic_evaluate

    tmp_path = _isolated_intelligence_dbs
    decision, signal = _decision_and_signal_for_critic("AAPL")
    assessment = critic_evaluate(decision, signal, now=datetime(2024, 6, 1, tzinfo=timezone.utc))
    assert assessment.verdict.value == "APPROVE"  # sanity: this fixture is a genuinely clean case

    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(PredictionRecord(
        prediction_id="pred-approve", decision_id="dec-AAPL", symbol="AAPL", created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=signal.reference_price, stop_price=signal.stop_price, target_price=signal.target_price,
        entry_time=signal.generated_at, horizon_bars=20, interval="1d", critic_assessment=assessment,
    ))
    store.close()

    response = client.get("/intelligence/AAPL")
    assert "APPROVE" in response.text


def test_decision_detail_page_shows_a_real_reject_verdict_with_reasons(client, _isolated_intelligence_dbs):
    from critic.engine import evaluate as critic_evaluate

    tmp_path = _isolated_intelligence_dbs
    decision, signal = _decision_and_signal_for_critic("AAPL")
    assessment = critic_evaluate(decision, signal, now=datetime(2024, 6, 1, tzinfo=timezone.utc), existing_open_position=True)
    assert assessment.verdict.value == "REJECT"

    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(PredictionRecord(
        prediction_id="pred-reject", decision_id="dec-AAPL", symbol="AAPL", created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=signal.reference_price, stop_price=signal.stop_price, target_price=signal.target_price,
        entry_time=signal.generated_at, horizon_bars=20, interval="1d", critic_assessment=assessment,
    ))
    store.close()

    response = client.get("/intelligence/AAPL")
    assert "REJECT" in response.text
    assert "already has" in response.text  # the DUPLICATE_EXPOSURE reason text, not fabricated


def test_decision_detail_page_escapes_critic_reasons(client, _isolated_intelligence_dbs):
    """Defense in depth, same discipline as the journal-entry escaping
    test elsewhere in this file: critic reasons are always html.escape()'d."""
    from critic.models import CriticAssessment, CriticCheck, CriticCheckName, CriticCheckSeverity, CriticVerdict

    tmp_path = _isolated_intelligence_dbs
    malicious_assessment = CriticAssessment(
        verdict=CriticVerdict.REJECT,
        checks=(CriticCheck(name=CriticCheckName.KILL_SWITCH, evaluated=True, passed=False, severity=CriticCheckSeverity.HARD, detail="x"),),
        failed_checks=(CriticCheckName.KILL_SWITCH.value,), warnings=(), reasons=("<script>alert(1)</script>",),
        config_version="cfg1",
    )
    store = PredictionStore(tmp_path / "predictions.db")
    store.save_prediction(PredictionRecord(
        prediction_id="pred-xss", decision_id="dec-AAPL", symbol="AAPL", created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0, entry_time=datetime(2024, 6, 1),
        horizon_bars=20, interval="1d", critic_assessment=malicious_assessment,
    ))
    store.close()

    response = client.get("/intelligence/AAPL")
    assert "<script>alert(1)</script>" not in response.text


def test_decision_detail_page_normalizes_symbol_case(client, _isolated_intelligence_dbs):
    tmp_path = _isolated_intelligence_dbs
    _save_decision(tmp_path / "decisions.db", "AAPL", DecisionLabel.BUY, _candidate("AAPL"))

    response = client.get("/intelligence/aapl")
    assert response.status_code == 200
    assert "No decision recorded" not in response.text


def test_decision_detail_page_escapes_malicious_symbol(client, _isolated_intelligence_dbs):
    response = client.get("/intelligence/%3Cscript%3E")
    assert "<script>" not in response.text


# --- PAPER EXECUTION section ----------------------------------------------------


def _paper_signal(symbol: str = "AAPL"):
    from strategy.signal import ReasonCode, Side, Signal

    return Signal(
        symbol=symbol, generated_at=datetime(2024, 6, 1), side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0,
        strategy_name="decision_engine_buy_bridge", reason_codes=[ReasonCode.DECISION_ENGINE_SCORED],
    )


def test_intelligence_page_shows_a_real_pending_paper_order(client, _isolated_intelligence_dbs):
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore

    tmp_path = _isolated_intelligence_dbs
    engine = PaperTradingEngine(PaperStore(tmp_path / "paper.db"), initial_capital=20_000.0)
    engine.submit_signal(_paper_signal("AAPL"))
    engine.store.close()

    response = client.get("/intelligence")
    assert response.status_code == 200
    assert "No paper-execution account exists yet" not in response.text
    assert "AAPL" in response.text
    assert "20,000.00" in response.text  # real account equity, not fabricated
    assert "Pending orders" in response.text


def test_intelligence_page_shows_a_real_open_paper_position(client, _isolated_intelligence_dbs):
    from paper.engine import Bar, PaperTradingEngine
    from paper.store import PaperStore

    tmp_path = _isolated_intelligence_dbs
    engine = PaperTradingEngine(PaperStore(tmp_path / "paper.db"), initial_capital=20_000.0)
    engine.submit_signal(_paper_signal("MSFT"))
    engine.process_bar("MSFT", Bar(
        timestamp=datetime(2024, 6, 2), open=101.0, high=102.0, low=100.5, close=101.5, volume=1000.0,
    ))
    engine.store.close()

    response = client.get("/intelligence")
    assert "MSFT" in response.text
    assert "Open positions" in response.text
    assert response.text.count("MSFT") >= 2  # appears in the open-positions table AND the journal


def test_intelligence_page_paper_section_escapes_html_in_journal(client, _isolated_intelligence_dbs):
    """Defense in depth: even though a symbol can never actually contain
    HTML in real use (upstream validation), the page must not trust that
    and render it unescaped -- same discipline as the decision-detail
    page's own symbol-escaping test above."""
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore

    tmp_path = _isolated_intelligence_dbs
    store = PaperStore(tmp_path / "paper.db")
    engine = PaperTradingEngine(store, initial_capital=20_000.0)
    signal = _paper_signal("AAPL")
    engine.submit_signal(signal)

    entries = store.list_journal_entries()
    entry = entries[0]
    store.update_journal_entry(entry.model_copy(update={
        "symbol": "<script>alert(1)</script>", "outcome": entry.outcome,
    }))
    store.close()

    response = client.get("/intelligence")
    assert "<script>alert(1)</script>" not in response.text


# --- MARKET STATUS banner (shared by every page via _page()) -----------------
#
# Real gap found via adversarial UI audit (Section O of the new mission --
# "Is the market open?" must be answerable within seconds): neither
# dashboard page showed market-session state at all, even though
# live.dhan.market_session.current_market_session already existed and is
# already used by the scheduler. Computed fresh, in-process, from
# wall-clock IST time only -- no I/O, so testing it here (via the always-run
# /intelligence route, not the AAPL-cache-gated root page) needs only to
# monkeypatch the pure function, not any store.


def test_intelligence_page_shows_market_status_open(client, monkeypatch):
    import live.dhan.market_session as market_session_module

    fixed = market_session_module.MarketSession(
        state=market_session_module.MarketSessionState.OPEN,
        as_of_ist=datetime(2026, 9, 7, 10, 0, 0),  # a Monday
        is_weekday=True,
    )
    monkeypatch.setattr(market_session_module, "current_market_session", lambda *a, **k: fixed)

    response = client.get("/intelligence")
    assert "Market status" in response.text
    assert "OPEN" in response.text
    assert "2026-09-07 10:00:00" in response.text


def test_intelligence_page_shows_market_status_closed(client, monkeypatch):
    import live.dhan.market_session as market_session_module

    fixed = market_session_module.MarketSession(
        state=market_session_module.MarketSessionState.CLOSED,
        as_of_ist=datetime(2026, 9, 6, 22, 0, 0),  # a Sunday night
        is_weekday=False,
    )
    monkeypatch.setattr(market_session_module, "current_market_session", lambda *a, **k: fixed)

    response = client.get("/intelligence")
    assert "Market status" in response.text
    assert "CLOSED" in response.text


def test_intelligence_page_market_status_discloses_no_holiday_awareness(client):
    # No monkeypatch -- the real current_market_session() runs, so this
    # only checks the honesty disclaimer is always present, regardless of
    # what today actually is.
    response = client.get("/intelligence")
    assert "does NOT know exchange" in response.text


# --- KILL SWITCH section ------------------------------------------------------
#
# Real gap found via adversarial UI audit (a real, running dashboard was
# inspected in a browser against actual persisted state -- not just an
# HTTP-200 unit test): /intelligence (the page showing the shadow-run/
# --paper-execute account this session's own risk-halt/kill-switch bug
# fixes concern) had ZERO kill-switch visibility at all, even though the
# root `/` page's kill switch banner is impossible to miss. An operator
# watching only /intelligence -- the more complete, decision-oriented
# view -- had no way to see the kill switch had been activated without
# navigating back to the older paper-live workstation page. Confirmed by
# grepping intelligence_page's own source for "kill_switch": zero matches,
# before this fix.


def test_intelligence_page_shows_kill_switch_inactive_by_default(client, _isolated_intelligence_dbs):
    response = client.get("/intelligence")
    assert "KILL SWITCH" in response.text
    assert "INACTIVE" in response.text


def test_intelligence_page_shows_kill_switch_active_with_reason(client, _isolated_intelligence_dbs):
    from live.state_store import LiveStateStore

    tmp_path = _isolated_intelligence_dbs
    store = LiveStateStore(tmp_path / "live_state.db")
    store.activate_kill_switch(reason="manual test activation")
    store.close()

    response = client.get("/intelligence")
    assert "KILL SWITCH ACTIVE" in response.text
    assert "manual test activation" in response.text


def test_intelligence_page_kill_switch_survives_no_state_db_yet(client):
    # No _isolated_intelligence_dbs override needed here beyond the
    # autouse fixture's own tmp_path -- the point is the STATE_DB_PATH
    # file itself was never created (no shadow-run/paper-live has ever
    # touched it). Must render INACTIVE, never crash or fabricate ACTIVE.
    response = client.get("/intelligence")
    assert response.status_code == 200
    assert "KILL SWITCH" in response.text
    assert "INACTIVE" in response.text


# --- SCHEDULER section -------------------------------------------------------


def test_intelligence_page_shows_a_completed_scheduler_run(client, _isolated_intelligence_dbs):
    from datetime import timezone

    from scheduler.models import RunStatus
    from scheduler.store import SchedulerRunStore

    tmp_path = _isolated_intelligence_dbs
    store = SchedulerRunStore(tmp_path / "scheduler_runs.db")
    store.start_run(run_id="run-1", slot_name="intraday", run_date="2026-09-04", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="run-1", status=RunStatus.COMPLETED, detail="ran 3 candidates")
    store.close()

    response = client.get("/intelligence")
    assert "No scheduler run history yet" not in response.text
    assert "intraday" in response.text
    assert "COMPLETED" in response.text
    assert "ran 3 candidates" in response.text
    assert "Currently running" in response.text and "no</span>" in response.text


def test_intelligence_page_shows_an_active_scheduler_lock(client, _isolated_intelligence_dbs):
    from datetime import timezone

    from scheduler.store import SchedulerRunStore

    tmp_path = _isolated_intelligence_dbs
    store = SchedulerRunStore(tmp_path / "scheduler_runs.db")
    store.start_run(run_id="run-active", slot_name="pre_market", run_date="2026-09-04", started_at=datetime.now(timezone.utc))
    store.close()

    response = client.get("/intelligence")
    assert "pre_market" in response.text
    assert "yes</span>" in response.text  # currently running


def test_intelligence_page_shows_a_failed_scheduler_run_with_its_error(client, _isolated_intelligence_dbs):
    from datetime import timezone

    from scheduler.models import RunStatus
    from scheduler.store import SchedulerRunStore

    tmp_path = _isolated_intelligence_dbs
    store = SchedulerRunStore(tmp_path / "scheduler_runs.db")
    store.start_run(run_id="run-fail", slot_name="market_open", run_date="2026-09-04", started_at=datetime.now(timezone.utc))
    store.finish_run(run_id="run-fail", status=RunStatus.FAILED, error="simulated provider outage")
    store.close()

    response = client.get("/intelligence")
    assert "FAILED" in response.text
    assert "simulated provider outage" in response.text
