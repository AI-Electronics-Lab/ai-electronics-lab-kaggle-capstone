# Submission evidence index

Record only reproducible, reviewable, and non-sensitive evidence.

## Competition submission contract

The logged-in Kaggle competition Overview, Rules, Writeup, media, track, and project-link interfaces
were reviewed on 2026-06-24.

The final submission deadline displayed by Kaggle is **2026-07-07 at 09:59 GMT+3**.

A valid submission requires:

- one Kaggle Writeup of no more than 2,500 words;
- a title of no more than 80 characters;
- a subtitle of no more than 140 characters;
- one 560 by 280 card and thumbnail image;
- selection of one competition track;
- at least one media-gallery image;
- one public YouTube or Vimeo video of no more than five minutes;
- one public project link;
- final submission rather than an unsubmitted draft.

A public GitHub repository with detailed setup instructions is accepted when a public live deployment
is not feasible. A live public endpoint is not required.

Each team may make one submission. The submission must demonstrate at least three course concepts.
This repository provides code-level evidence for:

1. an Agent / Google ADK workflow;
2. security features;
3. an Agent Skill.

## Public repository evidence

| Claim | Public evidence | Status |
| --- | --- | --- |
| Problem, solution, value, architecture, and setup | `README.md`, `specs/architecture.md` | Complete |
| Frozen three-topology scope | `README.md`, `docs/decisions.md` | Complete |
| Bounded natural-language planner | `src/ai_electronics_lab/planning/`, planner tests | Complete |
| Deterministic circuit and SPICE authority | `src/ai_electronics_lab/simulation/`, simulation tests | Complete |
| Bounded ngspice execution and parsing | runner/parser specifications, source, and tests | Complete |
| Deterministic PASS/WARN/FAIL verification | `docs/evaluation.md`, verifier tests | Complete |
| Successful live run for each supported topology | Phase 0 record in `docs/development-log.md` | Complete |
| Fresh-clone installation and live request | `docs/fresh-clone-evidence.md` | Complete |
| Unsupported and malformed request rejection | `docs/evaluation.md` | Complete |
| Complete automated evaluation | `docs/evaluation.md` | Complete |
| Public security architecture | `docs/security.md` | Complete |
| Current-tree and full-history secret scan | `docs/secret-scan-evidence.md` | Complete |
| Agent Skill | `.agents/skills/verified-circuit-simulation/`, Skill tests | Complete |
| Google ADK Workflow and FunctionTool | `src/ai_electronics_lab/adk/`, ADK tests | Complete |
| Reproducible verification entry point | `scripts/verify.sh`, `.github/workflows/ci.yml` | Complete |
| Public file-scoped licensing | `LICENSE`, `LICENSE-DOCUMENTATION`, `LICENSING.md` | Complete |

## External submission assets still required

These items belong to the Kaggle submission workflow and are not yet complete:

- final track selection;
- final 560 by 280 card and thumbnail image;
- at least one sanitized media-gallery image;
- public YouTube or Vimeo demonstration video of no more than five minutes;
- final Kaggle Writeup;
- attached public GitHub project link;
- final screenshots and video timestamps;
- final Kaggle submission confirmation.

Claims about Codex or Antigravity contributions must be supported by reviewable project history or a
visible demonstration rather than unsupported narrative.

## Evidence safety

Do not include:

- credentials or `.env` contents;
- hidden chain-of-thought;
- raw provider responses;
- raw child-process output;
- temporary filesystem paths;
- private production traces;
- claims for plots, comparisons, explanations, persistence, memory, MCP, or cloud deployment.

Every claimed capability must be reproducible from the public repository.
