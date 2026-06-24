"""Bounded OpenRouter adapter for untrusted CircuitPlan candidates."""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any
from urllib.parse import urlparse

import httpx2 as httpx

from ai_electronics_lab.contracts import (
    CircuitPlan,
    CircuitPlanValidationError,
    require_valid_circuit_plan,
)
from ai_electronics_lab.contracts.circuit_plan import SUPPORTED_TOPOLOGIES

OPENROUTER_PLANNER_VERSION = "1.0"

_BASE_URL_DEFAULT = "https://openrouter.ai/api/v1"
_CHAT_COMPLETIONS_URL = f"{_BASE_URL_DEFAULT}/chat/completions"
_DEFAULT_MODEL = "openai/gpt-oss-120b:free"
_DEFAULT_TIMEOUT_SECONDS = 20.0
_DEFAULT_MAX_TOKENS = 800
_CONNECT_TIMEOUT_SECONDS = 5.0
_READ_TIMEOUT_SECONDS = 15.0
_MAX_PROMPT_CODE_POINTS = 4000
_MAX_PROMPT_BYTES = 16384
_MAX_REQUEST_BYTES = 32768
_MAX_RESPONSE_BYTES = 65536
_MAX_CONTENT_BYTES = 16384
_MAX_JSON_NESTING = 80
_PYTHON_INT_MAX_STR_DIGITS = sys.get_int_max_str_digits()
_MAX_JSON_INTEGER_DIGITS = (
    _PYTHON_INT_MAX_STR_DIGITS if _PYTHON_INT_MAX_STR_DIGITS > 0 else 4300
)
_CANDIDATE_KEYS = frozenset(
    {
        "schema_version",
        "topology",
        "analysis",
        "parameters",
        "requested_frequencies_hz",
        "assumptions",
    }
)
_FORBIDDEN_CANDIDATE_KEYS = frozenset(
    {
        "netlist",
        "spice",
        "spice_directive",
        "shell",
        "command",
        "path",
        "tools",
        "tool_calls",
        "evidence",
        "verification",
        "status",
        "explanation",
    }
)
_TOPOLOGY_PARAMETER_KEYS = frozenset(
    {
        "capacitance_farads",
        "input_voltage_volts",
        "resistance_bottom_ohms",
        "resistance_ohms",
        "resistance_top_ohms",
    }
)
_SAFE_ERROR_PATH_TOKENS = frozenset(
    {
        "OPENROUTER_API_KEY",
        "assumptions",
        "analysis",
        "candidate",
        "capacitance_farads",
        "choices",
        "content",
        "duplicate_key",
        "error",
        "error_path",
        "finish_reason",
        "input_voltage_volts",
        "message",
        "parameters",
        "prompt",
        "provider_envelope",
        "requested_frequencies_hz",
        "resistance_bottom_ohms",
        "resistance_ohms",
        "resistance_top_ohms",
        "schema_version",
        "tool_calls",
        "topology",
        "unknown_field",
    }
)
_GENERIC_SAFE_ERROR_PATH = ("error_path",)

_SYSTEM_MESSAGE = (
    "Return exactly one JSON object for a CircuitPlan version 1.0. "
    "Use only schema_version, topology, analysis, parameters, "
    "requested_frequencies_hz, and assumptions. Supported topologies are "
    "rc_low_pass, rc_high_pass, and resistive_divider. Do not include prose, "
    "markdown, netlists, SPICE, commands, paths, tool calls, evidence, or explanations."
)

_REPAIR_MESSAGE = (
    "The previous candidate failed deterministic validation. Return one corrected exact "
    "JSON object. Do not include markdown, prose, netlists, commands, paths, evidence, "
    "or tool calls."
)

_ERROR_MESSAGES = {
    "planner.input.type": "Prompt must be a string.",
    "planner.input.empty": "Prompt must not be empty.",
    "planner.input.too_large": "Prompt is too large.",
    "planner.config.api_key_missing": "OpenRouter API key is required.",
    "planner.config.invalid": "OpenRouter planner configuration is invalid.",
    "planner.provider.timeout": "OpenRouter planner request timed out.",
    "planner.provider.network_error": "OpenRouter planner network request failed.",
    "planner.provider.http_error": "OpenRouter planner provider returned an unsuccessful status.",
    "planner.provider.response_oversized": "OpenRouter planner response is too large.",
    "planner.provider.envelope_invalid": "OpenRouter planner response envelope is invalid.",
    "planner.provider.content_missing": "OpenRouter planner response content is missing.",
    "planner.output.invalid_json": "OpenRouter planner returned invalid candidate JSON.",
    "planner.plan.unsupported_topology": "OpenRouter planner returned an unsupported topology.",
    "planner.plan.invalid": "OpenRouter planner returned an invalid CircuitPlan.",
    "planner.repair.exhausted": "OpenRouter planner repair attempt did not produce a valid plan.",
}


class CircuitPlannerError(ValueError):
    """Stable, user-safe planner failure."""

    def __init__(
        self,
        code: str,
        path: Iterable[str | int] = (),
        message: str = "",
    ) -> None:
        safe_code = code if type(code) is str and code in _ERROR_MESSAGES else "planner.config.invalid"
        self.code = safe_code
        self.path = _safe_error_path(path)
        self.message = (
            _ERROR_MESSAGES[safe_code]
            if type(message) is not str or message == ""
            else _safe_error_message(safe_code, message)
        )
        super().__init__(self.message)

    def __repr__(self) -> str:
        return (
            f"CircuitPlannerError(code={self.code!r}, path={self.path!r}, message={self.message!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "path": list(self.path), "message": self.message}


@dataclass(frozen=True, slots=True)
class OpenRouterPlannerConfig:
    """Validated OpenRouter planner configuration."""

    api_key: str = field(repr=False)
    base_url: str = _BASE_URL_DEFAULT
    model: str = _DEFAULT_MODEL
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    max_tokens: int = _DEFAULT_MAX_TOKENS

    def __post_init__(self) -> None:
        api_key = _validate_secret(self.api_key)
        base_url = _validate_base_url(self.base_url)
        model = _validate_model(self.model)
        timeout_seconds = _validate_timeout(self.timeout_seconds)
        max_tokens = _validate_max_tokens(self.max_tokens)
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "timeout_seconds", timeout_seconds)
        object.__setattr__(self, "max_tokens", max_tokens)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_tokens": self.max_tokens,
        }


def load_openrouter_planner_config() -> OpenRouterPlannerConfig:
    """Load only the explicitly named OpenRouter environment variables."""

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key is None or api_key.strip() == "":
        raise _planner_error("planner.config.api_key_missing", ("OPENROUTER_API_KEY",))
    try:
        return OpenRouterPlannerConfig(
            api_key=api_key,
            base_url=os.environ.get("OPENROUTER_BASE_URL", _BASE_URL_DEFAULT),
            model=os.environ.get("OPENROUTER_MODEL", _DEFAULT_MODEL),
            timeout_seconds=_parse_float_env(
                os.environ.get("OPENROUTER_TIMEOUT_SECONDS"), _DEFAULT_TIMEOUT_SECONDS
            ),
            max_tokens=_parse_int_env(os.environ.get("OPENROUTER_MAX_TOKENS"), _DEFAULT_MAX_TOKENS),
        )
    except CircuitPlannerError:
        raise
    except (TypeError, ValueError):
        raise _planner_error("planner.config.invalid") from None


async def plan_circuit_request(
    prompt: str,
    *,
    config: OpenRouterPlannerConfig | None = None,
) -> CircuitPlan:
    """Return one validated CircuitPlan from a bounded OpenRouter request."""

    return await _plan_circuit_request_with_transport(prompt, config=config, transport=None)


async def _plan_circuit_request_with_transport(
    prompt: str,
    *,
    config: OpenRouterPlannerConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CircuitPlan:
    """Private test seam for injecting a mocked HTTP transport."""

    bounded_prompt = _validate_prompt(prompt)
    planner_config = config if config is not None else load_openrouter_planner_config()
    try:
        _validate_config_instance(planner_config)
    except CircuitPlannerError:
        raise
    except (TypeError, ValueError):
        raise _planner_error("planner.config.invalid") from None

    try:
        async with asyncio.timeout(planner_config.timeout_seconds):
            try:
                content = await _request_candidate(
                    bounded_prompt,
                    planner_config,
                    repair_errors=(),
                    transport=transport,
                )
                return _candidate_to_plan(content, repair=False)
            except CircuitPlannerError as first_error:
                if not _is_repairable(first_error):
                    raise
                content = await _request_candidate(
                    bounded_prompt,
                    planner_config,
                    repair_errors=(first_error,),
                    transport=transport,
                )
                try:
                    return _candidate_to_plan(content, repair=True)
                except CircuitPlannerError as repair_error:
                    if _is_repairable(repair_error):
                        raise _planner_error("planner.repair.exhausted") from None
                    raise
    except TimeoutError:
        raise _planner_error("planner.provider.timeout") from None


async def _request_candidate(
    prompt: str,
    config: OpenRouterPlannerConfig,
    *,
    repair_errors: Sequence[CircuitPlannerError],
    transport: httpx.AsyncBaseTransport | None,
) -> str:
    body = _build_request_body(prompt, config, repair_errors)
    encoded_body = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded_body) > _MAX_REQUEST_BYTES:
        raise _planner_error("planner.input.too_large")

    timeout = httpx.Timeout(
        config.timeout_seconds,
        connect=min(_CONNECT_TIMEOUT_SECONDS, config.timeout_seconds),
        read=min(_READ_TIMEOUT_SECONDS, config.timeout_seconds),
        write=min(_CONNECT_TIMEOUT_SECONDS, config.timeout_seconds),
        pool=min(_CONNECT_TIMEOUT_SECONDS, config.timeout_seconds),
    )
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            verify=True,
            transport=transport,
        ) as client:
            async with client.stream(
                "POST",
                _CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                content=encoded_body,
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise _planner_error("planner.provider.http_error")
                response_bytes = await _read_bounded_response(response)
    except TimeoutError:
        raise _planner_error("planner.provider.timeout") from None
    except httpx.TimeoutException:
        raise _planner_error("planner.provider.timeout") from None
    except CircuitPlannerError:
        raise
    except httpx.RequestError:
        raise _planner_error("planner.provider.network_error") from None

    envelope = _decode_json_bytes(response_bytes, provider=True)
    return _extract_provider_content(envelope)


async def _read_bounded_response(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > _MAX_RESPONSE_BYTES:
            raise _planner_error("planner.provider.response_oversized")
        chunks.append(chunk)
    return b"".join(chunks)


def _build_request_body(
    prompt: str,
    config: OpenRouterPlannerConfig,
    repair_errors: Sequence[CircuitPlannerError],
) -> dict[str, Any]:
    messages = [{"role": "system", "content": _SYSTEM_MESSAGE}]
    if repair_errors:
        messages.append(
            {
                "role": "user",
                "content": _repair_prompt(prompt, repair_errors),
            }
        )
    else:
        messages.append({"role": "user", "content": prompt})
    return {
        "model": config.model,
        "messages": messages,
        "temperature": 0,
        "stream": False,
        "max_tokens": config.max_tokens,
        "reasoning": {"effort": "low", "exclude": True},
    }


def _repair_prompt(prompt: str, errors: Sequence[CircuitPlannerError]) -> str:
    stable_errors = [{"code": error.code, "path": list(error.path)} for error in errors[:8]]
    repair_context = {
        "original_bounded_prompt": prompt,
        "stable_validation_errors": stable_errors,
    }
    return (
        f"{_REPAIR_MESSAGE}\n"
        "Repair context JSON:\n"
        f"{json.dumps(repair_context, ensure_ascii=True, separators=(',', ':'))}"
    )


def _candidate_to_plan(content: str, *, repair: bool) -> CircuitPlan:
    candidate = _decode_candidate_content(content)
    topology = candidate.get("topology")
    if isinstance(topology, str) and topology not in SUPPORTED_TOPOLOGIES:
        raise _planner_error("planner.plan.unsupported_topology", ("topology",))
    try:
        plan = CircuitPlan(
            schema_version=candidate["schema_version"],
            topology=candidate["topology"],
            analysis=candidate["analysis"],
            parameters=candidate["parameters"],
            requested_frequencies_hz=candidate["requested_frequencies_hz"],
            assumptions=candidate["assumptions"],
        )
        return require_valid_circuit_plan(plan)
    except CircuitPlanValidationError as error:
        if repair:
            raise _planner_error("planner.plan.invalid", _validation_path(error)) from None
        raise _planner_error("planner.plan.invalid", _validation_path(error)) from None
    except (OverflowError, TypeError, ValueError):
        raise _planner_error("planner.plan.invalid") from None


def _validation_path(error: CircuitPlanValidationError) -> tuple[str | int, ...]:
    if not error.errors:
        return ()
    validation_path = error.errors[0].path
    if (
        len(validation_path) >= 2
        and validation_path[0] == "parameters"
        and validation_path[1] not in _TOPOLOGY_PARAMETER_KEYS
    ):
        return ("parameters", "unknown_field")
    return _safe_error_path(validation_path)


def _decode_candidate_content(content: str) -> dict[str, Any]:
    if not isinstance(content, str) or content == "":
        raise _planner_error("planner.provider.content_missing")
    if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
        raise _planner_error("planner.provider.response_oversized")
    stripped = content.strip()
    if stripped != content or stripped.startswith("```"):
        raise _planner_error("planner.output.invalid_json")
    candidate = _decode_json_text(content, provider=False)
    if type(candidate) is not dict:
        raise _planner_error("planner.output.invalid_json")
    keys = set(candidate)
    if keys != _CANDIDATE_KEYS:
        path = _candidate_key_path(keys)
        raise _planner_error("planner.output.invalid_json", path)
    return candidate


def _candidate_key_path(keys: set[str]) -> tuple[str | int, ...]:
    missing = sorted(_CANDIDATE_KEYS - keys, key=str)
    if keys - _CANDIDATE_KEYS or keys & _FORBIDDEN_CANDIDATE_KEYS:
        return ("candidate", "unknown_field")
    if missing:
        return ("candidate", missing[0])
    return ()


def _extract_provider_content(envelope: Any) -> str:
    if type(envelope) is not dict:
        raise _planner_error("planner.provider.envelope_invalid")
    choices = envelope.get("choices")
    if type(choices) is not list or len(choices) != 1:
        raise _planner_error("planner.provider.envelope_invalid", ("choices",))
    choice = choices[0]
    if type(choice) is not dict:
        raise _planner_error("planner.provider.envelope_invalid", ("choices", 0))
    if "error" in choice:
        raise _planner_error("planner.provider.envelope_invalid", ("choices", 0, "error"))
    if choice.get("finish_reason") != "stop":
        raise _planner_error("planner.provider.envelope_invalid", ("choices", 0, "finish_reason"))
    message = choice.get("message")
    if type(message) is not dict:
        raise _planner_error("planner.provider.envelope_invalid", ("choices", 0, "message"))
    tool_calls = message.get("tool_calls")
    if tool_calls not in (None, []):
        raise _planner_error(
            "planner.provider.envelope_invalid", ("choices", 0, "message", "tool_calls")
        )
    content = message.get("content")
    if type(content) is not str or content == "":
        raise _planner_error(
            "planner.provider.content_missing", ("choices", 0, "message", "content")
        )
    if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
        raise _planner_error("planner.provider.response_oversized")
    return content


def _decode_json_bytes(data: bytes, *, provider: bool) -> Any:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        code = "planner.provider.envelope_invalid" if provider else "planner.output.invalid_json"
        raise _planner_error(code) from None
    return _decode_json_text(text, provider=provider)


def _decode_json_text(text: str, *, provider: bool) -> Any:
    code = "planner.provider.envelope_invalid" if provider else "planner.output.invalid_json"
    duplicate_path = (
        ("provider_envelope", "duplicate_key") if provider else ("candidate", "duplicate_key")
    )
    if _nesting_exceeds_limit(text):
        raise _planner_error(code)
    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_keys(code, duplicate_path),
        parse_constant=_reject_json_constant(code),
        parse_float=_parse_json_float(code),
        parse_int=_parse_json_int(code),
    )
    decoded_text = text.lstrip(" \t\r\n") if provider else text
    try:
        value, end = decoder.raw_decode(decoded_text)
    except CircuitPlannerError:
        raise
    except (JSONDecodeError, OverflowError, TypeError, ValueError):
        raise _planner_error(code) from None
    if decoded_text[end:].strip():
        raise _planner_error(code)
    return value


def _reject_duplicate_keys(code: str, duplicate_path: tuple[str, str]):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _planner_error(code, duplicate_path)
            result[key] = value
        return result

    return hook


def _reject_json_constant(code: str):
    def reject(_value: str) -> None:
        raise _planner_error(code)

    return reject


def _parse_json_int(code: str):
    def parse(value: str) -> int:
        digits = value[1:] if value.startswith("-") else value
        if len(digits) > _MAX_JSON_INTEGER_DIGITS:
            raise _planner_error(code)
        return int(value)

    return parse


def _parse_json_float(code: str):
    def parse(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise _planner_error(code)
        return parsed

    return parse


def _nesting_exceeds_limit(text: str) -> bool:
    depth = 0
    in_string = False
    escape = False
    for character in text:
        if in_string:
            if escape:
                escape = False
            elif character == "\\":
                escape = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_JSON_NESTING:
                return True
        elif character in "]}":
            depth -= 1
    return False


def _validate_prompt(prompt: str) -> str:
    if type(prompt) is not str:
        raise _planner_error("planner.input.type")
    bounded = prompt.strip()
    if bounded == "":
        raise _planner_error("planner.input.empty")
    if len(bounded) > _MAX_PROMPT_CODE_POINTS:
        raise _planner_error("planner.input.too_large")
    if len(bounded.encode("utf-8")) > _MAX_PROMPT_BYTES:
        raise _planner_error("planner.input.too_large")
    return bounded


def _validate_config_instance(config: OpenRouterPlannerConfig) -> None:
    if type(config) is not OpenRouterPlannerConfig:
        raise _planner_error("planner.config.invalid")
    OpenRouterPlannerConfig(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        timeout_seconds=config.timeout_seconds,
        max_tokens=config.max_tokens,
    )


def _validate_secret(value: Any) -> str:
    if type(value) is not str:
        raise _planner_error("planner.config.invalid")
    if _has_control_character(value):
        raise _planner_error("planner.config.invalid")
    trimmed = value.strip()
    if trimmed == "":
        raise _planner_error("planner.config.api_key_missing", ("OPENROUTER_API_KEY",))
    if len(trimmed) > 4096:
        raise _planner_error("planner.config.invalid")
    return trimmed


def _validate_base_url(value: Any) -> str:
    if type(value) is not str:
        raise _planner_error("planner.config.invalid")
    trimmed = value.strip()
    try:
        parsed = urlparse(trimmed)
    except ValueError:
        raise _planner_error("planner.config.invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"openrouter.ai", "openrouter.ai:443"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"/api/v1", "/api/v1/"}
    ):
        raise _planner_error("planner.config.invalid")
    return _BASE_URL_DEFAULT


def _validate_model(value: Any) -> str:
    if type(value) is not str:
        raise _planner_error("planner.config.invalid")
    if _has_control_character(value):
        raise _planner_error("planner.config.invalid")
    trimmed = value.strip()
    if trimmed == "" or len(trimmed) > 200:
        raise _planner_error("planner.config.invalid")
    return trimmed


def _validate_timeout(value: Any) -> float:
    if type(value) not in (int, float):
        raise _planner_error("planner.config.invalid")
    timeout = float(value)
    if not math.isfinite(timeout) or timeout < 1 or timeout > 60:
        raise _planner_error("planner.config.invalid")
    return timeout


def _validate_max_tokens(value: Any) -> int:
    if type(value) is not int:
        raise _planner_error("planner.config.invalid")
    if value < 64 or value > 2048:
        raise _planner_error("planner.config.invalid")
    return value


def _parse_float_env(value: str | None, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _parse_int_env(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _has_control_character(value: str) -> bool:
    return any(not character.isprintable() for character in value)


def _is_repairable(error: CircuitPlannerError) -> bool:
    return error.code in {"planner.output.invalid_json", "planner.plan.invalid"}


def _planner_error(code: str, path: Iterable[str | int] = ()) -> CircuitPlannerError:
    return CircuitPlannerError(code=code, path=path)


def _safe_error_message(code: str, message: str) -> str:
    if type(message) is str and message == _ERROR_MESSAGES[code]:
        return message
    return _ERROR_MESSAGES[code]


def _safe_error_path(path: Iterable[str | int]) -> tuple[str | int, ...]:
    try:
        raw_path = tuple(path)
    except Exception:
        return _GENERIC_SAFE_ERROR_PATH
    if not raw_path:
        return ()
    for token in raw_path:
        if type(token) is int:
            if token < 0:
                return _GENERIC_SAFE_ERROR_PATH
            continue
        if type(token) is not str or token not in _SAFE_ERROR_PATH_TOKENS:
            return _GENERIC_SAFE_ERROR_PATH
    return raw_path


__all__ = [
    "OPENROUTER_PLANNER_VERSION",
    "CircuitPlannerError",
    "OpenRouterPlannerConfig",
    "load_openrouter_planner_config",
    "plan_circuit_request",
]
