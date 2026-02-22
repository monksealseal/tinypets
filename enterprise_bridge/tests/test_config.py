"""Tests for configuration loading and profile management."""

import json
import tempfile
from pathlib import Path

import pytest

from enterprise_bridge.core.config import Config, ConnectionProfile


@pytest.fixture
def sample_config_dict():
    return {
        "connections": {
            "test_sf": {
                "system": "salesforce",
                "base_url": "https://test.salesforce.com",
                "auth": {
                    "type": "oauth2_client_credentials",
                    "token_url": "https://login.salesforce.com/services/oauth2/token",
                    "client_id": "test_id",
                    "client_secret": "test_secret",
                },
            },
            "test_sap": {
                "system": "sap",
                "base_url": "https://test.s4hana.cloud.sap",
                "auth": {
                    "type": "basic",
                    "username": "admin",
                    "password": "pass123",
                },
                "options": {"api_version": "v4"},
            },
            "test_ns": {
                "system": "netsuite",
                "base_url": "https://123456.suitetalk.api.netsuite.com",
                "auth": {
                    "type": "api_key",
                    "api_key": "ns_key_123",
                },
                "options": {"account_id": "123456"},
            },
            "test_oracle": {
                "system": "oracle",
                "base_url": "https://test.fa.us2.oraclecloud.com",
                "auth": {
                    "type": "basic",
                    "username": "oracle_user",
                    "password": "oracle_pass",
                },
            },
        }
    }


@pytest.fixture
def sample_config(sample_config_dict):
    return Config(sample_config_dict)


class TestConfig:
    def test_load_from_dict(self, sample_config):
        assert len(sample_config.profiles) == 4

    def test_list_profiles(self, sample_config):
        profiles = sample_config.list_profiles()
        names = [p["name"] for p in profiles]
        assert "test_sf" in names
        assert "test_sap" in names
        assert "test_ns" in names
        assert "test_oracle" in names

    def test_get_profile(self, sample_config):
        profile = sample_config.get_profile("test_sf")
        assert profile.system == "salesforce"
        assert profile.base_url == "https://test.salesforce.com"

    def test_get_missing_profile_raises(self, sample_config):
        with pytest.raises(KeyError, match="nonexistent"):
            sample_config.get_profile("nonexistent")

    def test_profile_to_adapter_config(self, sample_config):
        profile = sample_config.get_profile("test_sap")
        adapter_cfg = profile.to_adapter_config()
        assert adapter_cfg["system"] == "sap"
        assert adapter_cfg["api_version"] == "v4"
        assert adapter_cfg["auth"]["type"] == "basic"

    def test_load_from_json_file(self, sample_config_dict):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(sample_config_dict, f)
            f.flush()
            config = Config.load(f.name)

        assert len(config.profiles) == 4

    def test_load_missing_file_returns_empty(self, tmp_path):
        config = Config.load(tmp_path / "nonexistent.yaml")
        assert len(config.profiles) == 0

    def test_generate_template(self):
        template = Config.generate_template()
        assert "connections:" in template
        assert "salesforce" in template
        assert "sap" in template
        assert "netsuite" in template
        assert "oracle" in template

    def test_env_override(self, sample_config_dict, monkeypatch):
        monkeypatch.setenv("EB_TEST_SF_CLIENT_ID", "env_client_id")
        monkeypatch.setenv("EB_TEST_SF_CLIENT_SECRET", "env_secret")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(sample_config_dict, f)
            f.flush()
            config = Config.load(f.name)

        profile = config.get_profile("test_sf")
        assert profile.auth["client_id"] == "env_client_id"
        assert profile.auth["client_secret"] == "env_secret"


class TestConnectionProfile:
    def test_creation(self):
        raw = {
            "system": "salesforce",
            "base_url": "https://example.com",
            "auth": {"type": "basic", "username": "u", "password": "p"},
            "options": {"api_version": "v58.0"},
        }
        profile = ConnectionProfile("test", raw)
        assert profile.name == "test"
        assert profile.system == "salesforce"
        assert profile.options == {"api_version": "v58.0"}
