# Agent Skills Eval Bundle

This bundle contains:
- `eval.py`: reads `evals/cases.jsonl`, runs `runner.py`, and performs deterministic checks.
- `runner.py`: OpenAI Responses API runner that copies a repo to an isolated workspace, loads *all* skills under a configurable directory (default `skills/`), and runs a simple tool loop (read/write/shell).
- `interactive.py`: Interactive chat session with agent skills.
- `evals/cases.jsonl`: example test cases.

## Quick start

1) Install dependencies:
```bash
uv sync
```

2) Set env vars:
```bash
export OPENAI_API_KEY="your-key"
# Optional
export OPENAI_MODEL="gpt-5"
export OPENAI_API_BASE="https://api.openai.com/v1"  # For other providers
```

3) Run evaluations:
```bash
# Using uv run (no install needed)
uv run python eval.py

# Or after installing
uv sync
python eval.py

# Using console scripts (after uv sync)
agent-eval
agent-runner --skill-root . --prompt "..."
agent-interactive --skill-root .
```

## Runner arguments

```bash
uv run python runner.py --skill-root . --prompt "..."
uv run python runner.py --skill-root . --skills-dir skills/ --prompt "..."

# Use custom model and API endpoint
uv run python runner.py --skill-root . --prompt "..." --model claude-sonnet-4-20250514 --api-base https://api.anthropic.com
```

## Interactive session

```bash
uv run python interactive.py --skill-root . --skills-dir skills/
```

Notes:
- Skills are discovered by finding `SKILL.md` or `skill.md` under the skills dir.
- Skills are injected into a system message delimited by `SKILL START/END` markers.