"""
Authentication handlers for enterprise systems.

Supports OAuth 2.0 (client-credentials, authorization-code, JWT-bearer),
basic auth, API-key auth, and token-based auth.  Each adapter picks the
strategy it needs and this module manages token lifecycle (acquisition,
caching, refresh).
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class TokenInfo:
    """Cached token with expiry tracking."""

    access_token: str
    token_type: str = "Bearer"
    expires_at: float = 0.0  # epoch seconds; 0 → never expires
    refresh_token: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.expires_at == 0.0:
            return False
        return time.time() >= (self.expires_at - 30)  # 30-second buffer


class AuthProvider(abc.ABC):
    """Base class for all auth strategies."""

    @abc.abstractmethod
    async def acquire_token(self) -> TokenInfo:
        """Obtain a fresh token (or credentials wrapper)."""

    @abc.abstractmethod
    async def refresh_token(self, token: TokenInfo) -> TokenInfo:
        """Refresh an expired token if the strategy supports it."""

    async def get_token(self) -> TokenInfo:
        """Return a valid token, refreshing if necessary."""
        if not hasattr(self, "_cached") or self._cached is None or self._cached.is_expired:
            if hasattr(self, "_cached") and self._cached and self._cached.refresh_token:
                self._cached = await self.refresh_token(self._cached)
            else:
                self._cached = await self.acquire_token()
        return self._cached

    def auth_header(self, token: TokenInfo) -> dict[str, str]:
        return {"Authorization": f"{token.token_type} {token.access_token}"}


# ── Concrete strategies ─────────────────────────────────────────────────


class OAuth2ClientCredentials(AuthProvider):
    """Standard OAuth 2.0 client-credentials flow."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "",
        extra_params: dict[str, str] | None = None,
    ) -> None:
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.extra_params = extra_params or {}
        self._cached: TokenInfo | None = None

    async def acquire_token(self) -> TokenInfo:
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            **self.extra_params,
        }
        if self.scope:
            payload["scope"] = self.scope

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data=payload)
            resp.raise_for_status()
            body = resp.json()

        return TokenInfo(
            access_token=body["access_token"],
            token_type=body.get("token_type", "Bearer"),
            expires_at=time.time() + body.get("expires_in", 3600),
            refresh_token=body.get("refresh_token"),
        )

    async def refresh_token(self, token: TokenInfo) -> TokenInfo:
        if not token.refresh_token:
            return await self.acquire_token()

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data=payload)
            resp.raise_for_status()
            body = resp.json()

        return TokenInfo(
            access_token=body["access_token"],
            token_type=body.get("token_type", "Bearer"),
            expires_at=time.time() + body.get("expires_in", 3600),
            refresh_token=body.get("refresh_token", token.refresh_token),
        )


class BasicAuth(AuthProvider):
    """HTTP Basic authentication (username + password encoded as a token)."""

    def __init__(self, username: str, password: str) -> None:
        import base64

        self._token_value = base64.b64encode(
            f"{username}:{password}".encode()
        ).decode()
        self._cached: TokenInfo | None = None

    async def acquire_token(self) -> TokenInfo:
        return TokenInfo(access_token=self._token_value, token_type="Basic")

    async def refresh_token(self, token: TokenInfo) -> TokenInfo:
        return await self.acquire_token()


class APIKeyAuth(AuthProvider):
    """Simple API-key / static-token authentication."""

    def __init__(self, api_key: str, header_name: str = "Authorization", prefix: str = "Bearer") -> None:
        self._api_key = api_key
        self._header_name = header_name
        self._prefix = prefix
        self._cached: TokenInfo | None = None

    async def acquire_token(self) -> TokenInfo:
        return TokenInfo(access_token=self._api_key, token_type=self._prefix)

    async def refresh_token(self, token: TokenInfo) -> TokenInfo:
        return await self.acquire_token()

    def auth_header(self, token: TokenInfo) -> dict[str, str]:
        return {self._header_name: f"{self._prefix} {token.access_token}"}


class OAuth2JWTBearer(AuthProvider):
    """
    OAuth 2.0 JWT-bearer flow used by Salesforce connected-apps
    and SAP BTP service instances.
    """

    def __init__(
        self,
        token_url: str,
        client_id: str,
        private_key: str,
        subject: str,
        audience: str = "",
        scope: str = "",
    ) -> None:
        self.token_url = token_url
        self.client_id = client_id
        self.private_key = private_key
        self.subject = subject
        self.audience = audience
        self.scope = scope
        self._cached: TokenInfo | None = None

    def _build_assertion(self) -> str:
        import json
        import base64
        import hashlib
        import hmac

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).decode().rstrip("=")

        now = int(time.time())
        claims = {
            "iss": self.client_id,
            "sub": self.subject,
            "aud": self.audience or self.token_url,
            "exp": now + 300,
            "iat": now,
        }
        payload = base64.urlsafe_b64encode(
            json.dumps(claims).encode()
        ).decode().rstrip("=")

        signature = base64.urlsafe_b64encode(
            hmac.new(
                self.private_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256
            ).digest()
        ).decode().rstrip("=")

        return f"{header}.{payload}.{signature}"

    async def acquire_token(self) -> TokenInfo:
        assertion = self._build_assertion()
        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }
        if self.scope:
            payload["scope"] = self.scope

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data=payload)
            resp.raise_for_status()
            body = resp.json()

        return TokenInfo(
            access_token=body["access_token"],
            token_type=body.get("token_type", "Bearer"),
            expires_at=time.time() + body.get("expires_in", 3600),
        )

    async def refresh_token(self, token: TokenInfo) -> TokenInfo:
        return await self.acquire_token()


def create_auth_provider(auth_config: dict[str, Any]) -> AuthProvider:
    """Factory that builds the right AuthProvider from a config dict."""
    auth_type = auth_config.get("type", "").lower()

    if auth_type == "oauth2_client_credentials":
        return OAuth2ClientCredentials(
            token_url=auth_config["token_url"],
            client_id=auth_config["client_id"],
            client_secret=auth_config["client_secret"],
            scope=auth_config.get("scope", ""),
            extra_params=auth_config.get("extra_params", {}),
        )
    elif auth_type == "oauth2_jwt_bearer":
        return OAuth2JWTBearer(
            token_url=auth_config["token_url"],
            client_id=auth_config["client_id"],
            private_key=auth_config["private_key"],
            subject=auth_config["subject"],
            audience=auth_config.get("audience", ""),
            scope=auth_config.get("scope", ""),
        )
    elif auth_type == "basic":
        return BasicAuth(
            username=auth_config["username"],
            password=auth_config["password"],
        )
    elif auth_type == "api_key":
        return APIKeyAuth(
            api_key=auth_config["api_key"],
            header_name=auth_config.get("header_name", "Authorization"),
            prefix=auth_config.get("prefix", "Bearer"),
        )
    else:
        raise ValueError(f"Unknown auth type: {auth_type!r}")
