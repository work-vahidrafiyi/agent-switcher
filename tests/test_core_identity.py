import base64
import json

from agent_switcher.core.identity import decode_jwt, parse_auth_identity


def make_jwt(payload):
    def encode(value):
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{encode({'alg': 'none'})}.{encode(payload)}."


def write_auth(path, email="user@example.com", plan="plus", refresh="2026-08-04T11:22:33.000Z"):
    token = make_jwt(
        {
            "email": email,
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": plan,
            },
        }
    )
    path.write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": token,
                    "refresh_token": f"refresh-{email}",
                },
                "last_refresh": refresh,
            }
        ),
        encoding="utf-8",
    )


def test_parse_auth_identity_from_synthetic_jwt(tmp_path):
    path = tmp_path / "auth.json"
    write_auth(path, email="work@example.com", plan="team")

    identity = parse_auth_identity(path)

    assert identity.email == "work@example.com"
    assert identity.plan == "team"
    assert identity.refreshed == "2026-08-04 11:22:33"


def test_decode_jwt_returns_empty_dict_for_bad_token():
    assert decode_jwt("not-a-jwt") == {}
