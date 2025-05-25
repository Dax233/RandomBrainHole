import os
import random
import importlib
from pathlib import Path
from typing import Callable, Any, Coroutine
from nonebot import on_keyword
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Bot, Event # 假设使用 OneBot V11
from nonebot.log import logger

from .config import PluginSetting, get_plugin_config # 从 .config 导入

def create_plugin_handlers():
    """
    根据配置动态创建和注册所有插件的事件处理器。
    """
    try:
        config = get_plugin_config()
    except Exception as e:
        logger.opt(exception=e).critical("RandomBrainHole: plugin_loader 无法获取配置，处理器创建中止。")
        return

    if not config.plugins:
        logger.warning("RandomBrainHole: 未在配置文件中找到任何插件配置。")
        return

    for plugin_setting in config.plugins:
        try:
            # 动态导入插件模块中的处理函数
            # 模块路径相对于 RandomBrainHole.plugins 文件夹
            # 例如 RandomBrainHole.plugins.brainhole
            full_module_name = f"RandomBrainHole.plugins.{plugin_setting.module_name}"
            plugin_module = importlib.import_module(full_module_name)
            
            info_func: Callable[[str], str] = getattr(plugin_module, plugin_setting.info_function_name)

            # 创建关键词匹配器
            # 使用 frozenset 以确保哈希一致性，set 也可以
            matcher_instance = on_keyword(set(plugin_setting.keywords), priority=10, block=True)

            # 定义通用的事件处理函数
            # 使用默认参数来捕获循环变量 (plugin_setting, info_func)
            async def _handler(bot: Bot, event: Event, current_plugin_setting: PluginSetting = plugin_setting, current_info_func: Callable[[str], str] = info_func):
                """
                通用的事件处理逻辑。
                """
                # 重新获取配置，以防 base_data_path 在运行时可能被修改（虽然不太可能）
                # 或者直接使用启动时加载的 config.base_data_path
                current_config = get_plugin_config() # 确保获取最新的配置实例
                base_path_str = current_config.base_data_path if current_config.base_data_path else ""
                
                data_folder_path_str = current_plugin_setting.folder_name
                
                # 确定数据文件夹的绝对路径
                if Path(data_folder_path_str).is_absolute():
                    data_folder_path = Path(data_folder_path_str)
                elif base_path_str and base_path_str != "your/base/data/path/": # 确保 base_data_path 已配置
                    data_folder_path = Path(base_path_str) / data_folder_path_str
                else:
                    logger.error(f"{current_plugin_setting.name}: base_data_path ('{base_path_str}') 未在 config.toml 中正确配置，或 folder_name ('{data_folder_path_str}') 不是绝对路径。无法确定数据文件夹。")
                    await matcher_instance.finish(f"{current_plugin_setting.name} 插件数据路径配置不明确，请检查 config.toml 中的 base_data_path。")
                    return

                if not data_folder_path.exists() or not data_folder_path.is_dir():
                    logger.error(f"{current_plugin_setting.name}: 数据文件夹 {data_folder_path} 不存在或不是一个目录。")
                    await matcher_instance.send(f"{current_plugin_setting.name} 的数据文件夹 '{data_folder_path}' 未找到，请检查配置。")
                    return

                valid_files = []
                for ext in current_plugin_setting.file_extensions:
                    valid_files.extend(list(data_folder_path.glob(f"*{ext}"))) # 使用 glob 查找文件

                if not valid_files:
                    logger.warning(f"{current_plugin_setting.name}: 在 {data_folder_path} 中未找到任何具有扩展名 {current_plugin_setting.file_extensions} 的文件。")
                    await matcher_instance.send(f"{current_plugin_setting.name} 的数据文件库是空的哦~ (路径: {data_folder_path})")
                    return

                selected_file_path = str(random.choice(valid_files))
                logger.debug(f"{current_plugin_setting.name}: 选定的文件: {selected_file_path}")

                for attempt in range(current_plugin_setting.retry_attempts):
                    try:
                        output_message = current_info_func(selected_file_path)
                        await matcher_instance.send(output_message)
                        return # 成功则返回
                    except Exception as e:
                        logger.error(f"{current_plugin_setting.name}: 第 {attempt + 1}/{current_plugin_setting.retry_attempts} 次尝试从 {selected_file_path} 获取信息失败: {e}", exc_info=True)
                        if attempt + 1 == current_plugin_setting.retry_attempts:
                            await matcher_instance.send(current_plugin_setting.failure_message)
                            return
            
            # 将处理函数注册到匹配器
            matcher_instance.handle()(_handler)
            logger.info(f"RandomBrainHole: 已为插件 '{plugin_setting.name}' (关键词: {plugin_setting.keywords}) 注册处理器。")

        except ImportError as e:
            logger.error(f"RandomBrainHole: 导入插件模块 '{full_module_name}' 失败: {e}。请确保模块存在且路径正确，并且 RandomBrainHole 在 Python 路径中。")
        except AttributeError as e:
            logger.error(f"RandomBrainHole: 在模块 '{plugin_setting.module_name}' 中未找到函数 '{plugin_setting.info_function_name}': {e}。")
        except Exception as e:
            logger.opt(exception=e).error(f"RandomBrainHole: 为插件 '{plugin_setting.name}' 设置处理器时发生未知错误。")

