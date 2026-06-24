# Submission evidence

Record only reproducible, reviewable, and non-sensitive evidence.

## Required evidence

- clean-clone installation;
- localhost application startup;
- one successful prompt run for each of the three supported topologies;
- one safely rejected unsupported request;
- bounded ngspice execution evidence;
- generated engineering schematic;
- reproducible `PASS`, `WARN`, and `FAIL` examples where deterministic fixtures permit them;
- complete automated test output;
- secret-scan output;
- Agent Skill validation after the Skill is added;
- Google ADK adapter validation after the adapter is added;
- meaningful Codex contribution evidence;
- meaningful Antigravity contribution evidence;
- final screenshots and video timestamps.

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
