# Security Review

Strategy science mission, Phase 17. Evidence-based review covering SQL
injection, XSS, path traversal, secrets in git history, and other common
issue classes. Source of truth is always the code, not this document.

## 1. SQL injection — CLEAN

Every SQL query across all 9 store modules (`paper/store.py`,
`live/state_store.py`, `scheduler/store.py`, `market_intelligence/store.py`,
`strategy/promotion_store.py`, `decision_engine/store.py`,
`research/store.py`, `predictions/store.py`, `experiments/store.py`) that
carries an externally-influenced value uses `?` parameterized placeholders,
never string interpolation. One f-string-built query exists
(`paper/store.py:309`, `f"SELECT data_json FROM {table}"`) but `table` is
always a hardcoded literal at every call site — not reachable from any CLI
argument or user input.

## 2. XSS in the dashboard — CLEAN

`dashboard/app.py` renders HTML by hand (no auto-escaping templating
engine), so every interpolation of external/user-influenced data was
checked individually: the kill-switch reason form field, the `/intelligence/
{symbol}` URL path parameter, real news headlines from `research/news.py`,
AI narrative/decision rationale text, and signal IDs used inside HTML
attributes (the higher-risk case, since attribute breakout is the classic
XSS vector). Every site applies `html.escape()` before interpolation. No
unescaped site was found.

## 3. Path traversal — REAL GAP, FOUND AND FIXED

`backtesting/cache.py`'s `_csv_path` joined a symbol string directly into a
filesystem path (`self._cache_root / symbol / f"{interval}.csv"`) with no
validation beyond `.strip().upper()`. `market_data/universe.py`'s
`from_watchlist` (the normal CLI entry point for `--symbols`/
`--watchlist-file`) rejects commas and whitespace but never path separators
or `..`. A crafted symbol — realistically arriving via a shared/downloaded
watchlist YAML, not necessarily a hostile CLI user — containing
`../../../etc/passwd`-style segments could escape `data/market/` entirely,
both for writing (`_write`, cache population) and reading (`_read`), and
the identical unvalidated join existed in Phase 12's own
`report_cache_staleness`.

**Fixed**: `backtesting/cache.py` gains `_validate_symbol_for_path()`, an
ALLOWLIST (not blocklist) matching this project's own real symbol shapes
(`data/market/`'s actual directory names: uppercase letters, digits, `.`
for exchange suffixes like `RELIANCE.NS`, `^` for index prefixes like
`^NSEI`, `-` for share-class tickers). A blocklist of specific bad
characters was deliberately not used — it's fragile against a bypass this
allowlist doesn't need to anticipate. Also explicitly rejects a symbol made
entirely of dots (e.g. `".."`), which would otherwise pass the character
allowlist yet still act as a parent-directory navigation token as a single
path component (no `/` required — a bare `..` component is enough).
Wired into both `CachedMarketDataProvider.fetch_ohlcv()` and
`report_cache_staleness()`, the two vulnerable sinks. Deliberately fixed at
the point where the path is actually constructed (defense at the trust
boundary) rather than only at the upstream `from_watchlist` entry point,
so it holds regardless of what future code path feeds a symbol in.

16 new tests: 8 malicious payloads rejected (`../../../etc/passwd`,
Windows-style `..\..\`, bare `..`/`...`, embedded `FOO/../../BAR`,
`FOO/BAR`, `FOO\BAR`, empty string) across both vulnerable functions, a
belt-and-suspenders check that no file actually lands outside `cache_root`
for a realistic payload, and 5 real-world legitimate symbols
(`AAPL`, `RELIANCE.NS`, `^NSEI`, `BRK-B`, `TATASTEEL.NS`) confirmed never
rejected.

## 4. Secrets in git history — CLEAN

Searched the full commit history (91 commits) for credential-shaped
patterns. Every match is either documentation referencing environment
variable *names* (never values) or test fixtures with explicitly fake
values (`"fake-token-for-tests"`, `"super-secret-value-should-never-
appear"`). No `.env` file was ever committed; `.gitignore` has excluded
`.env*` since early history.
`tests/test_dhan_credential_security.py` already has a structural test
asserting no tracked file contains a plausible Dhan access-token pattern.

## 5. Other findings

- **No `eval`/`exec`/`os.system`/`shell=True`/unsafe `pickle`/unsafe
  `yaml.load`** anywhere in project code (only in third-party `venv/`
  packages, out of scope). `market_data/universe.py` correctly uses
  `yaml.safe_load`.
- **No CSRF protection on the dashboard's state-changing routes**
  (`/approve`, `/reject`, `/kill-switch/activate`, `/kill-switch/reset`) —
  reasonable for the documented local-only, single-user threat model, but
  the `--host` flag can be pointed at a non-loopback address with no
  warning. **Fixed**: `run_dashboard_command` now prints an explicit
  warning naming the exact risk (no auth/CSRF on the kill-switch and
  approve/reject routes) whenever `--host` isn't `127.0.0.1`/`localhost`/
  `::1` — never blocked outright (a user may have a real reason to reach
  this from another device on their own trusted network), just made
  visible instead of silent. 2 new tests confirm the warning fires for
  `0.0.0.0` and stays silent for the default loopback host.
- `uvicorn.run(...)` has no debug/reload mode enabled — appropriate for
  the stated threat model.
