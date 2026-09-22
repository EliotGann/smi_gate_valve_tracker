# Window lifecycle, restart persistence and retired-window comparisons

## Identity and reset meaning

A confirmed **new window means a new physical window**, with a unique immutable
ID. Reinstallation/resuming retired IDs is not supported in the initial workflow.
An IOC restart resumes the current window; it does not create a new window.

The new-window action atomically retires the old window and creates the next one.
Current-window opens/closes, pump cycles, timers, loading, exposure, coverage,
milestones, last-cycle summaries and early/recent references start fresh. Old
history remains queryable and immutable except for explicit audited corrections.
Configuration and material parameters are explicitly carried over or entered in
the proposal; resetting counts must not silently reuse an incorrect thickness.
Service health/uptime and optional facility totals are not window-lifetime counters.

Persist every window's installation/removal UTC, operator identifier, lot/material,
thickness/geometry when known, model epochs, aggregate metrics, quality coverage,
removal reason and notes. Unknown geometry/dose is N/A, not a numeric zero.

## Operator workflow: identity-bound arm and confirm

Confirmed design: 60-second arm followed by typing the **current** window ID and
an explicit confirm. This replaces repetitive identical “Are you sure?” dialogs
with two different deliberate actions. The server, not the screen, enforces it.

1. **Propose:** enter a never-used new window ID, removal reason, operator name
   and notes; review material parameters. The preview shows old identity/current
   totals and the proposed new identity/configuration.
2. **Arm:** server validates bounded fields and uniqueness and issues an opaque
   one-use token. Bind it to current window ID + lifecycle revision, new identity,
   reason/operator/metadata, process session and monotonic expiry. Store one pending
   arm only. A second proposal cancels/replaces the first; expose that outcome.
3. **Confirm:** within 60 seconds, type the current window ID (no automatic copy
   into the confirmation field), provide the token and click “Retire OLD and start
   NEW.” The confirmation carries no mutable replacement metadata: it uses the
   immutable armed proposal.
4. **Commit:** revalidate current ID/revision, token, expiry and database uniqueness
   inside the serialized lifecycle operation. Flush/integrate all previously
   accepted events to a defined switch boundary and commit the retirement,
   new zeroed window, current pointer/revision, audit event and result together.
5. **Acknowledge:** only after commit, publish the new ID/generation and zeroed
   current totals. The screen shows a success receipt naming both windows, not a
   temporary zero that could be mistaken for connection loss.

Cancel and expiry clear the pending proposal. Wrong token/typed identity/stale
window invalidates the arm so another deliberate arm is necessary. Arm state is
ephemeral and is never restored on service restart. Service-session change
invalidates it. The display disables/clears its confirmation state on CA loss;
do not assume CA provides reliable authenticated per-operator sessions or instant
client-disconnect notification to the server. Server expiry remains authoritative.

This token protects against accidental actions/replays; it is **not authentication**.
Operator text is an audit label unless backed by site identity infrastructure.
Apply controls' normal write-access policy to lifecycle endpoints. Two independent
authenticated operators are not part of the chosen initial workflow.

## Atomic commands and concurrency

Do not implement confirmation as a global `Confirm=1` bit paired with shared
editable staging PVs: two screens can mix those fields. Specify bounded request
messages carrying a request ID and complete proposal/confirmation payload, or
an equivalent server-owned staging revision with atomic submission. BOY scripting
for that command transport is an implementation spike, not yet deployed here.
Command and reply schemas, size limits and CA access behavior must be tested.

The lifecycle revision changes on window switches, not on every counter update,
so ongoing monitoring does not invalidate a valid arm. Only one switch can commit
from a given revision. Reusing an old confirmation must not switch again. Persist
the operation ID/result with the switch; if the success response is lost, a client
can read the result/current ID rather than resubmit a new replacement blindly.
After a commit failure the same ephemeral token is not reusable: show failure and
require a new arm after recovery. Database rollback must retain the old window.

Serialize acquisition increments and lifecycle changes through the same reducer.
An interval spanning the logical switch is split; no increment belongs to both
windows or neither without a recorded unknown interval. Interrupt an active pump
attempt at replacement, clear ephemeral qualifying state, and rebaseline for the
new window. The operator should perform the operation at the actual replacement;
retroactive changes are a separate audited correction, not normal new-window logic.

## Retired-window history and lifetime summaries

Show current and previous window side by side with cycles, loaded/pumped hours,
beam hours, upper-bound photons/interaction, and nominal Gy **only when geometry
and model inputs support that calculation**. Keep original model IDs and units.
Do not average incompatible dose models, thickness/footprint assumptions or
different calibration epochs into an apparently comparable dose lifetime.

Removal reasons: **failure**, **suspected degradation**, **preventive replacement**,
**experiment change**, **unknown**. Keep notes and a correction trail. Provide:

- Paginated table of every retired window and its final totals/coverage/reason.
- Last retired window summary next to current values.
- Count, mean, median and spread of retired-window cycles and loading/exposure
  metrics, grouped by comparable configuration/model and removal reason.
- Explicit “observed service to removal” label for all-removal summaries. A
  preventive removal is not an observed failure lifetime.
- The current window shown separately as **in service**; exclude it from completed
  service-to-removal means. For later survival analysis, non-failure removals and
  current windows are right-censored, not failures at their observed exposure.
- Per-metric usable count, exclusions and coverage. Missing dose is omitted with
  a reported missing count, never treated as zero or as a zero-exposure lifetime.

Simple grouped descriptive summaries are the initial goal, not a replacement-date
prediction. Decide minimum sample counts and model-comparability rules before
displaying a derived remaining-life indicator (not planned initially).

## Implementation boundary

The offline `WindowChangeGuard` tests an immutable proposal, one pending arm,
monotonic expiry, identity/revision checks and one-use consumption. It returns a
validated proposal to the caller. It does **not** mutate statistics or implement
the SQLite transaction, durable receipt, authentication, CA command transport or
BOY dialog. Those must be integrated and crash-tested together before deployment.
