# Investigation: the repeated ~15:13-15:14 IST fleet-wide Dhan feed interruption

Scope: correlate the 2026-09-17 and 2026-09-22 live-session incidents against every
available local and code-level signal, to narrow (not yet prove) whether the cause is
external (Dhan/NSE-side) or local (this host/network/process). No strategy, risk, or
research logic was touched. **This is a diagnostic document, not a fix** — no source
code change follows from this investigation (the separate startup-environment guard
added tonight, in `live/environment_guard.py`, is an unrelated fix for a different,
already-understood issue).

**Evidence labels**: REAL (observed directly from a real log/event source),
MECHANISM-VERIFIED (proven by reading this project's own already-committed source),
INFERENCE (a reasoned conclusion from real evidence, not itself directly observed),
UNKNOWN (checked for, not found, and not confidently explainable either way).

## 1. The two incidents, side by side (REAL)

| | 2026-09-17 | 2026-09-22 |
|---|---|---|
| Fleet launch | 09:12:15 IST | 09:18:22 IST |
| First simultaneous gap | ~15:13 IST (09:43:00 UTC last bar) | ~15:14 IST (09:44:00 UTC last bar) |
| Time from launch to gap | ~6h01m | ~5h56m |
| Time from gap to NSE close (15:30 IST) | ~17 min | ~16 min |
| Reconnect logic engaged? | **No** — workers stayed CONNECTED, received nothing, for 600s+ without any `on_close`/`on_error`/reconnect firing (this was the ORIGINAL, undiagnosed incident) | **Yes** — every symbol crossed the (since-added) 300s silent-loss watchdog and successfully reconnected, 2-3 times each, between 15:19 and 15:33 IST |
| Manual intervention needed | Yes (none performed; session ended at close before self-healing could be assessed) | No — fully automatic recovery, confirmed |

Both incidents are drawn from real, already-committed session logs
(`docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-17.md` §9, and today's own
`runtime/*/logs/session.log`, `docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-22.md` §8).

## 2. This is NOT a newly-discovered phenomenon (MECHANISM-VERIFIED)

`live/dhan/market_data_source.py`'s `connected_idle_timeout_seconds` field carries a
long docstring, already committed before tonight, that documents the 2026-09-17
incident in detail and explicitly names three candidate causes:

> "The exact upstream cause of today's incident is UNKNOWN (Dhan-side session/
> connection-duration policy, an intermediate network device silently dropping an
> idle mapping, and a real, independently-observed Windows DNS-registration-timeout/
> NETLOGON-secure-session error on this host in the same window are all consistent
> with the evidence but none is proven) -- this field closes the gap regardless of
> which of those is the true cause."

That prior session already found the same local DNS/NETLOGON evidence tonight's
investigation re-confirms (§3), already declined to guess between the three
candidates, and built the 300s idle-connection watchdog specifically so the fleet
would recover automatically regardless of which one was true. **Tonight's finding is
that this watchdog worked correctly tonight, on a second real occurrence, exactly as
designed** — this is new, valuable confirmation, not a new incident.

## 3. Local-host evidence (REAL, Windows Event Log, both dates)

Checked: System, Application, `Microsoft-Windows-NetworkProfile/Operational`,
`Microsoft-Windows-Dhcp-Client/Admin`, `Microsoft-Windows-DNS-Client/Operational`,
`Microsoft-Windows-TCPIP/Operational`, `Microsoft-Windows-Time-Service`,
`Microsoft-Windows-WLAN-AutoConfig/Operational`, `Microsoft-Windows-Windows Defender/
Operational`, RAS/VPN client events, Task Scheduler. Log retention confirmed
sufficient for both dates (System log back to 2026-06-30, Application back to
2026-06-08 — both well before 2026-09-17).

**2026-09-17, 14:55-15:40 IST window** — two real, timestamped local anomalies found,
bracketing the 15:13 gap:
- **15:09:49 IST**, `Microsoft-Windows-DNS-Client` Warning (event 8015): host A/AAAA
  record registration failed — "the update request it sent to the DNS server timed
  out," server `205.251.197.33:53`.
- **15:21:14 IST**, `NETLOGON` Error (event 5719): "This computer was not able to set
  up a secure session with a domain controller in domain IDEABYTES... An internal
  error occurred... Make sure that this computer is connected to the network."

Both are genuine symptoms of a brief loss of network reachability/name resolution on
this host, in a window that contains the 15:13 gap.

**2026-09-22, 14:55-15:40 IST window** — **zero** matching events in any of the same
channels. No DNS registration failure, no NETLOGON error, no network-profile change,
no DHCP renewal, no adapter reset, no Time-Service resync, no Defender/firewall event,
no scheduled task firing in that window.

**This is a real asymmetry, not explained away**: if a local network blip were the
*sole* cause, its own footprint should plausibly appear on both days, not just one.
It does not. This weakens (does not eliminate) the local-network-blip hypothesis as
the *sole* explanation.

**Important caveat, stated precisely rather than glossed over**: DNS host-record
registration and NETLOGON secure-channel refresh are *periodic, non-continuous*
background probes (they run on their own independent timers, not once per second).
Their absence on 09-22 proves only that *neither specific periodic probe happened to
land inside the outage window that day* — it does not prove no brief network
interruption occurred at all. This is genuinely inconclusive, not a clean acquittal.

## 4. VPN (GlobalProtect) — ruled out for both incidents (REAL)

This host has Palo Alto Networks GlobalProtect installed (`PanGPS` service, currently
running) and a `PANGP Virtual Ethernet Adapter` (currently Disabled). Its own event
log (`C:\Program Files\Palo Alto Networks\GlobalProtect\pan_gp_event.log`) records
every portal login, tunnel creation, and disconnection since 2026-09-12. **The VPN
tunnel was only ever actually established once in the entire retained log: 2026-09-16,
12:45:21-13:45:59 IST** — a single ~1-hour session, unrelated to either incident date
or time. On both 2026-09-17 and 2026-09-22, the only GlobalProtect log entries are
ordinary service start/stop events, none within hours of either 15:13/15:14 gap. **A
VPN reconnect/rekey event is definitively ruled out as the cause of either incident.**

## 5. The `code=805` disconnects during recovery are a well-understood side effect, not a separate mystery (INFERENCE, grounded in real evidence)

Tonight's fleet also logged 0-3 `code=805` ("too many WebSocket connections for this
client ID") disconnects per symbol during the 15:19-15:33 IST recovery window, on top
of the primary silent-loss events. This is very likely the **same, already-documented
dynamic** the launch-time `--launch-stagger-seconds` setting exists to reduce (see
`live/fleet_supervisor.py`'s own documented 2026-09-17 finding: simultaneous
connection attempts from 15 workers under one client ID can transiently exceed Dhan's
documented 5-connections-per-client-ID cap). When all 15 workers independently detect
the primary silent-loss within the same ~15-second window and all attempt to
reconnect near-simultaneously, they recreate the exact same "many simultaneous
connect attempts, one client ID" condition the launch stagger was built for — just
triggered by a recovery storm instead of a cold start. This is a secondary,
self-inflicted consequence of the primary event, not independent evidence about the
primary event's own cause.

## 6. What was NOT checked, and why (honest accounting)

- **Dhan's own server-side infrastructure/session logs**: not accessible from this
  project or host at all. This is the single piece of evidence that would most
  directly resolve the question, and it is simply unavailable.
- **A second, independent, redundant Dhan connection running in parallel**: not
  attempted tonight. Standing up a second live connection is a real, low-risk
  diagnostic option for a *future* session (it would directly test "does the SAME
  client ID's second connection also drop at the same moment" vs. "does only one
  drop"), but the market is closed right now, so it cannot be tested tonight, and
  doing so during market hours is a decision for a future, explicitly-scoped session,
  not something to retrofit after the fact.
- **CPU/memory during the incident window**: no continuous performance-counter
  logging was configured for either session, so there is no historical time series to
  examine. Not measurable retroactively.
- **An NSE-documented session boundary at ~15:13-15:14 IST specifically**: none found
  in this project's own scheduler/session-timing code, and none is asserted here that
  isn't backed by a citation — NSE's regular cash-market session is 09:15-15:30 IST;
  no additional documented boundary at T-16/17 minutes is known to this project.

## 7. The confound this investigation could not resolve with only two data points

Both incidents occurred at both (a) a similar wall-clock time (~15:13-15:14 IST) and
(b) a similar elapsed time since connection (~5h56m-6h01m) and (c) a similar offset
before close (~16-17 min) — **because both sessions happened to launch at nearly the
same time of day (09:12-09:18 IST)**. With only two observations that share nearly
identical start times, these three candidate explanations (wall-clock-of-day,
session-duration, proximity-to-close) are statistically indistinguishable from each
other. A future session that launches at a meaningfully different time of day (to the
extent NSE's fixed 09:15 open allows any real variation) would be the cleanest way to
separate these hypotheses: if the gap still lands at ~15:13-15:14 IST regardless of
launch time, that points toward wall-clock-of-day or proximity-to-close; if it instead
tracks a fixed offset from THAT session's own launch time, that points toward a
connection-duration-based cause instead.

## 8. Conclusion

**Root cause remains unproven — narrowed, not solved, exactly as expected from two
data points.** What changed with tonight's investigation:

- Confirmed this is a previously-investigated, previously-mitigated phenomenon, not a
  new one — a robust, cause-agnostic recovery mechanism (the 300s idle watchdog) was
  already built after the first occurrence and is now confirmed working correctly on
  a second, independent occurrence.
- VPN reconnect is definitively ruled out for both incidents.
- A real, local-host DNS/NETLOGON anomaly is confirmed to have co-occurred with the
  2026-09-17 incident, but no equivalent local anomaly evidence exists for the
  2026-09-22 incident in the same channels, with the caveat that this asymmetry is
  suggestive, not conclusive, given the periodic (not continuous) nature of the
  specific probes checked.
- The secondary `code=805` disconnects seen during tonight's recovery window are very
  likely an already-understood side effect of the recovery storm itself, not an
  independent piece of the mystery.
- The three leading hypotheses (Dhan-side session/connection-duration policy, an
  intermediate network device dropping an idle mapping, a local network/DNS blip)
  remain genuinely open. This is disclosed as an unresolved, real, recurring
  operational question — not something to guess at further tonight, and not something
  that changes anything about the trading system, its strategy, or its risk
  configuration.

**Per the standing instruction not to chase this further without more data**: the
system's own existing recovery mechanism is proven robust across two real occurrences
and needs no code change right now. The next concrete evidence this question needs is
either a third occurrence (confirming or breaking the temporal pattern) or a
redundant parallel connection test, both decisions for a future, separately-scoped
session.
