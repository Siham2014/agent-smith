"""Configuration check and explicitly opted-in single LLM request."""

import argparse
from collections.abc import Sequence
import sys

from pydantic import ValidationError

from agent_smith import __version__
from agent_smith.config import load_settings


def main(argv: Sequence[str] | None = None) -> int:
    """Validate configuration and return a shell-friendly exit code."""
    parser = argparse.ArgumentParser(description="Agent Smith configuration check")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--env-file", default=".env", help="Optional UTF-8 dotenv path")
    live = parser.add_mutually_exclusive_group()
    live.add_argument("--llm-smoke-test", action="store_true", help="Opt in to ONE real Gemini IndexError request")
    live.add_argument("--prompt", help="Opt in to ONE real Gemini request with this user message")
    live.add_argument("--agent-task", help="Opt in to a bounded coding workflow (at most two Gemini requests)")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env_file)
    except (ValidationError, OSError, UnicodeError):
        # Do not echo configuration values: future settings may contain secrets.
        print("Invalid configuration. Check SMITH_ settings and the dotenv file.", file=sys.stderr)
        return 2
    if args.agent_task is not None:
        from agent_smith.agent import run_agent
        from agent_smith.providers.gemini import GeminiProvider
        from agent_smith.providers.base import LLMError

        if not args.agent_task.strip():
            print("Agent task must not be blank.", file=sys.stderr)
            return 2
        try:
            result = run_agent(args.agent_task, GeminiProvider(settings))
        except (LLMError, ValueError):
            print("Agent initialization failed. Check the task and local LLM configuration.", file=sys.stderr)
            return 2
        key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
        text = result.code.replace(key, "[REDACTED]") if key else result.code
        print(text)
        print(f"Status: {result.status}")
        print(f"Stop reason: {result.stop_reason}")
        print(f"LLM calls: {result.llm_calls}")
        print(f"Total latency: {result.total_latency_seconds:.3f} seconds")
        return 2 if result.status == "failed" else 0
    if args.llm_smoke_test or args.prompt is not None:
        from agent_smith.providers.gemini import GeminiProvider
        from agent_smith.providers.base import LLMError

        prompt = "Explain in two sentences what a Python IndexError is." if args.llm_smoke_test else args.prompt
        try:
            response = GeminiProvider(settings).ask(prompt)
        except (LLMError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        # Do not echo a configured secret even if returned by a provider.
        key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
        text = response.text.replace(key, "[REDACTED]") if key else response.text
        print(text)
        print(f"Latency: {response.latency_seconds:.3f} seconds")
        return 0
    print(f"Agent Smith {__version__}: configuration valid ({settings.environment}).")
    print("Phase 3: no model connected by default and no execution sandbox implemented.")
    return 0
