import os
import subprocess
from config import settings
from utils.error_handler import SnowflakeLoadError
from utils.logger import setup_logger

logger = setup_logger(__name__)

DBT_DIR = settings.REPO_ROOT / 'dbt'


def run_dbt_build() -> None:
    """Run dbt deps + build (models and seeds, excluding warehouse tests).

    Requires Snowflake credentials in the environment. Called after the Python
    loader lands raw_* tables and before workflows read the marts.
    """
    if not DBT_DIR.is_dir():
        raise SnowflakeLoadError(f"dbt project not found at {DBT_DIR}")

    env = os.environ.copy()
    profiles_dir = str(DBT_DIR)

    for label, args in (
        ("dbt deps", ["dbt", "deps", "--profiles-dir", profiles_dir]),
        ("dbt build", [
            "dbt", "build",
            "--profiles-dir", profiles_dir,
            "--exclude", "resource_type:test",
        ]),
    ):
        logger.info(f"Running {label}")
        try:
            subprocess.run(
                args,
                cwd=DBT_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"{label} failed: {e.stderr or e.stdout}")
            raise SnowflakeLoadError(f"{label} failed: {e.stderr or e.stdout}") from e

    logger.info("dbt build completed")
