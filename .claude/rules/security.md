# Python Security Guidelines

## Mandatory Checks Before Every Commit

```
□ No secrets hardcoded (API keys, passwords, tokens, connection strings)
□ All user inputs validated and sanitized
□ SQL queries use parameterized statements — never string formatting
□ HTML output is escaped / sanitized
□ Authentication and authorization verified on every protected route
□ Rate limiting active on all public endpoints
□ Error responses never expose stack traces, internal paths, or credentials
□ Dependencies scanned for known CVEs
```

If **any** item fails → STOP. Fix before continuing.

---

## Secret Management

Use `os.environ["KEY"]` (raises `KeyError`) — never `os.getenv("KEY")` (silent `None`). A missing secret must be a loud startup failure.

```python
# ❌
OPENAI_API_KEY = "sk-proj-xxxxx"

# ✅
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
```

Validate all required secrets at startup via a frozen `Settings` dataclass loaded at import time. Use `python-dotenv` in dev entry points only. `.env` is never committed; `.env.example` is.

---

## Input Validation

Use Pydantic for all external inputs. Allowlist over blocklist.

```python
class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    age: int = Field(ge=0, le=150)
```

```python
if column not in ALLOWED_SORT_COLUMNS:
    raise ValueError(f"Sort column '{column}' is not allowed.")
```

---

## SQL Injection Prevention

Always parameterized queries. Never string formatting or concatenation.

```python
# ❌
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# ✅
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
# or SQLAlchemy ORM / text() with bound params
```

---

## Authentication and Authorization

- Authenticate before authorizing — never skip the identity check.
- Short-lived tokens (JWT `exp`, max 1h for sensitive ops).
- Never store plaintext passwords — use `bcrypt` or `argon2-cffi`.
- Invalidate sessions on logout and password change.

---

## Sensitive Data Handling

Never log passwords, tokens, API keys, or PII. Return generic error + correlation ID to clients; log detail server-side.

```python
# ❌
return {"error": str(exception), "traceback": traceback.format_exc()}

# ✅
logger.exception("Unhandled error [%s]", correlation_id)
return {"error": "An internal error occurred.", "correlation_id": correlation_id}
```

---

## Rate Limiting

Every public/authenticated endpoint must have rate limiting (e.g. `slowapi`):
- General endpoints: 60/minute
- Auth/sensitive endpoints: 5/minute

---

## Dependency Security

```bash
uv run pip-audit --fail-on HIGH   # add to CI
```

Keep deps pinned in `pyproject.toml`. Never commit `uv.lock` changes without reviewing what changed.

---

## Agents — Additional Rules

**Prompt injection**: never interpolate raw user input into system prompts — place untrusted content in a separate `<user_input>` block.

**Tool call validation**: validate every argument with Pydantic before executing a tool, even when the caller is the LLM.

**Shell access**: never `shell=True` with user-controlled input — pass args as a list: `subprocess.run(["ls", "--", user_input])`.

**LLM output**: never `eval` or `exec` — parse structured output, validate shape with Pydantic.

---

## Security Response Protocol

```
1. STOP — do not push, do not merge
2. Assess: CRITICAL / HIGH / MEDIUM / LOW
3. CRITICAL/HIGH → fix before any other work
4. Exposed secret: rotate immediately, audit access logs, assume git history is compromised
5. Search codebase for the same pattern
6. Add a test that would have caught it
```

| Severity | Examples | Action |
|---|---|---|
| CRITICAL | Exposed secret, RCE, auth bypass | Stop everything, fix now |
| HIGH | SQL injection, privilege escalation, PII leak | Fix before next deploy |
| MEDIUM | Missing rate limit, verbose error messages | Fix in current sprint |
| LOW | Missing security header, minor info leak | Backlog with deadline |

---

## Quick Reference Checklist

- [ ] No secrets or credentials in source code or logs
- [ ] `.env` in `.gitignore`, never staged
- [ ] All external inputs through Pydantic validation
- [ ] All SQL uses parameterized queries
- [ ] Error responses: generic message + correlation ID only
- [ ] Sensitive data never logged
- [ ] Rate limiting on all endpoints
- [ ] `uv run pip-audit` shows no HIGH or CRITICAL CVEs
- [ ] Agent tool calls validate arguments before execution
- [ ] No `shell=True` with user-controlled input
- [ ] No `eval`/`exec` on LLM-generated content
