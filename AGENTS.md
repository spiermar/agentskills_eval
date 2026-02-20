# AGENTS.md - Agent Coding Guidelines

This document provides guidance for agentic coding agents operating in this repository.

## Project Overview

This is a Python-based evaluation framework for testing agent skills. It uses the OpenAI Responses API to run agents against test cases and verify their behavior.

- **Language**: Python 3
- **Dependencies**: `openai` SDK (see `runner.py:9`)
- **Entry Points**: `eval.py`, `runner.py`

## Build, Lint, and Test Commands

### Running Evaluations

```bash
# Run all evaluation cases
python eval.py

# Run the runner directly with custom prompts
python runner.py --skill-root . --prompt "..."

# Run with custom skills directory
python runner.py --skill-root . --skills-dir skills/ --prompt "..."
```

### Required Environment Variables

```bash
# Required
export OPENAI_API_KEY="your-api-key"

# Optional (defaults shown)
export OPENAI_MODEL="gpt-5"
export OPENAI_API_BASE="https://api.openai.com/v1"  # For other providers (e.g., Anthropic, Ollama)
```

### Running the Interactive Session

```bash
# Start an interactive chat session with skills loaded
python interactive.py --skill-root . --skills-dir skills/

# Custom max tool iterations per turn
python interactive.py --skill-root . --max-steps 10
```

Commands in interactive mode:
- `exit` / `quit` / `q` - End the session
- `clear` - Clear conversation history (keeps skills loaded)

### Running Tests

This project does **not** have a formal test framework (pytest, unittest). To run a single evaluation case manually:

```python
# Import and call eval_case directly from eval.py
from eval import eval_case, load_cases

cases = load_cases("evals/cases.jsonl")
result = eval_case(cases[0])  # Run first case
print(result)
```

### Linting

No formal linter is configured. When making changes:

- Run Python syntax check: `python -m py_compile eval.py runner.py`
- Ensure imports are valid: `python -c "import eval, runner"`

## Code Style Guidelines

### General Principles

- Write clean, readable Python code
- Keep functions focused and small (< 50 lines preferred)
- Use descriptive variable and function names
- Add docstrings for public functions

### Imports

Organize imports in the following order (separate groups with blank lines):

1. Standard library imports (`os`, `sys`, `subprocess`, `json`, etc.)
2. Third-party imports (`openai`, `dataclasses`)
3. Local application imports

```python
# Correct import order (eval.py)
import json, os, re, sys, subprocess
from dataclasses import dataclass
from typing import Any, Dict, List
```

### Formatting

- Use **f-strings** for string interpolation
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters (soft guideline)
- Use blank lines sparingly to separate logical sections

### Types

- Use **type hints** for all function parameters and return types
- Use `typing` module for complex types (`List`, `Dict`, `Any`, `Optional`)
- Use dataclasses for simple data containers

```python
# Good - type hints used
def load_cases(path: str) -> List[Dict[str, Any]]:
    ...

@dataclass
class RunResult:
    tool_calls: List[Dict[str, Any]]
    final_text: str
    workspace_dir: str
```

### Naming Conventions

- **Functions/variables**: `snake_case` (e.g., `run_agent`, `skill_was_used`)
- **Classes**: `PascalCase` (e.g., `RunResult`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `CASES_PATH`)
- **Files**: `snake_case.py`

### Error Handling

- Use specific exception types when possible
- Include context in error messages
- Use `try/except` blocks sparingly - only catch expected errors

```python
# Good - specific error with context
try:
    text = read_file(workspace_dir, rel_path)
except Exception:
    continue  # Skip files that can't be read
```

```python
# Good - raise with context
if p.returncode != 0:
    raise RuntimeError(f"runner failed (code {p.returncode}):\nSTDERR:\n{p.stderr}\nSTDOUT:\n{p.stdout}")
```

### File Structure

```
agentskills_eval/
├── AGENTS.md              # This file
├── README.md              # Project documentation
├── eval.py                # Main evaluation runner
├── runner.py              # OpenAI API integration
├── interactive.py         # Interactive chat session
├── evals/
│   └── cases.jsonl        # Test cases (JSONL format)
└── skills/                # Skills directory (external)
    └── SKILL.md           # Skill definitions
```

### Working with JSONL

Test cases are stored in JSONL format (one JSON object per line):

```bash
# View cases
cat evals/cases.jsonl

# Add a new case (append JSON as single line)
echo '{"id": "new-case", "prompt": "...", "expect": {...}}' >> evals/cases.jsonl
```

### Security Considerations

- Never hardcode API keys - use environment variables
- Sanitize file paths to prevent directory traversal (see `safe_join` in `runner.py`)
- Be careful with `shell=True` in subprocess calls

### Common Patterns

**Tool loop pattern** (from runner.py):
1. Create initial API request with tools
2. Execute and collect tool calls
3. Run tools and collect outputs
4. Feed outputs back to API
5. Repeat until no pending tool calls or max steps reached

**Evaluation pattern** (from eval.py):
1. Load test cases from JSONL
2. Run agent for each case
3. Check expectations (routing, process, outcomes)
4. Aggregate and report results

### Adding New Features

When adding new functionality:

1. Add new command-line arguments to `argparse` in `runner.py` or `eval.py`
2. Update README.md with usage examples
3. Add test cases to `evals/cases.jsonl`
4. Verify with `python eval.py`

### Getting Help

- See `README.md` for quick start guide
- Check `runner.py` for tool implementation examples
- Examine `evals/cases.jsonl` for test case format

## Lessons Learned

### Avoid Circular Imports

Never import from `runner.py` in shared modules. This causes circular import errors:

```python
# BAD - causes circular import
from runner import read_file
```

Instead, duplicate the needed functions in your module:

```python
# GOOD - self-contained module
def safe_join(workspace: str, relpath: str) -> str:
    relpath = relpath.lstrip("/").replace("..", "")
    return os.path.join(workspace, relpath)

def read_file(workspace: str, path: str) -> str:
    abspath = safe_join(workspace, path)
    with open(abspath, "r", encoding="utf-8") as f:
        return f.read()
```

### Import Placement

- Always place imports at the top of the file, not inside functions or loops
- Importing inside loops causes repeated import overhead
- Importing inside functions can cause circular import issues

### Test Early and Often

- Test each task after implementation before proceeding to the next
- Run syntax checks: `python3 -m py_compile <file>.py`
- Verify imports work: `python3 -c "from module import function"`
- Run a quick end-to-end test to catch integration issues early

### Type Annotations

- Be pragmatic with type annotations - don't over-engineer
- If a value needs to be a specific type for the API, cast it explicitly
- Don't change type annotations mid-implementation based on review feedback without good reason
- The spec's type annotation takes precedence; implement to match the spec

### Virtual Environment Issues

When testing in a worktree, Python imports may fail because dependencies aren't available:

```bash
# Error you'll see:
ModuleNotFoundError: No module named 'openai'
```

Fix by using the parent project's venv:

```bash
# Source the venv from the parent project directory
source /path/to/parent/.venv/bin/activate
cd /path/to/worktree
python runner.py ...
```

Or use PYTHONPATH:

```bash
PYTHONPATH=/path/to/worktree python -c "from module import ..."
```