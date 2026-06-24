from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / ".agents" / "skills" / "verified-circuit-simulation"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
TRUST_PATH = SKILL_ROOT / "references" / "trust-boundary.md"
CASES_PATH = SKILL_ROOT / "references" / "validation-cases.md"
README_PATH = ROOT / "README.md"

REQUIRED_HEADINGS = (
    "## Trigger this Skill when",
    "## Do not trigger this Skill when",
    "## Supported product scope",
    "## Repository source of truth",
    "## Required spec-first workflow",
    "## Canonical CircuitPlan boundary",
    "## Trust and authority boundaries",
    "## Safe commands",
    "## Expected outputs",
    "## Error handling and stop conditions",
    "## Progressive references",
)

REFERENCED_PATHS = (
    "references/trust-boundary.md",
    "references/validation-cases.md",
    "README.md",
    "specs/product-requirements.md",
    "specs/acceptance-scenarios.md",
    "specs/architecture.md",
    "specs/bounded-agent-orchestration.md",
    "src/ai_electronics_lab/contracts/circuit_plan.py",
    "src/ai_electronics_lab/planning/openrouter.py",
    "src/ai_electronics_lab/orchestration/orchestrator.py",
    "src/ai_electronics_lab/simulation/",
    "src/ai_electronics_lab/verification/",
    "src/ai_electronics_lab/web/app.py",
    "scripts/verify.sh",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    result: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        assert separator == ":"
        assert key
        assert key not in result
        result[key] = value.strip()
    return result


def test_skill_frontmatter_is_minimal_and_named() -> None:
    frontmatter = _frontmatter(_read(SKILL_PATH))

    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "verified-circuit-simulation"
    assert "repository" in frontmatter["description"].lower()
    assert "bounded" in frontmatter["description"].lower()


def test_skill_covers_required_operating_contract() -> None:
    skill = _read(SKILL_PATH)

    for heading in REQUIRED_HEADINGS:
        assert skill.count(heading) == 1

    assert "RC low-pass filters" in skill
    assert "RC high-pass filters" in skill
    assert "unloaded resistive voltage dividers" in skill
    assert "GitHub `main` branch is authoritative" in skill
    assert "`CircuitPlan` is the canonical" in skill
    assert "do not merge without explicit user authorization" in skill
    assert "bash scripts/verify.sh" in skill


def test_validation_cases_have_three_triggers_and_three_non_triggers() -> None:
    cases = _read(CASES_PATH)

    assert len(re.findall(r"^### TRIGGER-[1-3]$", cases, flags=re.MULTILINE)) == 3
    assert len(re.findall(r"^### NONTRIGGER-[1-3]$", cases, flags=re.MULTILINE)) == 3
    assert "TRIGGER-4" not in cases
    assert "NONTRIGGER-4" not in cases


def test_validation_cases_include_guidance_and_boundary_tasks() -> None:
    cases = _read(CASES_PATH)

    assert "## Successful repository-guidance task" in cases
    assert "## Refusal and scope-boundary task" in cases
    assert "refuse the requested authority expansion" in cases
    assert "run focused tests and `bash scripts/verify.sh`" in cases


def test_referenced_repository_paths_exist() -> None:
    skill = _read(SKILL_PATH)

    for relative in REFERENCED_PATHS:
        assert f"`{relative}`" in skill
        if relative.startswith("references/"):
            path = SKILL_ROOT / relative
        else:
            path = ROOT / relative
        assert path.exists(), relative


def test_skill_documents_do_not_expose_secrets_or_private_paths() -> None:
    combined = "\n".join(
        (
            _read(SKILL_PATH),
            _read(TRUST_PATH),
            _read(CASES_PATH),
        )
    )

    forbidden_patterns = (
        r"sk-or-v1-[A-Za-z0-9_-]+",
        r"ghp_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"glpat-[A-Za-z0-9_-]{20,}",
        r"xox[baprs]-[A-Za-z0-9-]{20,}",
        r"AKIA[A-Z0-9]{16}",
        r"(?i)\bBearer\s+[A-Za-z0-9._-]{12,}",
        r"(?m)^[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)=\S+$",
        r"/home/[A-Za-z0-9._-]+/",
        r"/Users/[A-Za-z0-9._-]+/",
        r"(?i)C:\\Users\\[A-Za-z0-9._-]+\\",
        r"https?://(?:localhost|127\.0\.0\.1|10\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[01])\.)",
        r"private-user-images\.githubusercontent\.com",
        r"\{\s*\"choices\"\s*:",
    )

    for pattern in forbidden_patterns:
        assert re.search(pattern, combined) is None


def test_skill_keeps_product_scope_frozen() -> None:
    skill = _read(SKILL_PATH)
    cases = _read(CASES_PATH)
    scope = skill.split("## Supported product scope", 1)[1].split("##", 1)[0]
    supported_items = re.findall(r"^- (.+?)[.;]$", scope, flags=re.MULTILINE)

    assert supported_items == [
        "RC low-pass filters",
        "RC high-pass filters",
        "unloaded resistive voltage dividers",
    ]
    assert "supports exactly:" in scope
    assert "explicit non-goals" in scope
    assert "BJT circuits" in scope
    assert "arbitrary SPICE" in scope
    assert "does not execute simulations" in skill
    assert "Design a production BJT amplifier" in cases
    assert "unsupported product work" in cases


def test_readme_reports_current_skill_status() -> None:
    readme = _read(README_PATH)

    assert (
        "Agent Skill: included at "
        "`.agents/skills/verified-circuit-simulation/SKILL.md`"
    ) in readme
    assert "Google ADK adapter: not yet included" in readme
    assert "Agent Skill: not yet included" not in readme
