import logging
from typing import List

import pluggy

from snowcli.cli.common.snow_cli_global_context import global_context_copy
from snowcli.config import cli_config
from snowcli.plugin import (
    ExternalPluginsLoadingMode,
    ExternalLoadedPlugin,
    ExternalPluginPackageInfo,
)
from snowcli.plugin.api import plugin_hook_specs

log = logging.getLogger(__name__)


class LoadExternalPlugins:
    def __init__(self, plugin_loading_mode: ExternalPluginsLoadingMode):
        plugin_manager = pluggy.PluginManager("snowcli.plugin")
        plugin_manager.add_hookspecs(plugin_hook_specs)
        self._plugin_manager = plugin_manager
        self._plugin_loading_mode = plugin_loading_mode
        self._enabled_plugins = cli_config.get_enabled_plugins()

    def __call__(self, *args, **kwargs) -> List[ExternalLoadedPlugin]:
        self._load_plugins_code_to_manager()
        return self._extract_info_and_specifications_of_loaded_plugins()

    def _load_plugins_code_to_manager(self) -> None:
        {
            ExternalPluginsLoadingMode.ALL_INSTALLED_EXTERNAL_PLUGINS: lambda: self._load_code_of_all_installed_plugins(),
            ExternalPluginsLoadingMode.ONLY_ENABLED_EXTERNAL_PLUGINS: lambda: self._load_code_of_enabled_plugins(),
        }[self._plugin_loading_mode]()

    def _load_code_of_all_installed_plugins(self) -> None:
        self._plugin_manager.load_setuptools_entrypoints(group="snowcli.plugin")

    def _load_code_of_enabled_plugins(self) -> None:
        for plugin_name in self._enabled_plugins:
            try:
                self._plugin_manager.load_setuptools_entrypoints(
                    group="snowcli.plugin", name=plugin_name
                )
            except Exception as ex:
                log.error(
                    msg=f"Cannot load code of enabled external plugin [{plugin_name}]: {ex.__str__()}",
                    exc_info=global_context_copy().debug,
                )

    def _extract_info_and_specifications_of_loaded_plugins(
        self,
    ) -> List[ExternalLoadedPlugin]:
        plugins_to_package_info = {
            plugin: self._extract_package_info(distinfo)
            for (plugin, distinfo) in self._plugin_manager.list_plugin_distinfo()
        }
        plugins = []
        for (plugin_name, plugin) in self._plugin_manager.list_name_plugin():
            try:
                plugins.append(
                    ExternalLoadedPlugin(
                        plugin_name=plugin_name,
                        is_enabled=plugin_name in self._enabled_plugins,
                        plugin_package_info=plugins_to_package_info[plugin],
                        plugin_spec=plugin.plugin_spec(),
                    )
                )
            except Exception as ex:
                log.error(
                    msg=f"Cannot load info about external plugin [{plugin_name}]: {ex.__str__()}",
                    exc_info=global_context_copy().debug,
                )
        return plugins

    @staticmethod
    def _extract_package_info(distinfo) -> ExternalPluginPackageInfo:
        dependencies = distinfo.__getattr__("requires")
        return ExternalPluginPackageInfo(
            package_name=distinfo.__getattr__("name"),
            package_version=distinfo.__getattr__("version"),
            dependencies=dependencies,
        )
