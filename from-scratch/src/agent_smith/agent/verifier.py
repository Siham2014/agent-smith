"""Conservative text extraction and AST parsing; no code execution."""

import ast
import re

from .models import AgentState, VerificationResult

MAX_OUTPUT_CHARACTERS = 100_000


class CodeExtractionError(ValueError):
    """Safe, fixed extraction diagnostic."""


def extract_python_code(text: str) -> str:
    """Accept raw code or one explicitly Python-tagged fenced Markdown block."""
    if not isinstance(text, str) or not text.strip():
        raise CodeExtractionError("Extraction error: response is empty.")
    if len(text) > MAX_OUTPUT_CHARACTERS:
        raise CodeExtractionError("Extraction error: response exceeds the 100000-character limit.")
    text = text.strip()
    fences = list(re.finditer(r"(?m)^[ \t]*```[^\n]*$", text))
    if not fences:
        return text
    if len(fences) != 2:
        raise CodeExtractionError("Extraction error: ambiguous or unclosed Markdown fences.")
    opening, closing = fences
    if not re.fullmatch(r"[ \t]*```(?:python|py)[ \t]*\r?", opening.group(), re.IGNORECASE):
        raise CodeExtractionError("Extraction error: the single block must be tagged Python.")
    if not re.fullmatch(r"[ \t]*```[ \t]*\r?", closing.group()):
        raise CodeExtractionError("Extraction error: invalid closing Markdown fence.")
    code = text[opening.end():closing.start()].strip()
    if not code:
        raise CodeExtractionError("Extraction error: the Python block is empty.")
    return code


def verify_code(state: AgentState) -> VerificationResult:
    """Check already-extracted source; passing says nothing about behavior."""
    code = state.generated_code
    if not code.strip():
        return VerificationResult(
            passed=False, code_extracted=False,
            errors=["Extraction error: no Python code was extracted."],
        )
    if len(code) > MAX_OUTPUT_CHARACTERS:
        return VerificationResult(
            passed=False, code_extracted=True,
            errors=["Static check stopped: source exceeds the 100000-character limit."],
        )
    try:
        ast.parse(code)
    except SyntaxError as error:
        # Do not echo the source line, which may contain sensitive task data.
        message = f"Syntax error at line {error.lineno or 1}, column {error.offset or 1}."
        return VerificationResult(
            passed=False, code_extracted=True, errors=[message],
        )
    except (ValueError, RecursionError, MemoryError):
        return VerificationResult(
            passed=False, code_extracted=True,
            errors=["Static parser could not process this source; simplify the code."],
        )
    return VerificationResult(passed=True, code_extracted=True)
