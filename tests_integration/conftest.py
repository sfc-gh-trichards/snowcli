from __future__ import annotations

import functools
import json
import pytest
from dataclasses import dataclass
from pathlib import Path
from snowcli.cli.app import app
from tempfile import NamedTemporaryFile
from typer import Typer
from typer.testing import CliRunner
from typing import List, Dict, Any

TEST_DIR = Path(__file__).parent


@dataclass
class CommandResult:
    exit_code: int
    json: List[Dict[str, Any]]


@pytest.fixture(scope="session")
def test_snowcli_config():
    test_config = TEST_DIR / "config/connection_configs.toml"
    with NamedTemporaryFile(suffix=".toml", mode="w+") as fh:
        fh.write(test_config.read_text())
        fh.flush()
        yield fh.name


@pytest.fixture(scope="session")
def test_root_path():
    return TEST_DIR


class SnowCLIRunner(CliRunner):
    def __init__(self, app: Typer, test_snowcli_config: str):
        super().__init__()
        self.app = app
        self.test_snowcli_config = test_snowcli_config

    @functools.wraps(CliRunner.invoke)
    def invoke(self, *a, **kw):
        return super().invoke(self.app, *a, **kw)

    def invoke_with_config(self, *args, **kwargs):
        return self.invoke(
            ["--config-file", self.test_snowcli_config, *args[0]],
            **kwargs,
        )

    def invoke_with_config_and_integration_connection(self, *args, **kwargs):
        return self.invoke(
            ["--config-file", self.test_snowcli_config, *args[0], "-c", "integration"],
            **kwargs,
        )

    def invoke_integration(self, *args, **kwargs) -> CommandResult:
        result = self.invoke(
            [
                "--format",
                "JSON",
                "--config-file",
                self.test_snowcli_config,
                *args[0],
                "-c",
                "integration",
            ],
            **kwargs,
        )
        if result.output == "":
            return CommandResult(result.exit_code, [])
        return CommandResult(result.exit_code, json.loads(result.output))


@pytest.fixture
def runner(test_snowcli_config):
    return SnowCLIRunner(app, test_snowcli_config)
