"""Ephemeral new-window confirmation guard, independent of CA and storage.

Consumption authorizes a caller's atomic transaction; it does not reset counters.
Use from one serialized reducer. Database uniqueness and revision checks must be
repeated in the actual transaction. See docs/WINDOW_LIFECYCLE.md.
"""

from dataclasses import dataclass
from math import isfinite
from secrets import token_urlsafe

REMOVAL_REASONS = frozenset(
    {"failure", "suspected_degradation", "preventive", "experiment_change", "unknown"}
)


def _text(value: str, name: str, limit: int, *, empty: bool = False):
    if not isinstance(value, str) or len(value.encode("utf-8")) > limit:
        raise ValueError(f"{name} must be text within {limit} UTF-8 bytes")
    if value != value.strip() or (not empty and not value):
        raise ValueError(f"{name} must be nonblank and have no surrounding whitespace")


@dataclass(frozen=True)
class WindowProposal:
    current_id: str
    current_revision: int
    new_id: str
    removal_reason: str
    operator: str
    notes: str = ""

    def __post_init__(self):
        _text(self.current_id, "current_id", 128)
        _text(self.new_id, "new_id", 128)
        _text(self.operator, "operator", 128)
        _text(self.notes, "notes", 2048, empty=True)
        if self.current_id == self.new_id:
            raise ValueError("New window must have a new physical identity")
        if type(self.current_revision) is not int or self.current_revision < 0:
            raise ValueError("current_revision must be a nonnegative integer")
        if self.removal_reason not in REMOVAL_REASONS:
            raise ValueError("Unknown removal reason")


@dataclass(frozen=True)
class ArmedChange:
    proposal: WindowProposal
    token: str
    armed_at_s: float
    expires_at_s: float


class WindowChangeGuard:
    """One pending immutable proposal with monotonic expiry and one-use token.

    Create a fresh guard on service restart; never serialize pending state.
    ``new_id_exists`` is a caller's database check, repeated at commit time.
    """

    def __init__(self, *, timeout_s: float = 60.0):
        if not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        self.timeout_s = timeout_s
        self._pending: ArmedChange | None = None

    def cancel(self):
        self._pending = None

    def pending(self, *, now_s: float) -> ArmedChange | None:
        if not isfinite(now_s):
            self.cancel()
            raise ValueError("now_s must be finite")
        if self._pending is not None and not (
            self._pending.armed_at_s <= now_s < self._pending.expires_at_s
        ):
            self.cancel()
        return self._pending

    def arm(self, proposal: WindowProposal, *, now_s: float, new_id_exists: bool) -> ArmedChange:
        self.cancel()
        if type(new_id_exists) is not bool or new_id_exists:
            raise ValueError("New physical window ID must be verified unused")
        if not isfinite(now_s) or not isfinite(now_s + self.timeout_s):
            raise ValueError("Arm times must be finite")
        armed = ArmedChange(proposal, token_urlsafe(24), now_s, now_s + self.timeout_s)
        self._pending = armed
        return armed

    def consume(
        self,
        *,
        token: str,
        typed_current_id: str,
        current_id: str,
        current_revision: int,
        now_s: float,
    ) -> WindowProposal:
        armed = self.pending(now_s=now_s)
        self.cancel()  # Any confirm attempt consumes/invalidates the pending arm.
        if armed is None:
            raise ValueError("No active arm; rearm before confirming")
        proposal = armed.proposal
        if (
            token != armed.token
            or typed_current_id != proposal.current_id
            or current_id != proposal.current_id
            or type(current_revision) is not int
            or current_revision != proposal.current_revision
        ):
            raise ValueError("Confirmation identity/token/revision mismatch; rearm required")
        return proposal
