import time
import functools
from typing import Callable, Type, Tuple
import logging

class PipelineException(Exception):
    pass

class SalesforceExtractError(PipelineException):
    pass

class SnowflakeLoadError(PipelineException):
    pass

class GeminiAPIError(PipelineException):
    pass

class AsanaAPIError(PipelineException):
    pass

class SlackAPIError(PipelineException):
    pass

def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay
            
            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise
                    
                    logger = logging.getLogger(func.__module__)
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {str(e)}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
                    attempt += 1
            
            return None
        return wrapper
    return decorator

def handle_api_error(api_name: str, error: Exception, logger: logging.Logger) -> str:
    error_msg = f"{api_name} API Error: {type(error).__name__} - {str(error)}"
    logger.error(error_msg)
    return error_msg

