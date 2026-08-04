from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class Identity:
    email: Optional[str] = None
    plan: Optional[str] = None
    refreshed: Optional[str] = None

    def as_dict(self) -> dict[str, Optional[str]]:
        return {
            "email": self.email,
            "plan": self.plan,
            "refreshed": self.refreshed,
        }


def decode_jwt(token: str) -> dict[str, Any]:
    """Decode a JWT payload without validating the signature."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        value = json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def parse_auth_identity(path: Path) -> Identity:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Identity()

    tokens = data.get("tokens") if isinstance(data, dict) else {}
    if not isinstance(tokens, Mapping):
        tokens = {}
    claims = decode_jwt(str(tokens.get("id_token") or ""))

    email = _find_email(claims)
    plan = _find_plan(claims)
    refreshed = _format_refresh(data.get("last_refresh") if isinstance(data, dict) else None)
    return Identity(email=email, plan=plan, refreshed=refreshed)


def _find_email(claims: Mapping[str, Any]) -> Optional[str]:
    direct = claims.get("email")
    if isinstance(direct, str) and direct:
        return direct

    for value in claims.values():
        if isinstance(value, Mapping):
            nested = value.get("email")
            if isinstance(nested, str) and nested:
                return nested
    return None


def _find_plan(claims: Mapping[str, Any]) -> Optional[str]:
    for value in claims.values():
        if isinstance(value, Mapping):
            plan = value.get("chatgpt_plan_type") or value.get("plan_type")
            if isinstance(plan, str) and plan:
                return plan
    return None


def _format_refresh(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    return value[:19].replace("T", " ")
