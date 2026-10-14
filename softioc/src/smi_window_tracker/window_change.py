"""Atomic request protocol for local tracker history maintenance (not hardware).

No shared editable staging PVs. Each arm carries its full immutable proposal;
confirm carries its request ID, one-use token and typed old identity.
"""

import json
from dataclasses import asdict
from datetime import UTC, datetime

from .lifecycle import WindowChangeGuard, WindowProposal


class WindowRequests:
    def __init__(self):
        self.guard = WindowChangeGuard()
        self.request_id = None
        self.installed_utc = None

    def handle(self, message, store, *, mono, utc):
        if len(message.encode()) > 4096:
            self.guard.cancel()
            raise ValueError("Request too large")
        try:
            request = json.loads(message)
            operation = request["op"]
            if operation == "cancel":
                pending = self.guard.pending(now_s=mono)
                if pending is None or request.get("token") != pending.token:
                    raise ValueError("No matching arm to cancel")
                self.guard.cancel()
                return {"status": "cancelled"}, None
            if operation == "arm":
                self.guard.cancel()
                request_id = request["request_id"]
                if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                    raise ValueError("Invalid request ID")
                if request.get("session") != store.session:
                    raise ValueError("Service restarted; reopen the change screen")
                proposal = WindowProposal(
                    current_id=request["current_id"],
                    current_revision=store.revision,
                    new_id=request["new_id"],
                    removal_reason=request["reason"],
                    operator=request["operator"],
                    notes=request.get("notes", ""),
                )
                if proposal.current_id != store.window:
                    raise ValueError("Current ID changed; reopen the change screen")
                installed = datetime.fromisoformat(request["installed_utc"].replace("Z", "+00:00"))
                if installed.tzinfo is None:
                    raise ValueError("Installation date must include UTC/timezone")
                stamp = installed.astimezone(UTC).timestamp()
                if not 0 < stamp <= utc:
                    raise ValueError("Installation date must be in the past or now")
                if store.installed_utc is not None and stamp < store.installed_utc:
                    raise ValueError("New installation cannot predate current installation")
                arm = self.guard.arm(
                    proposal, now_s=mono, new_id_exists=store.window_exists(proposal.new_id)
                )
                self.request_id, self.installed_utc = request_id, stamp
                return {
                    "status": "armed",
                    "request_id": request_id,
                    "token": arm.token,
                    "proposal": asdict(proposal),
                    "installed_utc": stamp,
                    "expires_in_s": 60,
                }, None
            if operation == "confirm":
                if (
                    request.get("request_id") != self.request_id
                    or request.get("session") != store.session
                ):
                    raise ValueError("Request/session mismatch; rearm")
                proposal = self.guard.consume(
                    token=request["token"],
                    typed_current_id=request["typed_current_id"],
                    current_id=store.window,
                    current_revision=store.revision,
                    now_s=mono,
                )
                return {"status": "committing", "request_id": self.request_id}, (
                    proposal,
                    self.request_id,
                    self.installed_utc,
                )
            raise ValueError("Unknown operation")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            self.guard.cancel()
            raise ValueError(str(exc)) from exc
