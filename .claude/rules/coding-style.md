# Python Coding Style Guide

## Toolchain

| Tool | Purpose |
|---|---|
| `ruff format` | Code formatting |
| `ruff check` | Linting + auto-fix |
| `mypy` | Static type checking (strict) |
| `pylint` | Code quality (min score: 8.0) |
| `complexipy` | Cyclomatic complexity analysis |
| `pytest` | Testing |

```bash
make all     # install + format + lint + test + clean
make check   # ruff + mypy + pylint + complexipy
make format  # auto-format and fix with ruff
make test    # run pytest
```

---

## Module Header

Every `.py` file must start with a module-level docstring before any imports:

```python
"""
Módulo de autenticación de usuarios.

Provee funciones para validar credenciales y gestionar sesiones.
"""

from __future__ import annotations
```

---

## Type Annotations (mypy strict)

All functions and methods must be fully annotated.

- Use `from __future__ import annotations` in every file.
- Prefer `X | Y` over `Union[X, Y]`.
- Never use bare `dict`, `list`, `tuple` — always annotate generics.
- All `TypedDict`, `dataclass`, and `NamedTuple` fields must be typed.

```python
# ✅
def get_user(user_id: int) -> str | None: ...

# ❌
def get_user(user_id): ...
```

---

## Google-Style Docstrings

All public modules, classes, methods, and functions must have a Google-style docstring. Private helpers (`_name`) when logic is non-trivial.

```python
def compute_duration(start: int, end: int) -> int:
    """Computes the duration between two timesteps.

    Args:
        start: The initial timestep of the trace.
        end: The final timestep of the trace.

    Returns:
        Number of timesteps elapsed from start to end.

    Raises:
        ValueError: If end is less than start.

    Example:
        >>> compute_duration(3, 10)
        7
    """
    if end < start:
        raise ValueError(f"end ({end}) must be >= start ({start})")
    return end - start
```

Classes: include `Attributes:` and `Example:` sections. Properties: one-line docstring only.

---

## Code Quality Rules

**Complexity**: keep cyclomatic complexity low (`complexipy` runs on every `make check`). Extract helpers for functions with >~5 branches.

**Pylint ≥ 8.0**: common deductions — missing docstrings, too many arguments (refactor into a config dataclass), unused imports, non-descriptive names.

**Naming:**

| Kind | Convention | Example |
|---|---|---|
| Module | `snake_case` | `trace_analyzer.py` |
| Class | `PascalCase` | `TraceAnalyzer` |
| Function / method | `snake_case` | `get_top_traces` |
| Constant | `UPPER_SNAKE_CASE` | `DEFAULT_TOP_N = 10` |
| Private | leading `_` | `_validate_columns` |

---

## Imports

Order (enforced by ruff):
1. `from __future__ import annotations`
2. Standard library
3. Third-party
4. Local / project

Never use wildcard imports (`from module import *`).

---

## Quick Reference Checklist

- [ ] Module-level docstring at the top of every `.py` file
- [ ] All functions/methods have Google-style docstrings
- [ ] All arguments and return types are annotated
- [ ] `make check` passes (ruff + mypy + pylint ≥ 8 + complexipy)
- [ ] `make test` passes
- [ ] No wildcard imports
- [ ] No bare `dict` / `list` / `tuple` without generics
