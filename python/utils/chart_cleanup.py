from pathlib import Path
from datetime import datetime, timedelta
from utils.logger import setup_logger

logger = setup_logger(__name__)

def cleanup_old_charts(days_to_keep: int = 7):
    """Remove chart files older than specified days"""
    charts_dir = Path(__file__).parent.parent.parent / 'outputs' / 'charts'
    if not charts_dir.exists():
        return
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    deleted_count = 0
    
    for chart_file in charts_dir.glob('*.png'):
        try:
            file_time = datetime.fromtimestamp(chart_file.stat().st_mtime)
            if file_time < cutoff_date:
                chart_file.unlink()
                deleted_count += 1
        except Exception as e:
            logger.warning(f"Failed to delete {chart_file.name}: {e}")
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old chart files")

