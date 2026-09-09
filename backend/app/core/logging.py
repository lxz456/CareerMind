"""Small, dependency-free logging setup for the single-process demo."""

import logging
from contextvars import ContextVar, Token

from app.config import get_settings


_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestContextFilter(logging.Filter):
    """Attach the current HTTP request id to every application log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configure_logging() -> None:
    """Configure readable console logs once during application import."""
    level_name = get_settings().LOG_LEVEL.upper().strip()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s "
        "request_id=%(request_id)s %(message)s"
    ))
    logging.basicConfig(level=level, handlers=[handler], force=True)


def set_request_id(value: str) -> Token:
    """Bind a request id to the current async context."""
    return _request_id.set(value)


def reset_request_id(token: Token) -> None:
    """Restore the request context after a response is produced."""
    _request_id.reset(token)
