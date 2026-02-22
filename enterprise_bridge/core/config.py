"""
Configuration management for Enterprise Bridge.

Loads connection profiles from a YAML/JSON config file or environment
variables.  Each profile defines the target system, credentials, and
adapter-specific options.

Default config location: ~/.enterprise-bridge/config.yaml
Override with ENTERPRISE_BRIDGE_CONFIG env var.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_DIR = Path.home() / ".enterprise-bridge"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
ENV_CONFIG_PATH = "ENTERPRISE_BRIDGE_CONFIG"
ENV_PREFIX = "EB_"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML config, falling back to JSON parsing if PyYAML is missing."""
    text = path.read_text()
    try:
        import yaml

        return yaml.safe_load(text) or {}
    except ImportError:
        return json.loads(text)


def _env_overrides() -> dict[str, str]:
    """Collect EB_* environment variables."""
    return {
        k[len(ENV_PREFIX) :]: v
        for k, v in os.environ.items()
        if k.startswith(ENV_PREFIX)
    }


class ConnectionProfile:
    """A single enterprise-system connection definition."""

    def __init__(self, name: str, raw: dict[str, Any]) -> None:
        self.name = name
        self.system: str = raw["system"]  # sap | salesforce | netsuite | oracle
        self.auth: dict[str, Any] = raw.get("auth", {})
        self.base_url: str = raw.get("base_url", "")
        self.options: dict[str, Any] = raw.get("options", {})

    def to_adapter_config(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "system": self.system,
            "auth": self.auth,
            "base_url": self.base_url,
            **self.options,
        }


class Config:
    """Top-level configuration container."""

    def __init__(self, raw: dict[str, Any] | None = None) -> None:
        self._raw = raw or {}
        self.profiles: dict[str, ConnectionProfile] = {}
        self._parse()

    def _parse(self) -> None:
        for name, defn in self._raw.get("connections", {}).items():
            self.profiles[name] = ConnectionProfile(name, defn)

    def get_profile(self, name: str) -> ConnectionProfile:
        if name not in self.profiles:
            raise KeyError(
                f"Connection profile {name!r} not found. "
                f"Available: {list(self.profiles.keys())}"
            )
        return self.profiles[name]

    def list_profiles(self) -> list[dict[str, str]]:
        return [
            {"name": p.name, "system": p.system}
            for p in self.profiles.values()
        ]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        """
        Load configuration from file, with env-var overrides applied.

        Resolution order:
        1. Explicit *path* argument
        2. ENTERPRISE_BRIDGE_CONFIG env var
        3. ~/.enterprise-bridge/config.yaml
        """
        if path is None:
            path = os.environ.get(ENV_CONFIG_PATH, str(DEFAULT_CONFIG_FILE))
        path = Path(path)

        if path.exists():
            raw = _load_yaml(path)
        else:
            raw = {}

        # Apply EB_* env-var overrides for credentials
        env = _env_overrides()
        for profile_name, profile in raw.get("connections", {}).items():
            prefix = profile_name.upper()
            auth = profile.setdefault("auth", {})
            mappings = {
                f"{prefix}_CLIENT_ID": "client_id",
                f"{prefix}_CLIENT_SECRET": "client_secret",
                f"{prefix}_USERNAME": "username",
                f"{prefix}_PASSWORD": "password",
                f"{prefix}_API_KEY": "api_key",
                f"{prefix}_TOKEN_URL": "token_url",
                f"{prefix}_BASE_URL": "base_url",
            }
            for env_key, config_key in mappings.items():
                if env_key in env:
                    if config_key == "base_url":
                        profile["base_url"] = env[env_key]
                    else:
                        auth[config_key] = env[env_key]

        return cls(raw)

    @staticmethod
    def generate_template() -> str:
        """Return a YAML template users can fill in."""
        return """\
# Enterprise Bridge configuration
# Place this file at ~/.enterprise-bridge/config.yaml
# or set ENTERPRISE_BRIDGE_CONFIG=/path/to/config.yaml
#
# Credentials can also be supplied via environment variables:
#   EB_<PROFILE_NAME>_CLIENT_ID, EB_<PROFILE_NAME>_CLIENT_SECRET, etc.

connections:
  my_salesforce:
    system: salesforce
    base_url: https://myorg.my.salesforce.com
    auth:
      type: oauth2_client_credentials
      token_url: https://login.salesforce.com/services/oauth2/token
      client_id: YOUR_CLIENT_ID
      client_secret: YOUR_CLIENT_SECRET

  my_sap:
    system: sap
    base_url: https://my-sap-instance.s4hana.cloud.sap
    auth:
      type: oauth2_client_credentials
      token_url: https://my-sap-instance.authentication.eu10.hana.ondemand.com/oauth/token
      client_id: YOUR_CLIENT_ID
      client_secret: YOUR_CLIENT_SECRET
    options:
      api_version: v2

  my_netsuite:
    system: netsuite
    base_url: https://123456.suitetalk.api.netsuite.com
    auth:
      type: oauth2_client_credentials
      token_url: https://123456.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token
      client_id: YOUR_CLIENT_ID
      client_secret: YOUR_CLIENT_SECRET
    options:
      account_id: "123456"

  my_oracle:
    system: oracle
    base_url: https://myinstance.fa.us2.oraclecloud.com
    auth:
      type: basic
      username: YOUR_USERNAME
      password: YOUR_PASSWORD
    options:
      api_version: v1
"""
