"""Extraction and AST inspection only; no execution or compilation to bytecode."""

import ast
import re

from agent_smith.agent.models import VerificationResult


class CodeExtractionError(ValueError):
    """Response does not contain one unambiguous Python proposal."""


def extract_python_code(response: str) -> str:
    text = response.strip()
    if not text:
        raise CodeExtractionError("Empty response: no Python code available.")
    if "```" in text:
        blocks = list(re.finditer(r"```[ \t]*(?:python|py)[ \t]*\r?\n(.*?)```", text, re.DOTALL | re.IGNORECASE))
        if text.count("```") != 2 or len(blocks) != 1:
            raise CodeExtractionError("Expected exactly one complete Python Markdown block.")
        text = blocks[0].group(1).strip()
    if not text:
        raise CodeExtractionError("Empty Python code block.")
    return text


def verify_code(code: str) -> VerificationResult:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return VerificationResult(passed=False, level="syntax", code_extracted=True,
            errors=[f"Invalid Python syntax at line {exc.lineno}, column {exc.offset}."])
    except (ValueError, RecursionError):
        return VerificationResult(passed=False, level="structure", code_extracted=True,
            errors=["Python source could not be parsed."])
    if not tree.body or all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str) for node in tree.body):
        return VerificationResult(passed=False, level="structure", code_extracted=True,
            errors=["No usable Python statements found (empty, comments or text only)."])
    return VerificationResult(passed=True, level="syntax", code_extracted=True)
