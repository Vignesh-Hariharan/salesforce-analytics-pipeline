"""Shared pytest configuration.

Stubs out required environment variables before any module under test
imports `config.settings`, so tests run without a real `.env` file.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TEST_ENV = {
    'SNOWFLAKE_ACCOUNT': 'test-account',
    'SNOWFLAKE_USER': 'test-user',
    'SNOWFLAKE_PASSWORD': 'test-pass',
    'SNOWFLAKE_DATABASE': 'TEST_DB',
    'SNOWFLAKE_SCHEMA': 'TEST_SCHEMA',
    'SNOWFLAKE_WAREHOUSE': 'TEST_WH',
    'SALESFORCE_USERNAME': 'sf@example.com',
    'SALESFORCE_PASSWORD': 'sf-pass',
    'SALESFORCE_SECURITY_TOKEN': 'sf-token',
    'GEMINI_API_KEY': 'gemini-key',
    'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test',
}

for k, v in _TEST_ENV.items():
    os.environ.setdefault(k, v)
