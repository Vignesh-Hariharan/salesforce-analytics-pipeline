import logging
import sys
from typing import Optional

def setup_logger(name: str, log_level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, log_level.upper()))
        
        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

def log_metric(logger: logging.Logger, metric_name: str, value: any, context: Optional[str] = None):
    msg = f"METRIC | {metric_name}: {value}"
    if context:
        msg += f" | {context}"
    logger.info(msg)

def log_api_call(logger: logging.Logger, api_name: str, status: str, duration_ms: float, details: Optional[str] = None):
    msg = f"API_CALL | {api_name} | {status} | {duration_ms:.2f}ms"
    if details:
        msg += f" | {details}"
    logger.info(msg)

