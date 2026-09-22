from dataclasses import FrozenInstanceError

import pytest

from smi_window_tracker.lifecycle import WindowChangeGuard, WindowProposal


def proposal(**kwargs):
    return WindowProposal(
        **(
            dict(
                current_id="W1",
                current_revision=3,
                new_id="W2",
                removal_reason="preventive",
                operator="operator",
            )
            | kwargs
        )
    )


def confirm(guard, armed, **kwargs):
    return guard.consume(
        **(
            dict(
                token=armed.token,
                typed_current_id="W1",
                current_id="W1",
                current_revision=3,
                now_s=11,
            )
            | kwargs
        )
    )


def test_confirmation_is_immutable_one_use_and_does_not_change_history():
    guard = WindowChangeGuard()
    p = proposal()
    armed = guard.arm(p, now_s=10, new_id_exists=False)
    assert armed.expires_at_s == 70
    assert guard.pending(now_s=10) == armed
    with pytest.raises(FrozenInstanceError):
        armed.proposal.new_id = "W3"
    assert confirm(guard, armed) == p
    with pytest.raises(ValueError, match="No active"):
        confirm(guard, armed)


@pytest.mark.parametrize(
    "changes",
    [
        dict(token="wrong"),
        dict(typed_current_id="W2"),
        dict(current_id="W3"),
        dict(current_revision=4),
        dict(current_revision=3.0),
    ],
)
def test_bad_confirmation_clears_arm(changes):
    guard = WindowChangeGuard()
    armed = guard.arm(proposal(), now_s=10, new_id_exists=False)
    with pytest.raises(ValueError, match="mismatch"):
        confirm(guard, armed, **changes)
    assert guard.pending(now_s=12) is None


@pytest.mark.parametrize("now", [70, 71, 9])
def test_expiry_boundary_and_backwards_clock(now):
    guard = WindowChangeGuard()
    armed = guard.arm(proposal(), now_s=10, new_id_exists=False)
    with pytest.raises(ValueError, match="No active"):
        confirm(guard, armed, now_s=now)


def test_just_before_expiry():
    guard = WindowChangeGuard()
    armed = guard.arm(proposal(), now_s=10, new_id_exists=False)
    assert confirm(guard, armed, now_s=69.999) == armed.proposal


def test_cancel_restart_and_superseded_arm():
    guard = WindowChangeGuard()
    old = guard.arm(proposal(), now_s=10, new_id_exists=False)
    new = guard.arm(proposal(new_id="W3"), now_s=11, new_id_exists=False)
    assert new.token != old.token
    with pytest.raises(ValueError):
        confirm(guard, old)
    assert guard.pending(now_s=12) is None
    with pytest.raises(ValueError):
        confirm(WindowChangeGuard(), new)
    guard.arm(proposal(), now_s=20, new_id_exists=False)
    guard.cancel()
    assert guard.pending(now_s=21) is None


@pytest.mark.parametrize("exists", [True, None, 0])
def test_identity_must_be_verified_unused(exists):
    guard = WindowChangeGuard()
    guard.arm(proposal(), now_s=10, new_id_exists=False)
    with pytest.raises(ValueError, match="unused"):
        guard.arm(proposal(), now_s=11, new_id_exists=exists)
    assert guard.pending(now_s=12) is None


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout(bad):
    with pytest.raises(ValueError):
        WindowChangeGuard(timeout_s=bad)


@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_invalid_clock(bad):
    guard = WindowChangeGuard()
    with pytest.raises(ValueError):
        guard.arm(proposal(), now_s=bad, new_id_exists=False)
    guard.arm(proposal(), now_s=10, new_id_exists=False)
    with pytest.raises(ValueError):
        guard.pending(now_s=bad)
    assert guard.pending(now_s=11) is None


def test_clock_overflow():
    with pytest.raises(ValueError):
        WindowChangeGuard(timeout_s=1e308).arm(proposal(), now_s=1e308, new_id_exists=False)


@pytest.mark.parametrize(
    "changes",
    [
        dict(new_id="W1"),
        dict(new_id=""),
        dict(operator=" "),
        dict(current_id=" W1"),
        dict(new_id="x" * 129),
        dict(notes="x" * 2049),
        dict(new_id=None),
        dict(current_revision=-1),
        dict(current_revision=True),
        dict(removal_reason="typo"),
    ],
)
def test_invalid_proposals(changes):
    with pytest.raises(ValueError):
        proposal(**changes)
