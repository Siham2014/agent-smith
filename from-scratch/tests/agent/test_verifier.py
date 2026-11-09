"""Extraction and syntax validation independently of any LLM."""

import pytest

from agent_smith.agent.models import AgentState
from agent_smith.agent.verifier import (
    MAX_OUTPUT_CHARACTERS, CodeExtractionError, extract_python_code, verify_code,
)


@pytest.mark.parametrize("text,expected", [
    ("x = 1", "x = 1"),
    ("  x = 1\n", "x = 1"),
    ("```python\nx = 1\n```", "x = 1"),
    ("```PYTHON\r\nx = 1\r\n```", "x = 1"),
    ("Explanation\n```py\nx = 1\n```\nEnd", "x = 1"),
    ('x = "inline ``` stays Python"', 'x = "inline ``` stays Python"'),
])
def test_unambiguous_python_extraction(text, expected) -> None:
    assert extract_python_code(text) == expected


@pytest.mark.parametrize("text", [
    "", "  ", None,
    "```python\nx = 1",
    "```python\nx = 1\n```\n```python\ny = 2\n```",
    "```python\nx = 1\n```\n```json\n{}\n```",
    "```javascript\nlet x = 1;\n```",
    "```\nx = 1\n```",
    "```python\n   \n```",
    "```python\nx = 1\n```not-a-closing-fence",
])
def test_invalid_or_ambiguous_extraction(text) -> None:
    with pytest.raises(CodeExtractionError):
        extract_python_code(text)


def test_response_size_is_bounded_before_ast_parsing() -> None:
    with pytest.raises(CodeExtractionError, match="limit"):
        extract_python_code("x" * (MAX_OUTPUT_CHARACTERS + 1))


@pytest.mark.parametrize("source", [
    "x = 1", "# syntactically valid comment",
    "import os\nraise RuntimeError('not executed')",
    "def answer():\n    return 1 / 0",
])
def test_valid_python_only_passes_static_syntax(source) -> None:
    result = verify_code(AgentState(task="task", generated_code=source))
    assert result.passed
    assert result.level == "syntax"
    assert result.code_extracted
    assert result.errors == []


def test_syntax_and_extraction_errors_are_distinguished() -> None:
    syntax = verify_code(AgentState(task="task", generated_code="def f(\n"))
    missing = verify_code(AgentState(task="task"))
    assert syntax.code_extracted is True
    assert syntax.errors[0].startswith("Syntax error")
    assert missing.code_extracted is False
    assert missing.errors[0].startswith("Extraction error")
    assert not syntax.passed
    assert not missing.passed


def test_syntax_diagnostic_has_location_but_not_source_or_secret() -> None:
    source = "synthetic-secret-in-source ="
    result = verify_code(AgentState(task="task", generated_code=source))
    assert not result.passed
    assert "line 1" in result.errors[0]
    assert "column" in result.errors[0]
    assert "synthetic-secret" not in result.errors[0]
    assert all(len(message) <= 240 for message in result.errors)


def test_direct_verification_also_bounds_source_size() -> None:
    result = verify_code(AgentState(
        task="task", generated_code="x" * (MAX_OUTPUT_CHARACTERS + 1),
    ))
    assert not result.passed
    assert result.code_extracted


@pytest.mark.parametrize("failure", [
    ValueError("synthetic-secret"), RecursionError("synthetic-secret"),
    MemoryError("synthetic-secret"),
])
def test_parser_resource_failures_are_bounded_and_sanitized(failure, monkeypatch) -> None:
    from agent_smith.agent import verifier
    def fail(source):
        raise failure
    monkeypatch.setattr(verifier.ast, "parse", fail)
    result = verify_code(AgentState(task="task", generated_code="x = 1"))
    assert not result.passed
    assert "synthetic-secret" not in str(result.errors)
