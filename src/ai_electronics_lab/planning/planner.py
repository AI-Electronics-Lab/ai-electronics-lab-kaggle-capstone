"""Public natural-language circuit planner entrypoint."""

from __future__ import annotations

from .structured_openrouter import plan_circuit_request

__all__ = ["plan_circuit_request"]
