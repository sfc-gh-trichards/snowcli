from __future__ import annotations

import logging
import typer

from snowcli import utils
from snowcli.cli.stage.manager import StageManager
from snowcli.output.decorators import with_output
from snowcli.output.printing import OutputData
from snowcli.snow_connector import connect_to_snowflake
from snowcli.utils import generate_deploy_stage_name

from snowcli.cli.snowpark.procedure_coverage import app
from snowcli.cli.common.flags import ConnectionOption

log = logging.getLogger(__name__)


@app.command(
    "clear",
    help="Delete the code coverage reports from the stage, to start the measuring process over",
)
@with_output
def procedure_coverage_clear(
    environment: str = ConnectionOption,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Name of the procedure",
    ),
    input_parameters: str = typer.Option(
        ...,
        "--input-parameters",
        "-i",
        help="Input parameters - such as (message string, count int). Must exactly match those provided when creating the procedure.",
    ),
) -> OutputData:
    conn = connect_to_snowflake(connection_name=environment)
    deploy_dict = utils.get_deploy_names(
        conn.ctx.database,
        conn.ctx.schema,
        generate_deploy_stage_name(
            name,
            input_parameters,
        ),
    )
    coverage_path = f"""{deploy_dict["directory"]}/coverage"""
    cursor = StageManager(connection=conn).remove(
        stage_name=deploy_dict["stage"], path=coverage_path
    )
    log.info("Deleted the following coverage results from the stage:")
    return OutputData.from_cursor(cursor)
