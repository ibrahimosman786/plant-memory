"""Token issuance and verification.

- Dev backend: HS256 tokens issued by POST /v1/auth/dev-login (local only).
- Cognito backend: RS256 tokens verified against the user pool JWKS.
- Agent tokens: short-lived HS256 tokens the API mints for one run; eve verifies them with
  verifyJwtHmac and the attributes become the session auth context that tools read.
"""

from __future__ import annotations

import time
import uuid
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from ..config import get_settings


def issue_dev_token(user_id: uuid.UUID, email: str, ttl_seconds: int = 8 * 3600) -> str:
    s = get_settings()
    now = int(time.time())
    return jwt.encode(
        {"sub": str(user_id), "email": email, "iat": now, "exp": now + ttl_seconds, "iss": "plant-memory-dev", "aud": "plant-memory"},
        s.auth_dev_secret,
        algorithm="HS256",
    )


def verify_user_token(token: str) -> dict:
    s = get_settings()
    if s.auth_backend == "dev":
        return jwt.decode(token, s.auth_dev_secret, algorithms=["HS256"], audience="plant-memory", issuer="plant-memory-dev")
    if s.auth_backend == "cognito":
        if not (s.cognito_user_pool_id and s.cognito_region):
            raise RuntimeError("Cognito auth selected but COGNITO_USER_POOL_ID / COGNITO_REGION missing")
        issuer = f"https://cognito-idp.{s.cognito_region}.amazonaws.com/{s.cognito_user_pool_id}"
        signing_key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], issuer=issuer, options={"verify_aud": False})
        if s.cognito_client_id and claims.get("client_id", claims.get("aud")) != s.cognito_client_id:
            raise jwt.InvalidTokenError("client_id mismatch")
        return claims
    raise RuntimeError(f"unknown AUTH_BACKEND {s.auth_backend}")


@lru_cache
def _jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer}/.well-known/jwks.json")


def issue_agent_token(*, run_id: uuid.UUID, org_id: uuid.UUID, project_id: uuid.UUID, snapshot_id: uuid.UUID, user_id: uuid.UUID, ttl_seconds: int) -> str:
    """Token the API sends to eve when creating a session. eve verifies it and exposes the
    claims to tools as ctx.session.auth.current. Tools send it back on every API call."""
    s = get_settings()
    now = int(time.time())
    return jwt.encode(
        {
            "iss": s.agent_jwt_issuer,
            "aud": s.agent_jwt_audience,
            "sub": f"run:{run_id}",
            "iat": now,
            "exp": now + ttl_seconds,
            "run_id": str(run_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "snapshot_id": str(snapshot_id),
            "user_id": str(user_id),
            "principal_type": "service",
        },
        s.agent_jwt_secret,
        algorithm="HS256",
    )


def verify_agent_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.agent_jwt_secret, algorithms=["HS256"], audience=s.agent_jwt_audience, issuer=s.agent_jwt_issuer)
