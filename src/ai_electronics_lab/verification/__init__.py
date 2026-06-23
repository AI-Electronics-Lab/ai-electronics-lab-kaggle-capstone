"""Public deterministic simulation verification API."""

from .evidence import (
    SIMULATION_VERIFIER_VERSION,
    VERIFICATION_ABSOLUTE_TOLERANCE,
    VERIFICATION_DENOMINATOR_FLOOR,
    VERIFICATION_RELATIVE_TOLERANCE,
    VERIFICATION_WARNING_MULTIPLIER,
    SimulationVerificationError,
    SimulationVerificationResults,
    VerificationComparison,
    VerificationComplexValue,
    VerificationRunResult,
    VerificationTolerancePolicy,
    verify_simulation_results,
)

__all__ = [
    "SIMULATION_VERIFIER_VERSION",
    "VERIFICATION_ABSOLUTE_TOLERANCE",
    "VERIFICATION_DENOMINATOR_FLOOR",
    "VERIFICATION_RELATIVE_TOLERANCE",
    "VERIFICATION_WARNING_MULTIPLIER",
    "SimulationVerificationError",
    "SimulationVerificationResults",
    "VerificationComparison",
    "VerificationComplexValue",
    "VerificationRunResult",
    "VerificationTolerancePolicy",
    "verify_simulation_results",
]
