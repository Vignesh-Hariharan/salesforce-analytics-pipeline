import importlib
import sys


def test_settings_decode_kestra_secret_fallback(monkeypatch):
    """Local dev that only has KESTRA_SECRET_FOO=base64 in their env should
    still produce a usable plain `FOO` value after settings.py loads."""
    import base64

    monkeypatch.setenv(
        "KESTRA_SECRET_SNOWFLAKE_ACCOUNT",
        base64.b64encode(b"DECODED-ACCOUNT").decode(),
    )
    monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)

    sys.modules.pop("config.settings", None)
    settings = importlib.import_module("config.settings")
    assert settings.SNOWFLAKE_ACCOUNT == "DECODED-ACCOUNT"


def test_settings_prefers_explicit_plain_value(monkeypatch):
    """When both `FOO` and `KESTRA_SECRET_FOO` exist, the plain value wins."""
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "explicit")
    monkeypatch.setenv("KESTRA_SECRET_SNOWFLAKE_ACCOUNT", "ZGVjb2RlZA==")  # 'decoded'

    sys.modules.pop("config.settings", None)
    settings = importlib.import_module("config.settings")
    assert settings.SNOWFLAKE_ACCOUNT == "explicit"
