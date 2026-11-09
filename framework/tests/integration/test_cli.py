"""Exercise the installed module and entry-point boundary."""

import os
import subprocess
import sys

from agent_smith.cli import main


def test_module_startup():
    result = subprocess.run(
        [sys.executable, "-m", "agent_smith"],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "configuration valid" in result.stdout
    assert "no model connected" in result.stdout


def test_installed_console_script():
    executable = os.path.join(os.path.dirname(sys.executable), "agent-smith.exe" if os.name == "nt" else "agent-smith")
    result = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"


def test_invalid_configuration_fails_without_leaking_input(monkeypatch, capsys):
    sensitive_value = "invalid-private-value"
    monkeypatch.setenv("SMITH_ENVIRONMENT", sensitive_value)
    assert main([]) == 2
    output = capsys.readouterr()
    assert "Invalid configuration" in output.err
    assert sensitive_value not in output.err + output.out


def test_custom_dotenv(tmp_path, capsys):
    dotenv = tmp_path / "custom.env"
    dotenv.write_text("SMITH_ENVIRONMENT=test\n", encoding="utf-8")
    assert main(["--env-file", str(dotenv)]) == 0
    assert "(test)" in capsys.readouterr().out


def test_unreadable_dotenv_is_reported(tmp_path, capsys):
    dotenv = tmp_path / "broken.env"
    dotenv.write_bytes(b"\xff\xfe")
    assert main(["--env-file", str(dotenv)]) == 2
    assert "Invalid configuration" in capsys.readouterr().err
