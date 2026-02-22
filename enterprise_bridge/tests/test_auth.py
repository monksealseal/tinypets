"""Tests for authentication providers."""

import pytest

from enterprise_bridge.core.auth import (
    APIKeyAuth,
    BasicAuth,
    TokenInfo,
    create_auth_provider,
)


class TestTokenInfo:
    def test_not_expired_when_zero(self):
        token = TokenInfo(access_token="abc", expires_at=0.0)
        assert not token.is_expired

    def test_expired_when_past(self):
        token = TokenInfo(access_token="abc", expires_at=1.0)
        assert token.is_expired

    def test_not_expired_when_future(self):
        import time
        token = TokenInfo(access_token="abc", expires_at=time.time() + 3600)
        assert not token.is_expired


class TestBasicAuth:
    @pytest.mark.asyncio
    async def test_acquire_token(self):
        auth = BasicAuth("user", "pass")
        token = await auth.acquire_token()
        assert token.token_type == "Basic"
        import base64
        expected = base64.b64encode(b"user:pass").decode()
        assert token.access_token == expected

    @pytest.mark.asyncio
    async def test_auth_header(self):
        auth = BasicAuth("user", "pass")
        token = await auth.get_token()
        header = auth.auth_header(token)
        assert "Authorization" in header
        assert header["Authorization"].startswith("Basic ")


class TestAPIKeyAuth:
    @pytest.mark.asyncio
    async def test_acquire_token(self):
        auth = APIKeyAuth("my-api-key")
        token = await auth.acquire_token()
        assert token.access_token == "my-api-key"

    @pytest.mark.asyncio
    async def test_custom_header(self):
        auth = APIKeyAuth("key123", header_name="X-API-Key", prefix="Token")
        token = await auth.get_token()
        header = auth.auth_header(token)
        assert header == {"X-API-Key": "Token key123"}


class TestCreateAuthProvider:
    def test_basic(self):
        provider = create_auth_provider({
            "type": "basic",
            "username": "u",
            "password": "p",
        })
        assert isinstance(provider, BasicAuth)

    def test_api_key(self):
        provider = create_auth_provider({
            "type": "api_key",
            "api_key": "k",
        })
        assert isinstance(provider, APIKeyAuth)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown auth type"):
            create_auth_provider({"type": "kerberos"})
