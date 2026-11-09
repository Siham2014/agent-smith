"""Keep tests independent of local developer configuration."""

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    import os

    for key in tuple(os.environ):
        if key.upper().startswith("SMITH_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    """Automated tests must never contact Gemini, tracing, or another service."""
    import socket

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in automated tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
