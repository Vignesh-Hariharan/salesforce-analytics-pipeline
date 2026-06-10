import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

def get_required_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise ValueError(f"Missing required environment variable: {var_name}")
    return value

SNOWFLAKE_ACCOUNT = get_required_env('SNOWFLAKE_ACCOUNT')
SNOWFLAKE_USER = get_required_env('SNOWFLAKE_USER')
SNOWFLAKE_PASSWORD = get_required_env('SNOWFLAKE_PASSWORD')
SNOWFLAKE_DATABASE = get_required_env('SNOWFLAKE_DATABASE')
SNOWFLAKE_SCHEMA = get_required_env('SNOWFLAKE_SCHEMA')
SNOWFLAKE_WAREHOUSE = get_required_env('SNOWFLAKE_WAREHOUSE')

SALESFORCE_USERNAME = get_required_env('SALESFORCE_USERNAME')
SALESFORCE_PASSWORD = get_required_env('SALESFORCE_PASSWORD')
SALESFORCE_SECURITY_TOKEN = get_required_env('SALESFORCE_SECURITY_TOKEN')
SALESFORCE_DOMAIN = os.getenv('SALESFORCE_DOMAIN', 'login')

GEMINI_API_KEY = get_required_env('GEMINI_API_KEY')

SLACK_WEBHOOK_URL = get_required_env('SLACK_WEBHOOK_URL')

ASANA_ACCESS_TOKEN = os.getenv('ASANA_ACCESS_TOKEN')
ASANA_PROJECT_GID = os.getenv('ASANA_PROJECT_GID')

IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID', '546c25a59c58ad7')

def is_asana_configured() -> bool:
    return bool(ASANA_ACCESS_TOKEN and ASANA_PROJECT_GID)

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'outputs' / 'charts'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

