import importlib
from typing import Callable, Any, Coroutine 
from nonebot import on_keyword
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Bot, Event # 假设使用 OneBot V11
from nonebot.log import logger

from .config import PluginSetting, get_plugin_config # 从 .config 导入

def create_plugin_handlers():
    """根据配置动态创建和注册所有插件的事件处理器。"""
    try:
        config = get_plugin_config()
    except Exception as e:
        logger.opt(exception=e).critical("RandomBrainHole (PluginLoader): 无法获取配置，处理器创建中止。")
        return

    if not config.plugins:
        logger.warning("RandomBrainHole (PluginLoader): 未在配置文件中找到任何插件配置。")
        return

    for plugin_setting in config.plugins:
        try:
            # 动态导入插件模块中的处理函数
            full_module_name = f"src.plugins.RandomBrainHole.plugins.{plugin_setting.module_name}"
            plugin_module = importlib.import_module(full_module_name)
            
            # info_func 现在是一个接收 str (table_name) 并返回协程的函数
            info_func: Callable[[str], Coroutine[Any, Any, str]] = getattr(plugin_module, plugin_setting.info_function_name)

            # 创建关键词匹配器
            matcher_instance = on_keyword(set(plugin_setting.keywords), priority=10, block=True)

            # _handler 现在也需要是 async，因为它 await info_func
            async def _handler(
                bot: Bot, 
                event: Event, 
                current_plugin_setting: PluginSetting = plugin_setting, 
                current_info_func: Callable[[str], Coroutine[Any, Any, str]] = info_func
            ):
                """通用的事件处理逻辑。"""
                logger.debug(f"{current_plugin_setting.name}: 触发关键词，准备从数据库获取信息 (表: {current_plugin_setting.table_name})。")

                for attempt in range(current_plugin_setting.retry_attempts):
                    try:
                        # 调用 info_func 并传入 table_name
                        output_message = await current_info_func(current_plugin_setting.table_name)
                        await matcher_instance.send(output_message)
                        return # 成功则返回
                    except ValueError as ve: # 特别处理 info_func 可能抛出的 ValueError (例如数据库返回空)
                         logger.warning(f"{current_plugin_setting.name}: 第 {attempt + 1}/{current_plugin_setting.retry_attempts} 次尝试获取信息时，函数内部报告问题 (数据库表: {current_plugin_setting.table_name}): {ve}")
                         # 对于 ValueError，通常意味着数据获取或格式化问题，重试可能无用，除非是临时性数据库问题
                         if attempt + 1 == current_plugin_setting.retry_attempts:
                            # 可以发送一个更具体的错误消息，或者仍然使用通用的 failure_message
                            await matcher_instance.send(f"{current_plugin_setting.name}：暂时无法获取信息，请稍后再试。")
                            return
                    except Exception as e: # 其他意外错误
                        logger.opt(exception=e).error(f"{current_plugin_setting.name}: 第 {attempt + 1}/{current_plugin_setting.retry_attempts} 次尝试获取信息失败 (数据库表: {current_plugin_setting.table_name})。")
                        if attempt + 1 == current_plugin_setting.retry_attempts:
                            await matcher_instance.send(current_plugin_setting.failure_message)
                            return
            
            # 将处理函数注册到匹配器
            matcher_instance.handle()(_handler)
            logger.info(f"RandomBrainHole (PluginLoader): 已为插件 '{plugin_setting.name}' (关键词: {plugin_setting.keywords}, 表: {plugin_setting.table_name}) 注册处理器。")

        except ImportError as e:
            logger.error(f"RandomBrainHole (PluginLoader): 导入插件模块 '{full_module_name}' 失败: {e}。")
        except AttributeError as e:
            logger.error(f"RandomBrainHole (PluginLoader): 在模块 '{plugin_setting.module_name}' 中未找到函数 '{plugin_setting.info_function_name}' 或其签名不匹配: {e}。")
        except Exception as e:
            logger.opt(exception=e).error(f"RandomBrainHole (PluginLoader): 为插件 '{plugin_setting.name}' 设置处理器时发生未知错误。")
