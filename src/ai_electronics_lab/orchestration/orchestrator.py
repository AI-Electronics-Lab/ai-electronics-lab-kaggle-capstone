from __future__ import annotations

import asyncio
import inspect
import json
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

from ai_electronics_lab.contracts import (
    CircuitPlan,
    CircuitPlanValidationError,
    require_valid_circuit_plan,
)
from ai_electronics_lab.planning import (
    CircuitPlannerError,
    OpenRouterPlannerConfig,
    load_openrouter_planner_config,
    plan_circuit_request,
)
from ai_electronics_lab.simulation import (
    SimulationAssembly,
    SimulationDeck,
    SimulationDeckError,
    SimulationParsedResults,
    SimulationRawParseError,
    SimulationRunnerError,
    build_simulation_assembly_from_plan,
    build_simulation_deck_from_assembly,
    parse_simulation_execution_evidence,
    run_simulation_deck,
)
from ai_electronics_lab.verification import (
    SimulationVerificationError,
    SimulationVerificationResults,
    verify_simulation_results,
)

BOUNDED_AGENT_ORCHESTRATION_VERSION = '1.0'
_MAX_PROMPT_CODE_POINTS = 4000
_MAX_PROMPT_BYTES = 16384
_TRACE_STAGES = {
    'request.received',
    'request.validated',
    'planner.requested',
    'planner.completed',
    'plan.validated',
    'assembly.completed',
    'deck.completed',
    'simulation.started',
    'simulation.completed',
    'parse.completed',
    'verification.completed',
    'request.completed',
    'request.failed',
}
_TRACE_STATUSES = {'started', 'completed', 'failed'}
_ERROR_MESSAGES = {
    'orchestration.request.content_type': 'Request Content-Type must be application/json.',
    'orchestration.request.encoding': 'Request body must be valid UTF-8.',
    'orchestration.request.empty': 'Request body must not be empty.',
    'orchestration.request.malformed_json': 'Request body must contain valid JSON.',
    'orchestration.request.duplicate_key': 'Duplicate JSON object keys are not accepted.',
    'orchestration.request.non_finite': 'Non-finite JSON numbers are not accepted.',
    'orchestration.request.object_required': 'Request body must be a JSON object.',
    'orchestration.request.prompt_invalid': 'Prompt violates the bounded prompt contract.',
    'orchestration.request.busy': 'Another orchestration request is already running.',
    'orchestration.planner.invalid': 'The bounded planner returned an invalid CircuitPlan.',
    'orchestration.planner.unavailable': 'The bounded planner could not complete.',
    'orchestration.plan.invalid': 'The request cannot be converted into a valid circuit plan.',
    'orchestration.deck_rejected': 'The trusted simulation deck could not be created.',
    'orchestration.execution_failed': 'The bounded local simulation could not complete.',
    'orchestration.evidence_invalid': 'The bounded simulation evidence could not be parsed.',
    'orchestration.verification_invalid': 'The deterministic simulation evidence could not be verified.',
    'orchestration.internal_error': 'The bounded orchestration pipeline could not complete.',
}
_PLANNER_INVALID_CODES = frozenset(
    {
        'planner.output.invalid_json',
        'planner.plan.unsupported_topology',
        'planner.plan.invalid',
        'planner.repair.exhausted',
    }
)
_ERROR_STATUS_CODES = {
    'orchestration.request.content_type': 400,
    'orchestration.request.encoding': 400,
    'orchestration.request.empty': 400,
    'orchestration.request.malformed_json': 400,
    'orchestration.request.duplicate_key': 400,
    'orchestration.request.non_finite': 400,
    'orchestration.request.object_required': 422,
    'orchestration.request.prompt_invalid': 422,
    'orchestration.request.busy': 429,
    'orchestration.planner.invalid': 422,
    'orchestration.planner.unavailable': 503,
    'orchestration.plan.invalid': 422,
    'orchestration.deck_rejected': 500,
    'orchestration.execution_failed': 503,
    'orchestration.evidence_invalid': 502,
    'orchestration.verification_invalid': 502,
    'orchestration.internal_error': 500,
}

class BoundedAgentOrchestrationError(RuntimeError):
    def __init__(
        self,
        code: str,
        path: tuple[str | int, ...] = (),
        message: str | None = None,
        *,
        status_code: int | None = None,
    ) -> None:
        safe_code = code if code in _ERROR_MESSAGES else 'orchestration.internal_error'
        self.code = safe_code
        self.path = _safe_path(path)
        self.message = _ERROR_MESSAGES[safe_code] if message is None else message
        self.status_code = status_code if status_code is not None else _ERROR_STATUS_CODES[safe_code]
        super().__init__(self.message)

    def __str__(self) -> str:
        location = '.'.join(str(item) for item in self.path) or '<root>'
        return f'{self.code} at {location}: {self.message}'

    def __repr__(self) -> str:
        return (
            f"BoundedAgentOrchestrationError(code={self.code!r}, path={self.path!r}, "
            f"message={self.message!r}, status_code={self.status_code!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {'code': self.code, 'path': list(self.path), 'message': self.message}

@dataclass(frozen=True, slots=True)
class BoundedAgentTraceEvent:
    stage: str
    status: str
    code: str | None = None
    path: tuple[str | int, ...] = ()

    def __post_init__(self) -> None:
        if self.stage not in _TRACE_STAGES:
            raise ValueError('trace stage is not part of the safe vocabulary')
        if self.status not in _TRACE_STATUSES:
            raise ValueError('trace status is not part of the safe vocabulary')
        object.__setattr__(self, 'path', tuple(self.path))
        if self.code is not None and type(self.code) is not str:
            raise ValueError('trace code must be a string or None')
        if any(type(item) not in {str, int} for item in self.path):
            raise ValueError('trace path elements must be strings or integers')

    def to_dict(self) -> dict[str, Any]:
        data = {'stage': self.stage, 'status': self.status}
        if self.code is not None:
            data['code'] = self.code
            data['path'] = list(self.path)
        return data

@dataclass(frozen=True, slots=True)
class BoundedAgentOrchestrationResult:
    version: str
    status: str
    stage_trace: tuple[BoundedAgentTraceEvent, ...]
    plan: CircuitPlan
    assembly: SimulationAssembly
    deck: SimulationDeck
    parsed_results: SimulationParsedResults
    verification: SimulationVerificationResults

    def __post_init__(self) -> None:
        object.__setattr__(self, 'stage_trace', tuple(self.stage_trace))
        if type(self.version) is not str or self.version != BOUNDED_AGENT_ORCHESTRATION_VERSION:
            raise ValueError('orchestration version is unsupported')
        if type(self.status) is not str or self.status not in {'PASS', 'WARN', 'FAIL'}:
            raise ValueError('orchestration status is invalid')
        if any(type(item) is not BoundedAgentTraceEvent for item in self.stage_trace):
            raise ValueError('stage trace entries are invalid')
        if type(self.plan) is not CircuitPlan:
            raise ValueError('plan is invalid')
        if type(self.assembly) is not SimulationAssembly:
            raise ValueError('assembly is invalid')
        if type(self.deck) is not SimulationDeck:
            raise ValueError('deck is invalid')
        if type(self.parsed_results) is not SimulationParsedResults:
            raise ValueError('parsed results are invalid')
        if type(self.verification) is not SimulationVerificationResults:
            raise ValueError('verification results are invalid')

    def to_dict(self) -> dict[str, Any]:
        return {
            'version': self.version,
            'status': self.status,
            'stage_trace': [item.to_dict() for item in self.stage_trace],
            'plan': self.plan.to_dict(),
            'assembly': self.assembly.to_dict(),
            'deck': self.deck.to_dict(),
            'parsed_results': self.parsed_results.to_dict(),
            'verification': self.verification.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

@dataclass(frozen=True, slots=True)
class BoundedAgentOrchestrationConfig:
    planner_config: OpenRouterPlannerConfig | None = None

    def __post_init__(self) -> None:
        if self.planner_config is not None and type(self.planner_config) is not OpenRouterPlannerConfig:
            raise ValueError('planner_config must be an OpenRouterPlannerConfig or None')

    def to_dict(self) -> dict[str, Any]:
        return {'planner_config': None if self.planner_config is None else self.planner_config.to_dict()}

def load_bounded_agent_orchestration_config() -> BoundedAgentOrchestrationConfig:
    return BoundedAgentOrchestrationConfig(planner_config=load_openrouter_planner_config())

def run_bounded_agent_orchestration(
    prompt: str,
    *,
    config: BoundedAgentOrchestrationConfig | None = None,
    planner: Callable[..., Any] = plan_circuit_request,
    runner: Callable[..., Any] = run_simulation_deck,
    parser: Callable[..., Any] = parse_simulation_execution_evidence,
    verifier: Callable[..., Any] = verify_simulation_results,
) -> BoundedAgentOrchestrationResult:
    bounded_prompt = _validate_prompt(prompt)
    planner_config = None if config is None else config.planner_config
    if planner is plan_circuit_request and planner_config is None:
        planner_config = load_openrouter_planner_config()

    stage_trace = [
        BoundedAgentTraceEvent('request.received', 'started'),
        BoundedAgentTraceEvent('request.validated', 'completed'),
        BoundedAgentTraceEvent('planner.requested', 'started'),
    ]

    try:
        candidate_plan = _call_callable(planner, bounded_prompt, config=planner_config)
        stage_trace.append(BoundedAgentTraceEvent('planner.completed', 'completed'))
        validated_plan = require_valid_circuit_plan(candidate_plan)
        stage_trace.append(BoundedAgentTraceEvent('plan.validated', 'completed'))
        assembly = build_simulation_assembly_from_plan(validated_plan)
        stage_trace.append(BoundedAgentTraceEvent('assembly.completed', 'completed'))
        deck = build_simulation_deck_from_assembly(assembly)
        stage_trace.append(BoundedAgentTraceEvent('deck.completed', 'completed'))
        stage_trace.append(BoundedAgentTraceEvent('simulation.started', 'started'))
        evidence = _call_callable(runner, deck)
        stage_trace.append(BoundedAgentTraceEvent('simulation.completed', 'completed'))
        parsed_results = _call_callable(parser, evidence)
        stage_trace.append(BoundedAgentTraceEvent('parse.completed', 'completed'))
        verification = _call_callable(verifier, validated_plan, parsed_results)
        stage_trace.append(BoundedAgentTraceEvent('verification.completed', 'completed'))
        stage_trace.append(BoundedAgentTraceEvent('request.completed', 'completed'))
        return BoundedAgentOrchestrationResult(
            version=BOUNDED_AGENT_ORCHESTRATION_VERSION,
            status=verification.status,
            stage_trace=tuple(stage_trace),
            plan=validated_plan,
            assembly=assembly,
            deck=deck,
            parsed_results=parsed_results,
            verification=verification,
        )
    except BoundedAgentOrchestrationError:
        raise
    except CircuitPlannerError as exc:
        if exc.code in _PLANNER_INVALID_CODES:
            code = 'orchestration.planner.invalid'
            status_code = 422
        else:
            code = 'orchestration.planner.unavailable'
            status_code = 503
        raise BoundedAgentOrchestrationError(
            code,
            exc.path,
            status_code=status_code,
        ) from None
    except CircuitPlanValidationError as exc:
        error = exc.errors[0] if exc.errors else None
        raise BoundedAgentOrchestrationError(
            'orchestration.planner.invalid',
            () if error is None else error.path,
            None if error is None else error.message,
            status_code=422,
        ) from None
    except SimulationDeckError as exc:
        raise BoundedAgentOrchestrationError(
            'orchestration.deck_rejected',
            exc.path,
            exc.message,
            status_code=500,
        ) from None
    except SimulationRunnerError as exc:
        raise BoundedAgentOrchestrationError(
            'orchestration.execution_failed',
            exc.path,
            exc.message,
            status_code=503,
        ) from None
    except SimulationRawParseError as exc:
        raise BoundedAgentOrchestrationError(
            'orchestration.evidence_invalid',
            exc.path,
            exc.message,
            status_code=502,
        ) from None
    except SimulationVerificationError as exc:
        raise BoundedAgentOrchestrationError(
            'orchestration.verification_invalid',
            exc.path,
            exc.message,
            status_code=502,
        ) from None
    except Exception as exc:
        raise BoundedAgentOrchestrationError('orchestration.internal_error', (), None, status_code=500) from exc

def _validate_prompt(prompt: object) -> str:
    if type(prompt) is not str:
        raise BoundedAgentOrchestrationError(
            'orchestration.request.prompt_invalid',
            ('prompt',),
            'Prompt must be a string.',
            status_code=422,
        )
    bounded = prompt.strip()
    if not bounded:
        raise BoundedAgentOrchestrationError(
            'orchestration.request.prompt_invalid',
            ('prompt',),
            'Prompt must not be empty.',
            status_code=422,
        )
    if len(bounded) > _MAX_PROMPT_CODE_POINTS or len(bounded.encode('utf-8')) > _MAX_PROMPT_BYTES:
        raise BoundedAgentOrchestrationError(
            'orchestration.request.prompt_invalid',
            ('prompt',),
            'Prompt is too large.',
            status_code=422,
        )
    if any(unicodedata.category(ch).startswith('C') for ch in bounded):
        raise BoundedAgentOrchestrationError(
            'orchestration.request.prompt_invalid',
            ('prompt',),
            'Prompt must not contain control characters.',
            status_code=422,
        )
    return bounded

def _call_callable(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    value = func(*args, **kwargs)
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value

def _safe_path(path: tuple[str | int, ...]) -> tuple[str | int, ...]:
    if any(type(item) not in {str, int} for item in path):
        return ('error_path',)
    return tuple(path)
