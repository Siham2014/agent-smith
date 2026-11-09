"""Opt-in real API check. Not a pytest test; never runs on import."""

import argparse

from .errors import LLMError
from .service import generate_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optional single Gemini API call.")
    parser.add_argument("--allow-api", action="store_true", help="Explicitly allow one real request.")
    args = parser.parse_args(argv)
    if not args.allow_api:
        print("Disabled: pass --allow-api to authorize one real call. No request sent.")
        return 0
    try:
        response = generate_text("Explain in two sentences what a Python IndexError is.")
    except LLMError as error:
        print(f"{type(error).__name__}: {error}")
        return 1
    print(response.text)
    print(f"Model: {response.model}")
    print(f"Latency: {response.latency_seconds:.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
