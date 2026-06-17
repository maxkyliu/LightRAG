"""
Identity, team onboarding, and roles (task group 3).

Maps Telegram accounts to teams (DM-only: one team per account) and resolves the
LightRAG workspace for each request. Enforces the owner/member role split
(design: owner manages/destroys, member ingests+queries).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .config import GatewayConfig
from .db import MEMBER, OWNER, Datastore, Invite, Membership


class OnboardingError(Exception):
    """User-facing onboarding failure (message is safe to show)."""


@dataclass
class ResolvedIdentity:
    membership: Membership
    workspace: str

    @property
    def is_owner(self) -> bool:
        return self.membership.role == OWNER


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expired(expires_at: Optional[str]) -> bool:
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) < _now()
    except ValueError:
        return False


def generate_team_id() -> str:
    return secrets.token_hex(4)  # 8 hex chars


def generate_invite_code() -> str:
    # Human-friendly, unambiguous uppercase code, e.g. "K7QF9X2M".
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


class IdentityService:
    def __init__(self, db: Datastore, config: GatewayConfig):
        self._db = db
        self._config = config

    # ---------------------------- resolution -------------------------------- #

    def resolve(self, tg_user_id: int) -> Optional[ResolvedIdentity]:
        membership = self._db.get_membership(tg_user_id)
        if not membership:
            return None
        workspace = self._config.workspace_for_team(membership.team_id)
        return ResolvedIdentity(membership=membership, workspace=workspace)

    # ---------------------------- onboarding -------------------------------- #

    def create_team(self, tg_user_id: int, name: str) -> tuple[str, str]:
        """Create a team owned by the caller. Returns (team_id, invite_code)."""
        if self._db.get_membership(tg_user_id):
            raise OnboardingError(
                "You already belong to a team. Use /leave first to create a new one."
            )
        name = (name or "").strip() or "Untitled Team"
        team_id = generate_team_id()
        self._db.create_team(team_id, name, tg_user_id)
        self._db.add_membership(tg_user_id, team_id, OWNER)
        invite = self._new_invite_for_team(team_id)
        return team_id, invite.code

    def join_team(self, tg_user_id: int, code: str) -> Membership:
        if self._db.get_membership(tg_user_id):
            raise OnboardingError(
                "You already belong to a team. Use /leave first to switch teams."
            )
        code = (code or "").strip().upper()
        if not code:
            raise OnboardingError("Usage: /join <invite-code>")
        invite = self._db.get_invite(code)
        if not invite or _expired(invite.expires_at):
            raise OnboardingError("That invite code is invalid or has expired.")
        if not self._db.get_team(invite.team_id):
            raise OnboardingError("That team no longer exists.")
        return self._db.add_membership(tg_user_id, invite.team_id, MEMBER)

    def new_invite(self, tg_user_id: int) -> str:
        """Owner-only: rotate the team's invite code (revokes old codes)."""
        identity = self.resolve(tg_user_id)
        if not identity:
            raise OnboardingError(
                "You are not in a team yet. Use /createteam or /join."
            )
        if not identity.is_owner:
            raise OnboardingError("Only the team owner can manage invite codes.")
        # Rotate: drop existing codes, mint a fresh one (design D7).
        self._db.delete_invites_for_team(identity.membership.team_id)
        invite = self._new_invite_for_team(identity.membership.team_id)
        return invite.code

    def leave_team(self, tg_user_id: int) -> None:
        identity = self.resolve(tg_user_id)
        if not identity:
            raise OnboardingError("You are not in a team.")
        if identity.is_owner:
            # Owner leaving tears the team down (v1: owner == team lifecycle).
            self._db.delete_team(identity.membership.team_id)
        else:
            self._db.remove_membership(tg_user_id)

    def require_identity(self, tg_user_id: int) -> ResolvedIdentity:
        identity = self.resolve(tg_user_id)
        if not identity:
            raise OnboardingError(
                "You are not in a team yet. Use /createteam <name> to start one, "
                "or /join <code> to join an existing team."
            )
        return identity

    def require_owner(self, tg_user_id: int) -> ResolvedIdentity:
        identity = self.require_identity(tg_user_id)
        if not identity.is_owner:
            raise OnboardingError("Only the team owner can do that.")
        return identity

    # ------------------------------ helpers --------------------------------- #

    def _new_invite_for_team(self, team_id: str) -> Invite:
        code = generate_invite_code()
        return self._db.create_invite(code, team_id, expires_at=None)
