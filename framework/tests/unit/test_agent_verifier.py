"""Static inspection is not a functional test or execution sandbox."""

import pytest

from agent_smith.agent.prompts import build_prompt
from agent_smith.agent.verifier import CodeExtractionError, extract_python_code, verify_code


@pytest.mark.parametrize("text,expected", [
    ("def f():\n    return 1", "def f():\n    return 1"),
    ("```python\nx = 1\n```", "x = 1"),
    ("Here is code:\n```python\nx = 1\n```\nExplanation.", "x = 1"),
    ("```py\r\nx = 1\r\n```", "x = 1"),
])
def test_extracts_one_python_proposal(text, expected):
    assert extract_python_code(text) == expected


@pytest.mark.parametrize("text", ["", "  ", "```python\n```", "```python\nx = 1", "```javascript\nx=1\n```",
    "```python\nx=1\n```\n```python\ny=2\n```", "```\nx=1\n```"])
def test_rejects_empty_or_ambiguous_markdown(text):
    with pytest.raises(CodeExtractionError):
        extract_python_code(text)


def test_reports_syntax_location_without_source():
    verification = verify_code("def f(:\n    pass")
    assert not verification.passed
    assert verification.level == "syntax"
    assert verification.code_extracted
    assert "line 1" in verification.errors[0]
    assert "def f" not in verification.errors[0]


@pytest.mark.parametrize("code", ["", "# comments only", '"explanation only"'])
def test_rejects_empty_module_or_text_only(code):
    verification = verify_code(code)
    assert not verification.passed
    assert verification.level == "structure"


@pytest.mark.parametrize("code", ["x = undefined_name", "def maximum(a, b, c):\n    return -999", "raise RuntimeError('would fail if executed')"])
def test_syntax_pass_is_not_functional_correctness(code):
    assert verify_code(code).passed


def test_correction_prompt_contains_previous_code_and_observation():
    prompt = build_prompt("Write a function", "def f(:", "Syntax error at line 1")
    assert "def f(:" in prompt
    assert "Syntax error at line 1" in prompt
    assert "Python code only" in prompt
    assert "claim it was tested" in prompt
