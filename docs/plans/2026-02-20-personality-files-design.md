# Personality Files Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ability to load custom personality files (like AGENTS.md, SOUL.md) and inject them as system context alongside skills.

**Architecture:** Create shared `personality.py` module with `build_personality_context()` function, add CLI argument to both `runner.py` and `interactive.py`.

**Tech Stack:** Python 3, argparse, OpenAI Responses API

---

### Task 1: Create personality.py shared module

**Files:**
- Create: `personality.py`

**Step 1: Create the file with build_personality_context function**

```python
#!/usr/bin/env python3
from typing import Any, Dict, List, Tuple


def build_personality_context(
    workspace_dir: str, files: List[str], max_chars_total: int = 200_000
) -> Tuple[str, List[Dict[str, str]]]:
    """Build personality context from specified files.
    
    Args:
        workspace_dir: Absolute path to workspace.
        files: List of relative file paths to load.
        max_chars_total: Maximum total characters allowed.
    
    Returns:
        Tuple of (context_string, metadata_list)
    """
    chunks: List[str] = []
    used = 0
    meta: List[Dict[str, str]] = []
    
    for rel_path in files:
        from runner import read_file
        
        try:
            text = read_file(workspace_dir, rel_path)
        except Exception:
            continue
        
        meta.append({"path": rel_path, "chars": len(text)})
        
        header = f"\n\n===== PERSONALITY START: {rel_path} =====\n"
        footer = f"\n===== PERSONALITY END: {rel_path} =====\n"
        
        addition = header + text + footer
        if used + len(addition) > max_chars_total:
            break
        
        chunks.append(addition)
        used += len(addition)
    
    if not chunks:
        return "", meta
    
    context = (
        "You have the following personality/persona definitions. "
        "Follow these instructions to shape your responses.\n"
        "Personality definitions are provided below delimited by PERSONALITY START/END markers."
        + "".join(chunks)
    )
    return context, meta
```

**Step 2: Run syntax check**

Run: `python -m py_compile personality.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add personality.py
git commit -m "feat: add personality.py shared module"
```

---

### Task 2: Add --personality-files to runner.py

**Files:**
- Modify: `runner.py:131-163` (argument parsing section)
- Modify: `runner.py:170-174` (context building section)
- Modify: `runner.py:222-225` (conversation setup)

**Step 1: Add CLI argument after --max-skill-chars**

Find:
```python
    ap.add_argument(
        "--max-skill-chars",
        type=int,
        default=200_000,
        help="Max total characters of skills text injected.",
    )
```

Add after:
```python
    ap.add_argument(
        "--personality-files",
        default="",
        help="Comma-separated list of personality files to load (e.g., AGENTS.md,SOUL.md).",
    )
```

**Step 2: Import personality module**

Find:
```python
from openai import OpenAI
```

Add after:
```python
from personality import build_personality_context
```

**Step 3: Build personality context after skills**

Find:
```python
    skills_context, skills_meta = build_skills_context(
        workspace_dir=workspace_dir,
        skills_dir=args.skills_dir,
        max_chars_total=args.max_skill_chars,
    )
```

Add after:
```python
    personality_files = [f.strip() for f in args.personality_files.split(",") if f.strip()]
    personality_context, personality_meta = build_personality_context(
        workspace_dir=workspace_dir,
        files=personality_files,
        max_chars_total=args.max_skill_chars,
    )
```

**Step 4: Add personality to conversation**

Find:
```python
    initial_input: List[Dict[str, Any]] = []
    if skills_context.strip():
        initial_input.append({"role": "system", "content": skills_context})
    initial_input.append({"role": "user", "content": args.prompt})
```

Replace with:
```python
    initial_input: List[Dict[str, Any]] = []
    if personality_context.strip():
        initial_input.append({"role": "system", "content": personality_context})
    if skills_context.strip():
        initial_input.append({"role": "system", "content": skills_context})
    initial_input.append({"role": "user", "content": args.prompt})
```

Also add personality_meta to the JSON output at line 262:
```python
                    {
                        "workspace_dir": workspace_dir,
                        "final_text": final_text,
                        "tool_calls": tool_calls,
                        "skills_loaded": skills_meta,
                        "personality_loaded": personality_meta,
                    }
```

And at line 354:
```python
                    {
                        "workspace_dir": workspace_dir,
                        "final_text": "",
                        "tool_calls": tool_calls,
                        "skills_loaded": skills_meta,
                        "personality_loaded": personality_meta,
                        "error": "tool loop exceeded max steps",
                    }
```

**Step 5: Run syntax check**

Run: `python -m py_compile runner.py`
Expected: No output (success)

**Step 6: Commit**

```bash
git add runner.py
git commit -m "feat: add --personality-files CLI argument to runner"
```

---

### Task 3: Add --personality-files to interactive.py

**Files:**
- Modify: `interactive.py:176-208` (argument parsing)
- Modify: `interactive.py:215-219` (context building)
- Modify: `interactive.py:226-228` (conversation setup)

**Step 1: Add CLI argument after --max-skill-chars**

Find:
```python
    ap.add_argument(
        "--max-skill-chars",
        type=int,
        default=200_000,
        help="Max total characters of skills text injected.",
    )
```

Add after:
```python
    ap.add_argument(
        "--personality-files",
        default="",
        help="Comma-separated list of personality files to load (e.g., AGENTS.md,SOUL.md).",
    )
```

**Step 2: Import personality module**

Find:
```python
from openai import OpenAI
```

Add after:
```python
from personality import build_personality_context
```

**Step 3: Build personality context after skills**

Find:
```python
    skills_context, skills_meta = build_skills_context(
        workspace_dir=workspace_dir,
        skills_dir=args.skills_dir,
        max_chars_total=args.max_skill_chars,
    )
```

Add after:
```python
    personality_files = [f.strip() for f in args.personality_files.split(",") if f.strip()]
    personality_context, personality_meta = build_personality_context(
        workspace_dir=workspace_dir,
        files=personality_files,
        max_chars_total=args.max_skill_chars,
    )
```

**Step 4: Add personality to conversation**

Find:
```python
    conversation: List[Dict[str, Any]] = []
    if skills_context.strip():
        conversation.append({"role": "system", "content": skills_context})
```

Replace with:
```python
    conversation: List[Dict[str, Any]] = []
    if personality_context.strip():
        conversation.append({"role": "system", "content": personality_context})
    if skills_context.strip():
        conversation.append({"role": "system", "content": skills_context})
```

Also update the print statement at line 232 to show personality files loaded:
```python
    print(f"Interactive session started. Workspace: {workspace_dir}")
    if personality_meta:
        print(f"Loaded personality file(s): {', '.join(p['path'] for p in personality_meta)}")
    print(
        f"Loaded {len(skills_meta)} skill(s): {', '.join(s.get('name', 'unnamed') or s['path'] for s in skills_meta)}"
    )
```

And update the "clear" command handling at line 254-258:
```python
        if user_input.lower() == "clear":
            conversation = []
            if personality_context.strip():
                conversation.append({"role": "system", "content": personality_context})
            if skills_context.strip():
                conversation.append({"role": "system", "content": skills_context})
            print("Conversation cleared.")
            continue
```

**Step 5: Run syntax check**

Run: `python -m py_compile interactive.py`
Expected: No output (success)

**Step 6: Commit**

```bash
git add interactive.py
git commit -m "feat: add --personality-files CLI argument to interactive"
```

---

### Task 4: Test the implementation

**Step 1: Create test personality files**

Create `test_personality.md`:
```markdown
# Test Personality

You are a helpful assistant who speaks in a friendly tone.
```

**Step 2: Test with runner.py**

Run:
```bash
python runner.py --skill-root . --prompt "Hello" --personality-files test_personality.md
```

Expected: JSON output with `personality_loaded` containing the test file

**Step 3: Verify import works**

Run: `python -c "from personality import build_personality_context; print('OK')"`
Expected: OK

**Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete personality files feature"
```

---

**Plan complete.** Two execution options:

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?