from __future__ import annotations

from typing import Optional, List

import click
from snowflake.connector.cursor import SnowflakeCursor

from snowcli.cli.common.sql_execution import SqlExecutionMixin


class ProcedureManager(SqlExecutionMixin):
    @staticmethod
    def identifier(
        name: Optional[str] = None,
        signature: Optional[str] = None,
        name_and_signature: Optional[str] = None,
    ):
        if all([name, signature, name_and_signature]):
            raise click.ClickException(
                "Provide only one, name and arguments or full signature. Both provided."
            )

        if not (name and signature) and not name_and_signature:
            raise click.ClickException(
                "Provide either name and arguments or full signature. None provided."
            )

        if name and signature:
            name_and_signature = name + signature

        return name_and_signature

    def drop(self, identifier: str) -> SnowflakeCursor:
        return self._execute_query(f"drop procedure {identifier}")

    def show(self, like: Optional[str] = None) -> SnowflakeCursor:
        query = "show user procedures"
        if like:
            query += f" like '{like}'"
        return self._execute_query(query)

    def describe(self, identifier: str) -> SnowflakeCursor:
        return self._execute_query(f"describe procedure {identifier}")

    def execute(self, expression: str) -> SnowflakeCursor:
        return self._execute_query(f"call {expression}")

    @staticmethod
    def artifact_stage_path(identifier: str):
        return (
            identifier.replace(
                "(",
                "",
            )
            .replace(
                ")",
                "",
            )
            .replace(
                " ",
                "_",
            )
            .replace(
                ",",
                "",
            )
            .lower()
        )

    def create(
        self,
        identifier: str,
        return_type: str,
        handler: str,
        artifact_file: str,
        packages: List[str],
        overwrite: bool,
        execute_as_caller: bool,
    ) -> SnowflakeCursor:
        create_stmt = "create or replace" if overwrite else "create"
        packages_list = ",".join(f"'{p}'" for p in packages)
        query = f"""\
            {create_stmt} procedure {identifier}
            returns {return_type}
            language python
            runtime_version=3.8
            imports=('@{artifact_file}')
            handler='{handler}'
            packages=({packages_list})
        """
        if execute_as_caller:
            query += "\nexecute as caller"
        return self._execute_query(query)
