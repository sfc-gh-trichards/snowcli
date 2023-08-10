import snowcli
from snowcli.cli.stage import commands
from snowcli.plugin.api import PluginSpec, PluginPath


@snowcli.plugin.api.plugin_hook_impl
def plugin_spec() -> PluginSpec:
    return PluginSpec(path=PluginPath([]), typer_instance=commands.app)
