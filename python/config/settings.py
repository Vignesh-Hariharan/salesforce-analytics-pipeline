import base64
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

# When running locally, load `.env` (plain values, no prefix). The Kestra path
# uses base64-encoded `KESTRA_SECRET_*` values from `.env.docker` and decodes
# them in the workflow scripts before invoking Python.
_local_env = REPO_ROOT / '.env'
if _local_env.exists():
    load_dotenv(dotenv_path=_local_env, override=False)

# Backwards-compatible fallback: if a developer has only the Kestra-style
# variables defined locally (KESTRA_SECRET_FOO=base64), surface them under the
# expected names so a `python main.py` invocation still works.
_KESTRA_PREFIX = 'KESTRA_SECRET_'
for key, value in list(os.environ.items()):
    if not key.startswith(_KESTRA_PREFIX):
        continue
    plain_name = key[len(_KESTRA_PREFIX):]
    if os.getenv(plain_name):
        continue
    try:
        os.environ[plain_name] = base64.b64decode(value).decode('utf-8')
    except Exception:
        # Value wasn't base64; leave it untouched and fail loudly later if
        # something requires it.
        continue


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


SNOWFLAKE_ACCOUNT   = _required('SNOWFLAKE_ACCOUNT')
SNOWFLAKE_USER      = _required('SNOWFLAKE_USER')
SNOWFLAKE_PASSWORD  = _required('SNOWFLAKE_PASSWORD')
SNOWFLAKE_DATABASE  = _required('SNOWFLAKE_DATABASE')
SNOWFLAKE_SCHEMA    = _required('SNOWFLAKE_SCHEMA')
SNOWFLAKE_WAREHOUSE = _required('SNOWFLAKE_WAREHOUSE')

SALESFORCE_USERNAME       = _required('SALESFORCE_USERNAME')
SALESFORCE_PASSWORD       = _required('SALESFORCE_PASSWORD')
SALESFORCE_SECURITY_TOKEN = _required('SALESFORCE_SECURITY_TOKEN')
SALESFORCE_DOMAIN         = os.getenv('SALESFORCE_DOMAIN', 'login')

SLACK_WEBHOOK_URL = _required('SLACK_WEBHOOK_URL')

# Optional LLM chart commentary. Absent a key (or with SKIP_AI set), the pipeline
# still extracts, loads, computes metrics, renders charts, and delivers them.
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')

ASANA_ACCESS_TOKEN = os.getenv('ASANA_ACCESS_TOKEN')
ASANA_PROJECT_GID  = os.getenv('ASANA_PROJECT_GID')

OUTPUT_DIR = REPO_ROOT / 'outputs' / 'charts'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def is_asana_configured() -> bool:
    return bool(ASANA_ACCESS_TOKEN and ASANA_PROJECT_GID)


def is_gemini_configured() -> bool:
    return bool(GEMINI_API_KEY)


def is_llm_commentary_enabled() -> bool:
    if os.getenv('SKIP_AI', '').lower() in ('1', 'true', 'yes'):
        return False
    return is_gemini_configured()
