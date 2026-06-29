from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Request
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, Response


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _normalise_team_domain(value: str) -> str:
    return value.strip().rstrip("/")


@lru_cache(maxsize=1)
def _get_jwks_client() -> PyJWKClient:
    team_domain = _normalise_team_domain(
        os.environ.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN", "")
    )

    if not team_domain:
        raise RuntimeError("CLOUDFLARE_ACCESS_TEAM_DOMAIN is not set.")

    return PyJWKClient(f"{team_domain}/cdn-cgi/access/certs")


def _verify_cloudflare_access_token(token: str) -> dict[str, Any]:
    team_domain = _normalise_team_domain(
        os.environ.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN", "")
    )
    audience = os.environ.get("CLOUDFLARE_ACCESS_AUD", "").strip()

    if not team_domain:
        raise RuntimeError("CLOUDFLARE_ACCESS_TEAM_DOMAIN is not set.")

    if not audience:
        raise RuntimeError("CLOUDFLARE_ACCESS_AUD is not set.")

    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)

    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=team_domain,
    )


class CloudflareAccessMiddleware(BaseHTTPMiddleware):
    """
    Require a valid Cloudflare Access JWT when CLOUDFLARE_ACCESS_REQUIRED=true.

    Cloudflare Access forwards the JWT to the origin in the
    cf-access-jwt-assertion header. Browser requests may also carry the
    CF_Authorization cookie.

    When enabled, this protects every route, including /health and static files,
    so the raw Cloud Run run.app URL cannot be used as a public bypass.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if not _env_truthy("CLOUDFLARE_ACCESS_REQUIRED"):
            return await call_next(request)

        token = (
            request.headers.get("cf-access-jwt-assertion")
            or request.cookies.get("CF_Authorization")
            or ""
        ).strip()

        if not token:
            return PlainTextResponse(
                "Forbidden: missing Cloudflare Access token.",
                status_code=403,
            )

        try:
            _verify_cloudflare_access_token(token)
        except Exception:
            return PlainTextResponse(
                "Forbidden: invalid Cloudflare Access token.",
                status_code=403,
            )

        return await call_next(request)
