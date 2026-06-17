"""Team onboarding, roles, and workspace isolation (task 7.1)."""

import pytest

from telegram_gateway.config import GatewayConfig
from telegram_gateway.db import MEMBER, OWNER, Datastore
from telegram_gateway.identity import IdentityService, OnboardingError


@pytest.fixture
def svc():
    db = Datastore(":memory:")
    config = GatewayConfig(workspace_prefix="team_")
    return IdentityService(db, config)


def test_create_team_makes_owner(svc):
    team_id, code = svc.create_team(1, "Acme")
    identity = svc.resolve(1)
    assert identity is not None
    assert identity.membership.role == OWNER
    assert identity.is_owner is True
    assert identity.workspace == f"team_{team_id}"
    assert code  # an invite code was issued


def test_cannot_create_second_team(svc):
    svc.create_team(1, "Acme")
    with pytest.raises(OnboardingError):
        svc.create_team(1, "Other")


def test_join_with_valid_code(svc):
    _team_id, code = svc.create_team(1, "Acme")
    membership = svc.join_team(2, code)
    assert membership.role == MEMBER
    identity = svc.resolve(2)
    assert identity.membership.team_id == svc.resolve(1).membership.team_id


def test_join_with_invalid_code(svc):
    svc.create_team(1, "Acme")
    with pytest.raises(OnboardingError):
        svc.join_team(2, "BOGUSCOD")


def test_member_cannot_rotate_invite(svc):
    _team_id, code = svc.create_team(1, "Acme")
    svc.join_team(2, code)
    with pytest.raises(OnboardingError):
        svc.new_invite(2)  # member, not owner


def test_owner_rotate_revokes_old_code(svc):
    _team_id, old_code = svc.create_team(1, "Acme")
    new_code = svc.new_invite(1)
    assert new_code != old_code
    # Old code no longer works.
    with pytest.raises(OnboardingError):
        svc.join_team(3, old_code)
    # New code works.
    assert svc.join_team(3, new_code).role == MEMBER


def test_two_teams_have_isolated_workspaces(svc):
    a_id, _ = svc.create_team(1, "Acme")
    b_id, _ = svc.create_team(2, "Globex")
    assert svc.resolve(1).workspace == f"team_{a_id}"
    assert svc.resolve(2).workspace == f"team_{b_id}"
    assert svc.resolve(1).workspace != svc.resolve(2).workspace


def test_owner_leaving_deletes_team(svc):
    _team_id, code = svc.create_team(1, "Acme")
    svc.join_team(2, code)
    svc.leave_team(1)  # owner leaves -> team torn down
    assert svc.resolve(1) is None
    # The member's membership is gone too (team deleted).
    assert svc.resolve(2) is None


def test_require_owner_and_identity(svc):
    with pytest.raises(OnboardingError):
        svc.require_identity(99)
    svc.create_team(1, "Acme")
    assert svc.require_owner(1).is_owner
