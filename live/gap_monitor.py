"""Real-time strategy validation mission, multi-symbol hardening pass --
closes a real, live-observed gap from the 2026-09-15 market-hours
session (docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md): a real
~15-minute Dhan tick-delivery gap occurred near market close with the
feed's own reported `state` remaining CONNECTED throughout (not a
disconnect) -- the freshness guard safely suppressed the one late bar
that eventually arrived, but nothing surfaced the GAP ITSELF while it
was happening; it was only reconstructable afterward from bar
timestamps.

`BarGapMonitor` is a small, pure, in-memory, per-symbol tracker: the
caller tells it whenever a genuinely NEW bar was processed
(`record_new_bar`), and asks on every loop iteration -- including
"nothing new this poll" ones -- whether the elapsed wall-clock time
since the last new bar has crossed a threshold (`check`). It has no
knowledge of WebSocket connection state, freshness policy, or anything
else in live/pipeline.py -- deliberately: this module is a pure
OBSERVABILITY layer, wired in from main.py's own CLI loop (see
_run_paper_live_loop), not a change to the sacred trading pipeline
itself. It never influences a trading decision.

Distinguishing the three states the mission asks for:
  - connected + receiving data: no BarGapMonitor.check() result (elapsed
    is within threshold).
  - connected + no data (this module's own reason to exist): the feed's
    own `state` is unchanged/CONNECTED (a live/pipeline.py concern, not
    this module's), but check() reports a gap -- new bars have simply
    stopped arriving.
  - disconnected: a completely separate, ALREADY-EXISTING signal
    (PipelineStepResult.kind == "FEED_DISCONNECTED"), printed distinctly
    by main.py's own existing code; this module is not involved.
  - stale/delayed data: a bar DID arrive but PipelineStepResult.freshness
    .is_fresh is False -- also an existing, already-printed signal. This
    module adds the missing piece: HOW LONG has it actually been since
    the last new bar, reported as the gap crosses a threshold, not only
    reconstructable after the fact.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class GapStatus:
    elapsed: timedelta
    threshold: timedelta
    is_new: bool
    """True the FIRST time this specific gap crossed the threshold;
    False for a periodic repeat report while the SAME gap persists (see
    `BarGapMonitor.repeat_warning_interval`) -- lets a caller phrase the
    first report ("gap detected") differently from a later one ("gap
    still ongoing, now Ns")."""


@dataclass
class BarGapMonitor:
    """One instance per symbol (mirrors this project's established
    one-per-symbol lifecycle for CandleBuilder/CriticGate). Tracks ONLY
    wall-clock inter-arrival time between new bars -- never touches bar
    content, prices, or anything decision-relevant."""

    expected_interval: timedelta
    gap_multiplier: float = 3.0
    """A gap is flagged once elapsed time since the last new bar exceeds
    expected_interval * gap_multiplier. Deliberately more lenient than
    live.freshness.FreshnessPolicy's own default 2x multiplier: that
    threshold governs whether a specific BAR is safe to open a new
    position on (a correctness/safety question); this one governs when
    to make NOISE about a delivery gap (an observability question) --
    different stakes, so a false-positive gap warning on ordinary
    network jitter is worse here than being a little slow to flag a
    genuine gap."""
    repeat_warning_interval: timedelta = timedelta(seconds=60)
    """Once a gap is being reported, do not re-report on every single
    poll iteration (which could be many times a second) -- only escalate
    again after this much additional wall-clock time, so a long real gap
    produces periodic updates rather than a flood of identical lines."""

    _last_new_bar_at: datetime | None = field(default=None, repr=False, init=False)
    _last_gap_report_at: datetime | None = field(default=None, repr=False, init=False)
    _gap_active: bool = field(default=False, repr=False, init=False)

    def record_new_bar(self, *, now: datetime) -> None:
        """Call every time a genuinely NEW bar was processed for this
        symbol (any PipelineStepResult carrying one, regardless of what
        happened to it next -- BAR_PROCESSED, PENDING_HUMAN_APPROVAL,
        CRITIC_REJECTED, KILL_SWITCH_ACTIVE, STALE_SIGNAL_SUPPRESSED --
        the gap this module watches for is about DELIVERY, not about
        what the pipeline decided to do with what was delivered).
        Resets the gap clock and clears any currently-active gap."""
        self._last_new_bar_at = now
        self._last_gap_report_at = None
        self._gap_active = False

    def check(self, *, now: datetime) -> GapStatus | None:
        """Call on EVERY poll iteration, including ones where nothing
        new arrived. Returns a GapStatus the first time a gap crosses
        the threshold, again every `repeat_warning_interval` while it
        persists, else None. Returns None unconditionally before the
        first `record_new_bar` call -- there is no baseline yet, and a
        session that has not received its first bar is not "gapped",
        it simply has not started."""
        if self._last_new_bar_at is None:
            return None
        elapsed = now - self._last_new_bar_at
        threshold = self.expected_interval * self.gap_multiplier
        if elapsed <= threshold:
            return None
        if not self._gap_active:
            self._gap_active = True
            self._last_gap_report_at = now
            return GapStatus(elapsed=elapsed, threshold=threshold, is_new=True)
        if self._last_gap_report_at is not None and (now - self._last_gap_report_at) >= self.repeat_warning_interval:
            self._last_gap_report_at = now
            return GapStatus(elapsed=elapsed, threshold=threshold, is_new=False)
        return None
