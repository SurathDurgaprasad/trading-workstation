# Installation

Everything needed to get from a fresh clone to a running system. No
step here requires Claude Code, an IDE, or any tool beyond Python and
(optionally) Ollama.

## Requirements

- Python 3.11+ (developed and tested against the version in `venv/`'s
  own `pyvenv.cfg`; any recent 3.11+ should work)
- ~200 MB free disk for dependencies, more for cached market data if
  you use the backtest cache
- Windows, macOS, or Linux — the codebase is pure Python plus SQLite;
  nothing platform-specific in the core pipeline
- **Optional**: [Ollama](https://ollama.com), only if you want the AI
  narration/summary features or the `analyze`/`review` commands. Every
  other command works with no Ollama installed.
- **Optional**: a Dhan broker account and API credentials, only if you
  want the real market-data feed instead of the built-in mock replay.
  Paper trading works identically either way — no code path in this
  repository can place a real order regardless of whether Dhan
  credentials are configured (see `SECURITY.md`).

## Steps

1. **Clone the repository.**

   ```bash
   git clone <repository-url>
   cd TradingAgents
   ```

2. **Create and activate a virtual environment.**

   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # macOS/Linux
   ```

3. **Install dependencies.**

   ```bash
   pip install -r requirements.txt
   ```

   This installs every package the application code directly imports
   (`requirements.txt` documents direct dependencies, not a full `pip
   freeze` — see that file's own header comment). No other setup step
   is required for this to succeed; there is no compiled extension,
   database server, or external service to stand up first.

4. **(Optional) Configure Dhan credentials**, only if you want the real
   market-data feed:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN`
   (generate a token from web.dhan.co → My Profile → Access DhanHQ
   APIs; it is valid 24 hours). `.env` is already `.gitignore`'d —
   never commit it. Nothing in this repository auto-loads `.env`; you
   must `export` these into your shell (or use your OS/secret
   manager's own env-var mechanism) before running a command that
   needs them.

5. **(Optional) Install Ollama**, only if you want AI narration/summary
   features or `analyze`/`review`:

   ```bash
   ollama pull qwen2.5-coder:7b
   ollama pull nomic-embed-text
   ollama serve
   ```

6. **Run the test suite** to confirm the install is healthy:

   ```bash
   pytest
   ```

   Run this from the project root (the directory containing `main.py`)
   — a handful of tests spawn `python -m mcp_server.server` as a real
   subprocess, which needs the current working directory to resolve
   that module. This requires no Ollama, no Dhan credentials, and no
   network access — every test is self-contained. A small number of
   tests that use locally-cached historical market data (`data/market/`)
   skip cleanly if that cache is absent (it is intentionally not
   committed to the repository) — this was verified with a genuine
   clean clone + fresh venv + single `pytest` invocation: 2020 passed,
   0 failed, 82 skipped, no network-dependent test left unaccounted
   for.

7. **Run a health check** against a real (mock-data) pipeline pass:

   ```bash
   python main.py readiness-check
   ```

8. **Try it.**

   ```bash
   python main.py scan --symbols AAPL,MSFT,RELIANCE.NS
   python main.py dashboard
   ```

   Open `http://127.0.0.1:8000` (or whatever port `dashboard` prints)
   in a browser.

## Verifying independence from any AI coding tool

This application has no runtime dependency on Claude Code, Claude
Desktop, or any AI-agent tooling — it was *developed* using Claude Code
(hence the `.claude/` directory in this repository), but nothing in
`main.py`, `dashboard/`, `scheduler/`, `paper/`, `decision_engine/`,
`live/`, or any other runtime module imports, shells out to, or checks
for the presence of any such tool. `mcp_server/` is a separate, opt-in
process (`python -m mcp_server.server`) for AI-assistant observability
— it is never imported by `main.py`'s own command set and is not
required for any core-pipeline command to work.

To verify this yourself: run steps 1–8 above from a plain terminal,
with no editor, IDE, or AI agent attached to the process at all. Every
command works identically.

## Troubleshooting a failed install

See `TROUBLESHOOTING.md`. The most common causes of a failed `pip
install` are an unsupported Python version or a network-blocked pip
index — neither is specific to this project.
