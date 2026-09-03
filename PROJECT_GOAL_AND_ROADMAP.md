# TradingAgents — Project Goal, Architecture & Long-Term Roadmap

> **Document Status:** Active Project Blueprint  
> **Purpose:** Define the long-term product vision, architecture, engineering principles, roadmap, and completion criteria for TradingAgents.  
> **This document is authoritative for future development phases unless explicitly superseded.**

---

# 1. Executive Summary

TradingAgents is being built as an **AI-powered, continuously operating market intelligence and decision-support platform for Indian equity markets**.

The system is not intended to be a simple trading bot.

The long-term goal is to build a system capable of:

- Continuously monitoring market conditions.
- Consuming real-time and historical market data.
- Monitoring NSE and other legitimate public market information sources.
- Researching companies, sectors, market conditions, and trends.
- Identifying potential trading opportunities.
- Performing deterministic technical and quantitative analysis.
- Using AI for research, synthesis, reasoning, and evidence analysis.
- Producing structured trading recommendations.
- Calculating entry, exit, stop-loss, target, and position sizing dynamically.
- Maintaining a complete audit trail for every decision.
- Continuing to evaluate its own predictions even when the user does not trade.
- Measuring whether recommendations were actually good or bad.
- Learning which strategies, market conditions, signals, and models historically perform well.
- Improving confidence calibration and strategy selection based on measured outcomes.
- Presenting live, understandable recommendations through a dashboard.

The intended experience is:

> A continuously running AI market analyst that researches the market, identifies opportunities, explains its reasoning, tracks its own predictions, and provides evidence-backed trading decision support.

---

# 2. Core Product Vision

The final system should behave conceptually like this:

```text
                     MARKET UNIVERSE
                           │
                           ▼
              ┌───────────────────────────┐
              │  MARKET DATA COLLECTION   │
              │                           │
              │  Dhan Live Data           │
              │  NSE Information          │
              │  BSE Information          │
              │  Historical Data          │
              │  News / Events            │
              │  Sector Information       │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ MARKET INTELLIGENCE LAYER │
              │                           │
              │ Market Regime             │
              │ Trend Detection           │
              │ Sector Strength           │
              │ Liquidity Analysis        │
              │ Volatility Analysis       │
              │ Candidate Discovery       │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ ANALYSIS & RESEARCH LAYER │
              │                           │
              │ Technical Analysis        │
              │ Fundamental Research      │
              │ News Analysis             │
              │ Market Research           │
              │ AI Reasoning              │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ DECISION INTELLIGENCE     │
              │                           │
              │ Opportunity Scoring       │
              │ Entry Analysis            │
              │ Exit Analysis             │
              │ Confidence Calculation    │
              │ Risk Analysis             │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ RECOMMENDATION ENGINE     │
              │                           │
              │ BUY                       │
              │ WATCH                     │
              │ AVOID                     │
              │ EXIT                      │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ AUDIT & LEARNING SYSTEM   │
              │                           │
              │ Prediction Recording      │
              │ Outcome Tracking          │
              │ Strategy Performance      │
              │ Model Evaluation          │
              │ Confidence Calibration    │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ LIVE USER INTERFACE       │
              │                           │
              │ Opportunities             │
              │ Buy / Sell Guidance       │
              │ Entry / Stop / Target     │
              │ Position Sizing           │
              │ AI Reasoning              │
              │ Historical Performance    │
              └───────────────────────────┘
````

---

# 3. Fundamental Product Principles

These principles apply to every future phase.

## 3.1 No Blind AI Decisions

An LLM must never be treated as an unquestioned market oracle.

Bad architecture:

```text
LLM
 ↓
"BUY RELIANCE"
```

Required architecture:

```text
Real Market Data
+
Deterministic Analysis
+
Historical Evidence
+
Market Context
+
Research Evidence
+
AI Reasoning
+
Risk Constraints
        ↓
Structured Recommendation
```

AI may assist with:

* Research.
* Information synthesis.
* Pattern explanation.
* Evidence interpretation.
* Market context analysis.
* Hypothesis generation.

Deterministic systems must handle:

* Mathematical calculations.
* Indicators.
* Position sizing.
* Risk calculations.
* Stop-loss constraints.
* Data validation.
* Time calculations.
* Historical performance measurement.

---

## 3.2 No Guaranteed Profit Assumption

The system must never assume:

```text
AI = guaranteed profit
```

The engineering objective is:

```text
Measure
→ Evaluate
→ Compare
→ Improve
```

Every strategy and recommendation must earn trust through measured historical performance.

---

## 3.3 Continuous Operation

The system should continue operating even when the user does not trade.

Example:

```text
Monday:
System recommends Stock A.
User does not trade.

System still records:
- Recommendation.
- Entry price.
- Stop-loss.
- Target.
- Timestamp.
- Market conditions.
- Reasoning.

Later:
System observes actual market outcome.

Result:
Prediction classified as:
- Correct.
- Incorrect.
- Partial success.
- Stop-loss hit.
- Target hit.
- Expired.
```

The system therefore continuously learns from the market regardless of user participation.

---

## 3.4 Dynamic Capital

Capital must never be hardcoded.

Examples:

```text
₹5,000
₹10,000
₹25,000
₹50,000
₹1,00,000
```

The recommendation engine must operate independently of available capital.

First determine:

```text
Market Opportunity
Entry
Stop Loss
Target
Risk Per Share
Confidence
```

Then apply the user's current capital configuration.

Example:

```text
Available Capital:
₹50,000

Maximum Risk Per Trade:
1%

Maximum Risk:
₹500

Stock Entry:
₹1,000

Stop Loss:
₹980

Risk Per Share:
₹20

Maximum Quantity Based on Risk:
₹500 / ₹20 = 25 shares

Capital Required:
₹25,000
```

If capital changes:

```text
₹10,000 → quantity changes
₹50,000 → quantity changes
₹1,00,000 → quantity changes
```

The market recommendation itself should remain independent from personal capital.

---

# 4. What the System Ultimately Produces

The system should eventually produce a structured recommendation similar to:

```text
=================================================

MARKET OPPORTUNITY

Stock:
RELIANCE

Action:
BUY

Status:
ACTIVE SETUP

Confidence:
78%

-------------------------------------------------

ENTRY

Suggested Entry Zone:
₹1,312.50 – ₹1,315.00

Preferred Entry:
₹1,313.00

Stop Loss:
₹1,298.00

Target 1:
₹1,330.00

Target 2:
₹1,345.00

-------------------------------------------------

POSITION SIZING

Available Capital:
₹50,000

Configured Risk Per Trade:
1%

Maximum Allowed Risk:
₹500

Risk Per Share:
₹15

Suggested Quantity:
33 Shares

Estimated Position Value:
₹43,329

-------------------------------------------------

WHY THIS TRADE?

Market Context:
Bullish

Sector:
Outperforming

Technical Evidence:
✓ Above VWAP
✓ Positive volume expansion
✓ Breakout confirmation
✓ Strong relative strength

Research Evidence:
✓ No major negative event detected
✓ Sector momentum positive

-------------------------------------------------

RISKS

⚠ Resistance near ₹1,330
⚠ High market volatility possible
⚠ Setup invalid below ₹1,298

-------------------------------------------------

DECISION ID

DEC-2026-09-03-000124

Generated:
10:42:03 IST

=================================================
```

Every recommendation must be reproducible from recorded evidence.

---

# 5. Current Project State

## Completed Before Phase 18

### Phase 16 — Real Dhan Connectivity

Completed and merged into `main`.

Real service verification achieved for:

```text
Dhan REST
    ↓
WebSocket Handshake
    ↓
Live Market Packets
    ↓
Packet Parsing
    ↓
Tick Processing
    ↓
CandleBuilder
    ↓
Real OHLCV Bars
    ↓
FreshnessPolicy
    ↓
LiveSimPipeline
    ↓
Strategy Invocation
```

Real evidence included:

* Stable live WebSocket session.
* Hundreds of real packets.
* Real NSE market data.
* Real OHLCV bar generation.
* Freshness validation.
* Live pipeline processing.

Order execution remains structurally disabled.

---

### Phase 17 — Production Readiness & Operationalization

Completed on branch:

```text
phase-17-production-readiness
```

Current Phase 17 status at the time this document was created:

```text
536 passed
0 failed
0 skipped
```

Key improvements:

* Correct WebSocket lifecycle cleanup.
* Guaranteed source closure.
* Ctrl+C handling.
* Improved CLI lifecycle handling.
* Correct test isolation.
* Documentation reconciliation.
* Full green regression suite.

Phase 17 merge status must be verified before beginning Phase 18.

---

# 6. Long-Term Architecture

The final architecture should be organized into explicit domains.

```text
TradingAgents
│
├── core/
│   ├── configuration
│   ├── domain models
│   ├── event definitions
│   ├── common utilities
│   └── system contracts
│
├── market_data/
│   ├── live feeds
│   ├── historical feeds
│   ├── NSE ingestion
│   ├── BSE ingestion
│   ├── data normalization
│   ├── validation
│   └── storage
│
├── market_intelligence/
│   ├── market regime
│   ├── sector analysis
│   ├── market breadth
│   ├── volatility analysis
│   ├── liquidity analysis
│   └── candidate discovery
│
├── analysis/
│   ├── technical analysis
│   ├── indicators
│   ├── price action
│   ├── volume analysis
│   ├── trend detection
│   └── statistical analysis
│
├── research/
│   ├── news research
│   ├── company research
│   ├── sector research
│   ├── macro research
│   ├── evidence collection
│   └── AI reasoning
│
├── strategies/
│   ├── deterministic strategies
│   ├── strategy registry
│   ├── strategy evaluation
│   └── strategy performance
│
├── decision_engine/
│   ├── opportunity scoring
│   ├── recommendation generation
│   ├── confidence scoring
│   └── decision validation
│
├── risk/
│   ├── position sizing
│   ├── capital management
│   ├── stop loss
│   ├── exposure limits
│   └── risk constraints
│
├── predictions/
│   ├── prediction records
│   ├── outcome tracking
│   ├── evaluation
│   └── performance metrics
│
├── learning/
│   ├── strategy learning
│   ├── confidence calibration
│   ├── model evaluation
│   ├── market regime learning
│   └── experimentation
│
├── audit/
│   ├── decision journal
│   ├── evidence snapshots
│   ├── reasoning records
│   └── reproducibility
│
├── dashboard/
│   ├── live market view
│   ├── recommendations
│   ├── reasoning
│   ├── prediction history
│   └── performance analytics
│
└── execution/
    ├── paper trading
    └── permanently disabled real order execution
```

---

# 7. Continuous Prediction and Learning System

This is a core requirement.

The system must continue learning even when the user performs zero trades.

## 7.1 Shadow Prediction Mode

Every meaningful recommendation should be recorded as a prediction.

Example:

```text
Recommendation:

BUY RELIANCE

Entry:
₹1,312

Stop:
₹1,298

Target:
₹1,335

Time Horizon:
Intraday

Confidence:
78%
```

Even if the user does nothing:

```text
User Trade:
NONE
```

The system continues monitoring.

---

## 7.2 Outcome Tracking

The system should later determine:

```text
Did entry occur?

YES / NO
```

If entry occurred:

```text
Did target occur first?

YES / NO
```

```text
Did stop loss occur first?

YES / NO
```

```text
Maximum Favorable Excursion:
How far did the trade move in the predicted direction?

Maximum Adverse Excursion:
How far did it move against the prediction?
```

---

## 7.3 Prediction Outcome States

Suggested states:

```text
PENDING
ACTIVE
TARGET_HIT
STOP_HIT
EXPIRED
INVALIDATED
PARTIAL_SUCCESS
MISSED_ENTRY
CANCELLED
INSUFFICIENT_DATA
```

---

## 7.4 Prediction Evaluation

Every prediction should eventually receive measurable results.

Example:

```json
{
  "prediction_id": "PRED-001",

  "instrument": "RELIANCE",

  "prediction": "BUY",

  "entry_price": 1312,

  "target_price": 1335,

  "stop_loss": 1298,

  "outcome": "TARGET_HIT",

  "prediction_timestamp": "...",

  "entry_timestamp": "...",

  "exit_timestamp": "...",

  "actual_return": 0.0175,

  "prediction_quality_score": 0.91
}
```

---

# 8. What "Learning" Means

The system must not claim to "learn" unless measurable learning exists.

Learning should initially mean:

## Level 1 — Performance Tracking

Measure:

```text
Win Rate
Loss Rate
Average Return
Average Loss
Risk/Reward
Maximum Drawdown
Sharpe-like metrics where appropriate
Profit Factor
Prediction Accuracy
```

---

## Level 2 — Strategy Comparison

Example:

```text
Strategy A:
Market Trend Following

Win Rate:
62%

Strategy B:
Mean Reversion

Win Rate:
48%
```

But this comparison must also include market conditions.

---

## Level 3 — Contextual Learning

Example:

```text
Trend Following Strategy:

Bull Market:
72% success

Sideways Market:
41% success

High Volatility:
55% success
```

The system learns:

```text
WHEN a strategy works.
```

Not merely:

```text
WHICH strategy exists.
```

---

## Level 4 — Confidence Calibration

Example:

```text
Predictions with 90% confidence:
Actual success rate = 68%

Predictions with 70% confidence:
Actual success rate = 71%
```

This reveals confidence is poorly calibrated.

The system should adjust confidence estimation over time.

---

## Level 5 — Controlled Model Improvement

Future learning may include:

* Strategy weighting.
* Signal ranking.
* Confidence calibration.
* Feature importance.
* Model comparison.
* Experiment tracking.

Any automated model adaptation must be:

```text
Versioned
Auditable
Reversible
Measured
```

Never silently modify production logic.

---

# 9. Decision Auditability

Every recommendation must be recorded.

A decision record should contain:

```text
Decision ID
Timestamp
Instrument
Market Price
Action
Entry
Stop Loss
Target
Quantity Calculation
Capital Configuration
Risk Configuration
Market Regime
Technical Evidence
Research Evidence
News Evidence
Strategy Version
Model Version
Confidence
Reasoning
Risk Decision
Final Recommendation
```

Example:

```text
DECISION
│
├── INPUT DATA
│
├── MARKET CONTEXT
│
├── TECHNICAL ANALYSIS
│
├── RESEARCH EVIDENCE
│
├── AI REASONING
│
├── STRATEGY RESULT
│
├── RISK CALCULATION
│
└── FINAL RECOMMENDATION
```

The system must be able to answer:

> Why did you recommend this stock?

> Why at this time?

> Why this entry?

> Why this quantity?

> Why this stop loss?

> What evidence supported the decision?

> Which model made this reasoning?

> Which strategy version was used?

> What eventually happened?

---

# 10. Data Source Strategy

The system should use legitimate, reliable sources appropriate for each data type.

Potential categories:

## Real-Time Market Data

* Dhan market data.
* Approved broker/data-provider APIs.

## Exchange Information

* NSE official information where legitimately accessible.
* BSE official information where legitimately accessible.

## Company Information

* Corporate announcements.
* Exchange filings.
* Earnings information.
* Public disclosures.

## News

Only legitimate and permitted sources.

Every external source should track:

```text
Source Name
Source Type
URL/API
Timestamp
Data Freshness
Reliability Status
Failure Status
```

The system must not silently rely on scraped or unreliable data.

---

# 11. Market Intelligence Layer

This layer answers:

> What is happening in the market right now?

## 11.1 Market Regime Detection

Possible states:

```text
BULLISH
BEARISH
SIDEWAYS
HIGH_VOLATILITY
LOW_VOLATILITY
RISK_ON
RISK_OFF
UNKNOWN
```

Inputs may include:

* Index trends.
* Volatility.
* Breadth.
* Sector participation.
* Volume.
* Price structure.

---

## 11.2 Sector Strength

Example:

```text
IT:
Strong

BANKING:
Moderate

ENERGY:
Strong

PHARMA:
Weak
```

This helps identify where capital is moving.

---

## 11.3 Market Breadth

Monitor:

```text
Advancing Stocks
Declining Stocks
Advance/Decline Ratio
New Highs
New Lows
Sector Participation
```

---

# 12. Market Scanner

The scanner should process a large market universe.

Example pipeline:

```text
Market Universe
      ↓
Liquidity Filter
      ↓
Price Filter
      ↓
Volume Filter
      ↓
Volatility Filter
      ↓
Trend Detection
      ↓
Breakout Detection
      ↓
Relative Strength
      ↓
Sector Strength
      ↓
Candidate Ranking
```

Output:

```text
Top Market Candidates
```

Example:

```text
Rank  Instrument  Opportunity Score

1     RELIANCE    87
2     TCS         84
3     ICICIBANK   81
4     INFY        79
5     HDFCBANK    76
```

---

# 13. Technical Analysis Engine

Technical calculations must be deterministic.

Potential indicators:

```text
SMA
EMA
RSI
MACD
VWAP
ATR
Bollinger Bands
Volume Analysis
Support/Resistance
Trend Strength
Relative Strength
Breakout Detection
```

Rules must be versioned.

Example:

```text
indicator_version:
technical-v2
```

Historical decisions must remain reproducible.

---

# 14. AI Research Layer

AI should act as a research and reasoning assistant.

Potential agents:

```text
Market Research Agent
News Research Agent
Company Research Agent
Sector Research Agent
Macro Research Agent
Risk Analyst Agent
```

AI outputs must be structured.

Example:

```json
{
  "summary": "...",

  "bull_case": [],

  "bear_case": [],

  "risks": [],

  "unknowns": [],

  "evidence": [],

  "confidence": 0.72
}
```

AI must distinguish:

```text
FACT
INFERENCE
UNCERTAINTY
```

---

# 15. Opportunity Scoring

The system should combine multiple signals.

Example:

```text
Technical Score:
82

Market Context Score:
75

Sector Score:
88

Liquidity Score:
95

Volatility Risk Score:
60

Research Score:
72
```

Then:

```text
Overall Opportunity Score:
81 / 100
```

Scoring formulas must be explicit and versioned.

---

# 16. Recommendation Engine

Possible recommendation states:

```text
BUY
WATCH
AVOID
EXIT
NO_ACTION
```

The system should not force recommendations.

Most market states should be allowed to produce:

```text
NO_ACTION
```

A good system must be comfortable saying:

> No high-quality opportunity currently detected.

---

# 17. Dynamic Position Sizing

Capital is configurable.

Example configuration:

```yaml
portfolio:
  available_capital: 50000

risk:
  max_risk_per_trade_percent: 1.0
  max_daily_risk_percent: 3.0
```

Position sizing formula:

```text
Maximum Risk Amount
=
Available Capital × Risk Percentage
```

```text
Risk Per Share
=
Entry Price − Stop Loss
```

```text
Maximum Quantity
=
Maximum Risk Amount / Risk Per Share
```

Additional constraints:

```text
Maximum Position Exposure
Maximum Daily Exposure
Minimum Liquidity
Maximum Number of Open Positions
```

---

# 18. Paper Trading

Paper trading remains the primary validation environment.

Architecture:

```text
Recommendation
      ↓
Paper Trade
      ↓
Virtual Position
      ↓
Market Monitoring
      ↓
Exit Condition
      ↓
Result
```

Paper trading should simulate:

* Entry.
* Stop-loss.
* Target.
* Time expiration.
* Position closure.
* P&L.

---

# 19. Continuous Background Operation

The system should eventually run continuously according to market schedules.

Example:

```text
Pre-Market:
Research + preparation

Market Open:
Live monitoring

Market Hours:
Data ingestion + scanning + prediction tracking

After Market:
Performance evaluation

Night:
Research + analytics + learning
```

Conceptually:

```text
24 Hour Intelligence Cycle
```

Even though markets are not open continuously.

---

# 20. Prediction Lifecycle

Every prediction follows:

```text
CREATED
   ↓
ACTIVE
   ↓
ENTRY_REACHED / MISSED
   ↓
TARGET / STOP / EXPIRED
   ↓
EVALUATED
   ↓
LEARNING DATA GENERATED
```

---

# 21. Performance Intelligence

The system should maintain dashboards for:

## Overall Performance

```text
Predictions Generated
Successful Predictions
Failed Predictions
Expired Predictions
Accuracy
Average Return
Maximum Drawdown
```

## Strategy Performance

```text
Strategy
Market Regime
Win Rate
Average Return
Sample Size
Confidence Calibration
```

## AI Performance

Measure whether AI reasoning improves decisions compared to:

```text
Baseline deterministic strategy
```

---

# 22. Dashboard Requirements

The dashboard should eventually provide:

## Live Market Overview

```text
Market:
OPEN

NIFTY:
Trend

BANK NIFTY:
Trend

Market Regime:
BULLISH
```

---

## Top Opportunities

```text
Rank
Stock
Action
Confidence
Entry
Stop
Target
```

---

## Recommendation Detail

```text
Why?
Evidence
Technical Signals
Market Context
Research
Risks
Invalidation Conditions
```

---

## Prediction History

```text
Prediction
Outcome
Actual Result
Accuracy
Reasoning
```

---

## Learning Dashboard

```text
Which strategies are working?

Which market conditions are profitable?

Where is confidence inaccurate?

Which models perform best?
```

---

# 23. Long-Term Phase Roadmap

---

# Phase 17 — Production Readiness

Status:

```text
COMPLETE ON BRANCH
MERGE STATUS MUST BE VERIFIED
```

Objectives:

* Reliable installation.
* Startup lifecycle.
* Shutdown lifecycle.
* Operational observability.
* Full regression stability.

---

# Phase 18 — Market Intelligence Foundation

## Objective

Create the foundational market intelligence layer.

## Deliverables

### Market Data Abstraction

Unified interfaces for:

```text
Live Data
Historical Data
Exchange Data
Research Data
```

### Market Universe

Build instrument universe management.

Examples:

```text
NIFTY 50
NIFTY 100
NIFTY 500
Configured Watchlists
```

### Market State Model

Create:

```text
MarketSnapshot
InstrumentSnapshot
SectorSnapshot
MarketRegime
```

### Data Quality

Implement:

```text
Freshness
Completeness
Source Health
Timestamp Validation
Duplicate Detection
```

### Acceptance Criteria

```text
Market data sources are abstracted.
Market state can be persisted.
Data quality is measurable.
No trading recommendation logic yet.
```

---

# Phase 19 — Market Scanner & Candidate Discovery

## Objective

Automatically identify potentially interesting instruments.

## Capabilities

```text
Liquidity Screening
Volume Screening
Momentum Detection
Breakout Detection
Trend Detection
Relative Strength
Sector Strength
```

## Output

```text
Ranked Candidate List
```

## Acceptance Criteria

```text
Scanner runs independently.
Scanner produces reproducible rankings.
Every score is explainable.
Historical scanner output is stored.
```

---

# Phase 20 — Research Intelligence

## Objective

Add evidence-backed research.

## Components

```text
News Collection
Company Events
Sector Analysis
Market Research
AI Research Summaries
```

## Critical Requirement

Every AI conclusion must include:

```text
Evidence
Source
Timestamp
Confidence
Unknowns
```

---

# Phase 21 — Decision Intelligence Engine

## Objective

Combine all intelligence into structured recommendations.

## Inputs

```text
Market Context
Technical Analysis
Scanner Score
Research Evidence
Risk Context
```

## Outputs

```text
BUY
WATCH
AVOID
EXIT
NO_ACTION
```

## Acceptance Criteria

```text
No recommendation without recorded evidence.
Decision is reproducible.
Decision version is stored.
```

---

# Phase 22 — Dynamic Risk & Position Sizing

## Objective

Separate market opportunity from personal capital.

## Features

```text
Dynamic Capital
Risk Per Trade
Daily Risk Limit
Position Size
Maximum Exposure
```

Capital changes must not require code changes.

---

# Phase 23 — Shadow Prediction & Continuous Evaluation

## Objective

Allow the system to learn without user trading.

## Features

```text
Prediction Recording
Outcome Monitoring
Target Tracking
Stop Tracking
Expiration
Prediction Scoring
```

This phase is critical.

The system should run:

```text
Even when user does not trade.
```

---

# Phase 24 — Performance Learning System

## Objective

Measure and improve intelligence quality.

## Features

```text
Strategy Comparison
Market Regime Performance
Confidence Calibration
Signal Quality
Experiment Tracking
Model Comparison
```

## Rule

No automatic strategy modification without:

```text
Versioning
Evaluation
Rollback Capability
Audit Trail
```

---

# Phase 25 — AI Multi-Agent Market Research

## Objective

Build specialized AI research agents.

Possible agents:

```text
Market Analyst
Technical Analyst
News Analyst
Sector Analyst
Risk Critic
Decision Reviewer
```

Agents must not independently execute trades.

---

# Phase 26 — Live Market Decision Dashboard

## Objective

Create the primary user interface.

The dashboard should answer:

```text
What should I watch?

What opportunities exist?

Why?

When should I enter?

What is the stop?

What is the target?

How many units based on my current capital?

How confident is the system?

What are the risks?
```

---

# Phase 27 — End-to-End Shadow Trading Validation

## Objective

Run the complete system without real orders.

```text
Live Market
↓
Research
↓
Analysis
↓
Recommendation
↓
Shadow Prediction
↓
Outcome
↓
Evaluation
```

Run for sufficient time before considering higher-risk functionality.

---

# Phase 28+ — Future Expansion

Possible future work:

```text
Portfolio Intelligence
Multi-Timeframe Strategies
Options Analysis
Advanced ML Models
Backtesting Infrastructure
Experiment Platform
Mobile Dashboard
Alerts
Scheduled Reports
```

These are not automatically approved and require separate architecture review.

---

# 24. Phase Execution Rules

Every future phase must follow this process.

## Step 1 — Understand Existing System

Before changing code:

```text
Read relevant architecture.
Read current implementation.
Read existing tests.
Read previous phase documentation.
```

Never assume.

---

## Step 2 — Define Scope

Document:

```text
Objective
In Scope
Out of Scope
Acceptance Criteria
Risks
Dependencies
```

---

## Step 3 — Create Branch

Example:

```text
phase-18-market-intelligence-foundation
```

---

## Step 4 — Baseline Verification

Before changes:

```bash
git status
git branch --show-current
pytest
```

Record baseline.

---

## Step 5 — Implement Incrementally

For every component:

```text
Design
Implement
Test
Review
```

Do not perform uncontrolled large refactors.

---

## Step 6 — Test

Required levels:

```text
Unit Tests
Integration Tests
Regression Tests
Safety Tests
```

Where applicable:

```text
Real Service Verification
```

---

## Step 7 — Audit

Check:

```text
Secrets
Credentials
Data leakage
Dead code
Thread safety
Failure recovery
Observability
Documentation
```

---

## Step 8 — Commit

Commits must be:

```text
Atomic
Meaningful
Scoped
Reversible
```

---

## Step 9 — Push

Push branch only after verification.

---

## Step 10 — Final Reconciliation Audit

Before merging:

```text
Production Code
Tests
Documentation
Git History
Secrets
Architecture
Scope
Known Limitations
```

---

## Step 11 — Merge Decision

Never merge automatically unless explicitly authorized.

---

# 25. Evidence Classification

All future reports must distinguish evidence honestly.

Use only:

```text
REAL SERVICE VERIFIED
LOCAL/INTEGRATION VERIFIED
LOCAL/DETERMINISTIC TEST VERIFIED
STRUCTURALLY VERIFIED
NOT VERIFIED
BLOCKED
```

Never claim:

```text
"Works"
```

without identifying the evidence level.

---

# 26. Safety Rules

The following remain mandatory.

## No Accidental Real Orders

Real order execution must remain structurally disabled.

## No Credential Exposure

Secrets must never appear in:

```text
Logs
Exceptions
CLI Output
Git
Tests
Documentation
```

## No Fake Real-Service Claims

Mocked tests must never be described as live verification.

## No Silent Learning

Any adaptive system must be measurable and auditable.

## No Silent Model Changes

Models and strategies must be versioned.

## No Unexplained Recommendation

Every recommendation requires evidence.

---

# 27. Non-Goals

The project is NOT:

```text
A guaranteed-profit system.
A magic AI stock predictor.
An uncontrolled autonomous trading bot.
A system that blindly trusts LLM output.
A system that executes real orders without explicit future architectural review.
```

---

# 28. Definition of Long-Term Success

The project can be considered mature when the system can continuously demonstrate:

```text
1. Reliable market data ingestion.

2. Market-wide opportunity discovery.

3. Evidence-backed research.

4. Deterministic technical analysis.

5. AI-assisted reasoning.

6. Structured recommendations.

7. Dynamic position sizing.

8. Complete decision auditability.

9. Continuous shadow prediction.

10. Outcome tracking.

11. Measurable strategy performance.

12. Confidence calibration.

13. Continuous improvement based on evidence.

14. Live dashboard visibility.
```

The ultimate product experience should be:

> Open the dashboard and understand what the market is doing, which opportunities exist, why they exist, what risks are involved, what the system recommends, how the recommendation performed historically, and how the system arrived at every decision.

---

# 29. Current Strategic Direction

The project has completed foundational infrastructure work.

The next major transition is:

```text
FROM:

Trading Infrastructure

TO:

Market Intelligence Platform
```

The recommended immediate sequence is:

```text
Phase 17
↓
Merge after verification/authorization
↓
Phase 18
Market Intelligence Foundation
↓
Phase 19
Market Scanner
↓
Phase 20
Research Intelligence
↓
Phase 21
Decision Intelligence
↓
Phase 22
Dynamic Risk & Position Sizing
↓
Phase 23
Shadow Prediction
↓
Phase 24
Continuous Learning
↓
Phase 25
AI Multi-Agent Research
↓
Phase 26
Live Dashboard
↓
Phase 27
Long-Term Shadow Validation
```

---

# 30. Final Project Principle

TradingAgents must continuously answer four questions:

```text
WHAT is happening in the market?

WHY is it happening?

WHAT should be watched or considered?

WAS the previous prediction actually correct?
```

The fourth question is what makes the system improve.

The system should not simply generate recommendations.

It should measure whether those recommendations deserved trust.

---

**END OF AUTHORITATIVE PROJECT BLUEPRINT**