from __future__ import annotations

import os

import click
import logging
import hashlib
from io import StringIO

from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import Optional

import snowflake.connector
from snowflake.connector.cursor import SnowflakeCursor
from snowflake.connector.errors import ForbiddenError, DatabaseError

from snowcli.config import cli_config, get_default_connection
from snowcli.exception import SnowflakeConnectionError, InvalidConnectionConfiguration

log = logging.getLogger(__name__)
TEMPLATES_PATH = Path(__file__).parent / "sql"


class SnowflakeConnector:
    """Initialize a connection from a snowsql-formatted config"""

    def __init__(
        self,
        connection_parameters: dict,
        overrides: Optional[dict] = None,
    ):
        if overrides:
            connection_parameters.update(
                {k: v for k, v in overrides.items() if v is not None}
            )
        self.ctx = snowflake.connector.connect(
            application=self._find_command_path(),
            **connection_parameters,
        )
        self.cs = self.ctx.cursor()

    @staticmethod
    def _find_command_path():
        ctx = click.get_current_context(silent=True)
        if ctx:
            # Example: SNOWCLI.WAREHOUSE.STATUS
            return ".".join(["SNOWCLI", *ctx.command_path.split(" ")[1:]]).upper()
        return "SNOWCLI"

    def __del__(self):
        try:
            self.cs.close()
            self.ctx.close()
        except (TypeError, AttributeError):
            pass

    def get_version(self):
        self.cs.execute("SELECT current_version()")
        return self.cs.fetchone()[0]

    def create_function(
        self,
        name: str,
        input_parameters: str,
        return_type: str,
        handler: str,
        imports: str,
        database: str,
        schema: str,
        role: str,
        warehouse: str,
        overwrite: bool,
        packages: list[str],
    ) -> SnowflakeCursor:
        return self.run_sql(
            "create_function",
            {
                "database": database,
                "schema": schema,
                "role": role,
                "warehouse": warehouse,
                "name": name,
                "overwrite": overwrite,
                "input_parameters": input_parameters,
                "return_type": return_type,
                "handler": handler,
                "imports": imports,
                "packages": packages,
                "signature": self.generate_signature_from_params(
                    input_parameters,
                ),
            },
        )

    def create_procedure(
        self,
        name: str,
        input_parameters: str,
        return_type: str,
        handler: str,
        imports: str,
        database: str,
        schema: str,
        role: str,
        warehouse: str,
        overwrite: bool,
        packages: list[str],
        execute_as_caller: bool,
    ) -> SnowflakeCursor:
        return self.run_sql(
            "create_procedure",
            {
                "database": database,
                "schema": schema,
                "role": role,
                "warehouse": warehouse,
                "name": name,
                "overwrite": overwrite,
                "input_parameters": input_parameters,
                "return_type": return_type,
                "handler": handler,
                "imports": imports,
                "packages": packages,
                "signature": self.generate_signature_from_params(
                    input_parameters,
                ),
                "execute_as_caller": execute_as_caller,
            },
        )

    def upload_file_to_stage(
        self,
        file_path,
        destination_stage,
        path,
        role,
        database,
        warehouse,
        schema,
        overwrite,
        parallel: int = 4,
        create_stage: bool = True,
    ):
        create_stage_command = ""
        if create_stage:
            create_stage_command = (
                f"create stage if not exists {destination_stage} "
                "comment='deployments managed by snowcli'"
            )

        full_stage_name = (
            f"@{destination_stage}"
            if not destination_stage.startswith("snow://")
            else destination_stage
        )
        return self.run_sql(
            "put_stage",
            {
                "role": role,
                "database": database,
                "schema": schema,
                "warehouse": warehouse,
                "path": file_path,
                "destination_path": path,
                "name": full_stage_name,
                "create_stage_command": create_stage_command,
                "parallel": parallel,
                "overwrite": overwrite,
            },
        )

    def describe_function(
        self,
        database,
        schema,
        role,
        warehouse,
        signature=None,
        name=None,
        input_parameters=None,
        show_exceptions=True,
    ) -> SnowflakeCursor:
        if signature is None and name and input_parameters:
            signature = name + self.generate_signature_from_params(input_parameters)
        return self.run_sql(
            "describe_function",
            {
                "database": database,
                "schema": schema,
                "role": role,
                "warehouse": warehouse,
                "signature": signature,
            },
            show_exceptions,
        )

    def describe_procedure(
        self,
        database,
        schema,
        role,
        warehouse,
        signature=None,
        name=None,
        input_parameters=None,
        show_exceptions=True,
    ) -> SnowflakeCursor:
        if signature is None and name and input_parameters:
            signature = name + self.generate_signature_from_params(input_parameters)
        return self.run_sql(
            "describe_procedure",
            {
                "database": database,
                "schema": schema,
                "role": role,
                "warehouse": warehouse,
                "signature": signature,
            },
            show_exceptions,
        )

    def set_procedure_comment(
        self,
        database,
        schema,
        role,
        warehouse,
        signature=None,
        name=None,
        input_parameters=None,
        show_exceptions=True,
        comment="",
    ) -> SnowflakeCursor:
        if signature is None and name and input_parameters:
            signature = name + self.generate_signature_from_params(input_parameters)
        return self.run_sql(
            "set_procedure_comment",
            {
                "database": database,
                "schema": schema,
                "role": role,
                "warehouse": warehouse,
                "signature": signature,
                "comment": comment,
            },
            show_exceptions,
        )

    def list_procedures(
        self,
        database,
        schema,
        role,
        warehouse,
        like="%%",
    ) -> SnowflakeCursor:
        return self.run_sql(
            "list_procedures",
            {
                "database": database,
                "schema": schema,
                "role": role,
                "warehouse": warehouse,
                "like": like,
            },
        )

    def drop_procedure(
        self,
        database,
        schema,
        role,
        warehouse,
        signature,
    ) -> SnowflakeCursor:
        return self.run_sql(
            "drop_procedure",
            {
                "database": database,
                "schema": schema,
                "role": role,
                "warehouse": warehouse,
                "signature": signature,
            },
        )

    def run_sql(
        self,
        command,
        context,
        show_exceptions=True,
    ) -> SnowflakeCursor:
        env = Environment(loader=FileSystemLoader(TEMPLATES_PATH))
        template = env.get_template(f"{command}.sql")
        sql = template.render(**context)
        try:
            log.debug(f"Executing sql:\n{sql}")
            results = self.ctx.execute_stream(StringIO(sql))

            # Return result from last cursor
            *_, last_result = results
            return last_result
        except snowflake.connector.errors.ProgrammingError as e:
            if show_exceptions:
                log.error(f"Error executing sql:\n{sql}")
            raise e

    @staticmethod
    def generate_signature_from_params(params: str) -> str:
        if params == "()":
            return "()"
        return "(" + " ".join(params.split()[1::2])


def connect_to_snowflake(connection_name: Optional[str] = None, **overrides) -> SnowflakeConnector:  # type: ignore
    connection_name = (
        connection_name if connection_name is not None else get_default_connection()
    )
    try:
        return SnowflakeConnector(
            connection_parameters=cli_config.get_connection(connection_name),
            overrides=overrides,
        )
    except ForbiddenError as err:
        raise SnowflakeConnectionError(err)
    except DatabaseError as err:
        raise InvalidConnectionConfiguration(err.msg)
