# Contributing

This is a personal research and engineering project, published as a portfolio piece —
not a maintained open-source product with a roadmap or a release cadence. There is no
guarantee of a timely response to issues or pull requests.

That said, contributions are genuinely welcome, especially:

- Bug reports with a concrete reproduction (a failing test is ideal).
- Corrections to anything factually wrong in the documentation, especially the research
  results or safety claims — those need to stay accurate above all else.
- Extensions to the offline research infrastructure (`backtesting/`, `quant_research/`)
  that follow the existing preregistration/leakage-audit/cost-model discipline described
  in [`docs/RESEARCH_METHODOLOGY.md`](docs/RESEARCH_METHODOLOGY.md).

## Ground rules for a pull request

1. **Never weaken the real-order safety architecture** (`DisabledDhanOrderExecutor`,
   `RealOrderPlacementDisabledError` — see [`docs/SAFETY.md`](docs/SAFETY.md)). A PR
   that adds a real order-placement code path, or any way to configure around the
   disabled executor, will not be merged.
2. **Never commit a real credential**, anywhere, in any file, including test fixtures.
   Use `.env.example`'s placeholders as the pattern.
3. **New trading hypotheses must be preregistered before their result is inspected** —
   see [`docs/RESEARCH_METHODOLOGY.md`](docs/RESEARCH_METHODOLOGY.md). A PR that adds a
   hypothesis with its verdict already decided, or that quietly reruns a closed research
   family, will be asked to follow the existing discipline instead.
4. **Do not claim profitability, and do not remove or soften the existing "no
   demonstrated edge" findings** to make a change look more impressive. Negative
   results are the point of this project's research registry — see
   [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).
5. Run the test suite before opening a PR (`pytest`) — it requires no credentials and no
   live connection, see [`docs/OPERATIONS.md`](docs/OPERATIONS.md).
6. Keep the two pipelines separate: the paper-trading execution path
   (`paper/`, `live/`, `strategy/`, `risk/`) and the market-intelligence path
   (`market_intelligence/`, `research/`, `decision_engine/`, `predictions/`) only touch
   through the one deliberate, opt-in bridge (`--paper-execute`) — see
   [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Reporting a security concern

See [`SECURITY.md`](SECURITY.md#reporting-a-concern).
