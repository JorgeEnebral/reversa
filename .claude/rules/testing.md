# Python Testing Guide

## Requirements

| Requirement | Value |
|---|---|
| Minimum coverage | **80%** |
| Test runner | `pytest` |
| Coverage tool | `pytest-cov` |
| E2E tool | `playwright` |
| Mocking | `unittest.mock` / `pytest-mock` |

```bash
make test   # or: uv run pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

---

## Test Types (ALL required)

```
tests/
  unit/        ← isolated, no I/O, mock everything external
  integration/ ← real DB/HTTP, components working together
  e2e/         ← Playwright, critical flows only
  conftest.py  ← shared fixtures per directory
```

---

## TDD — MANDATORY

```
1. RED    → write test first — must FAIL
2. GREEN  → minimal impl to make it pass
3. IMPROVE → refactor, stay green
4. VERIFY → coverage still ≥ 80%
```

---

## Writing Tests

Follow **Arrange / Act / Assert**. One logical assertion per test. Name: `test_<what>_<condition>`.

```python
def test_compute_duration_returns_correct_value() -> None:
    """Duration is end minus start."""
    assert compute_duration(start=3, end=10) == 7
```

Use `@pytest.mark.parametrize` to avoid duplication. Define reusable state in `conftest.py`, never duplicate setup across tests.

---

## Mocking

Use `pytest-mock` (`mocker` fixture). Never let unit tests hit network, filesystem, or DB.

```python
def test_load_traces_calls_read_csv(mocker: pytest.MockerFixture) -> None:
    mock_read = mocker.patch("src.io.pd.read_csv", return_value=pd.DataFrame())
    load_traces(path="fake/path.csv")
    mock_read.assert_called_once_with("fake/path.csv")
```

- Patch at the **import site** (`src.module.dependency`), not at the source.
- Always assert mocks were called with expected arguments.
- Use `mocker.patch.object` for class methods.

---

## E2E (Playwright)

Critical flows only — not for logic that belongs in unit tests.

```bash
uv run playwright install chromium && uv run pytest tests/e2e/ -v
```

---

## Coverage

**80% minimum** — build fails below this. Coverage is a floor, not a target. Do not write empty assertions or exclude files arbitrarily.

---

## Troubleshooting

```bash
uv run pytest tests/path/test_file.py::test_name -v --tb=long  # single test
uv run pytest tests/ -x                                         # stop at first failure
```

Fix implementation, not tests. Check fixture scope for flaky tests.

---

## Quick Reference Checklist

- [ ] Test written **before** implementation (RED → GREEN → IMPROVE)
- [ ] Every new function has at least one unit test
- [ ] New API endpoints have integration tests
- [ ] Critical flows have E2E coverage
- [ ] `make test` passes with coverage ≥ 80%
- [ ] All mocks assert they were called correctly
- [ ] No `assert True` or empty test bodies
