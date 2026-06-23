"""Minimal localhost browser interface for deterministic simulation evidence."""

from .app import (
    MAX_REQUEST_BODY_BYTES,
    MAX_UI_FREQUENCIES,
    WebUIError,
    app,
    create_app,
    simulate_request,
)

__all__ = [
    "MAX_REQUEST_BODY_BYTES",
    "MAX_UI_FREQUENCIES",
    "WebUIError",
    "app",
    "create_app",
    "simulate_request",
]
