from datetime import datetime, timedelta

from config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


def cleanup_old_charts(days_to_keep: int = 7) -> int:
    """Remove generated chart PNGs older than `days_to_keep`. Returns count deleted."""
    if not settings.OUTPUT_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=days_to_keep)
    deleted = 0
    for chart_file in settings.OUTPUT_DIR.glob('*.png'):
        try:
            if datetime.fromtimestamp(chart_file.stat().st_mtime) < cutoff:
                chart_file.unlink()
                deleted += 1
        except OSError as e:
            logger.warning(f"Failed to delete {chart_file.name}: {e}")

    if deleted:
        logger.info(f"Cleaned up {deleted} chart file(s) older than {days_to_keep} days")
    return deleted
