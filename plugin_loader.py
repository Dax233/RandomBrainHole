import importlib
from typing import Callable, Any, Coroutine, Dict, Optional, cast
from nonebot import on_message 
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Bot, Event, Message 
from nonebot.log import logger

from .config import PluginSetting, get_plugin_config
from .db_utils import search_term_in_db # 导入新的搜索函数

# 缓存已加载的函数，键是元组 (module_name, function_name)，值是实际的函数对象
# 函数可以是随机信息获取函数，也可以是特定词条格式化函数
# 类型提示调整为更通用，以适应不同签名的函数
_loaded_funcs: Dict[tuple[str, str], Callable[..., Coroutine[Any, Any, Any]]] = {}


async def _master_message_handler(bot: Bot, event: Event, matcher: Matcher):
    """
    单一的 on_message 处理器，负责接收消息并分发到具体的插件逻辑，
    包括新的“查词”功能和原有的关键词触发功能。
    """
    message_text = event.get_plaintext().strip()
    if not message_text:
        return

    current_config = get_plugin_config()

    # --- 1. 处理 "查词" 命令 ---
    SEARCH_COMMAND_PREFIX = "查词 " # 定义查词指令前缀
    if message_text.startswith(SEARCH_COMMAND_PREFIX):
        search_keyword = message_text[len(SEARCH_COMMAND_PREFIX):].strip()
        
        if not search_keyword:
            await matcher.send("请输入要查询的词汇，例如：查词 脑洞")
            return

        logger.info(f"RandomBrainHole (MasterHandler): 收到查词指令，关键词: '{search_keyword}'")
        
        try:
            found_entries = await search_term_in_db(search_keyword)
        except Exception as e:
            logger.opt(exception=e).error(f"查词功能：调用 search_term_in_db 时发生错误。")
            await matcher.send(f"查询“{search_keyword}”时发生内部错误，请稍后再试或联系管理员。")
            return

        if not found_entries:
            await matcher.send(f"未能找到与“{search_keyword}”相关的任何信息。")
            return

        response_messages = []
        for plugin_setting, data_dict in found_entries:
            # 动态加载并调用 format_function_name 指定的函数
            # format_function_name 必须在 config.toml 中为每个插件配置
            if not plugin_setting.format_function_name:
                logger.error(f"插件 '{plugin_setting.name}' 未配置 'format_function_name'，无法格式化搜索结果。")
                response_messages.append(f"（插件 {plugin_setting.name} 因配置问题无法显示“{search_keyword}”的详细信息。）")
                continue

            format_func_key = (plugin_setting.module_name, plugin_setting.format_function_name)
            current_format_func = _loaded_funcs.get(format_func_key)

            if current_format_func is None:
                try:
                    full_module_name = f"src.plugins.RandomBrainHole.plugins.{plugin_setting.module_name}"
                    plugin_module = importlib.import_module(full_module_name)
                    current_format_func = getattr(plugin_module, plugin_setting.format_function_name)
                    # 类型转换以帮助静态分析器，实际类型取决于函数定义
                    _loaded_funcs[format_func_key] = cast(Callable[..., Coroutine[Any, Any, Any]], current_format_func)
                    logger.debug(f"RandomBrainHole (MasterHandler): 已加载并缓存格式化函数 '{plugin_setting.format_function_name}' (模块: '{full_module_name}')")
                except ImportError:
                    logger.error(f"RandomBrainHole (MasterHandler): 导入模块 '{full_module_name}' (用于格式化) 失败。")
                    response_messages.append(f"（加载插件 {plugin_setting.name} 的格式化功能失败。）")
                    continue
                except AttributeError:
                    logger.error(f"RandomBrainHole (MasterHandler): 在模块 '{plugin_setting.module_name}' 中未找到格式化函数 '{plugin_setting.format_function_name}'。")
                    response_messages.append(f"（插件 {plugin_setting.name} 的格式化功能 '{plugin_setting.format_function_name}' 未找到。）")
                    continue
            
            try:
                # 假设 format_function_name 对应的函数是异步的，并且接收一个字典参数
                # (word_info: Dict[str, Any]) -> Coroutine[Any, Any, str]
                formatted_message = await current_format_func(data_dict) 
                if formatted_message and isinstance(formatted_message, str):
                    response_messages.append(formatted_message)
                else:
                    logger.warning(f"插件 '{plugin_setting.name}' 的格式化函数返回了无效内容。")
                    response_messages.append(f"（插件 {plugin_setting.name} 为“{search_keyword}”返回了空或无效的格式化信息。）")
            except Exception as e:
                logger.opt(exception=e).error(f"调用插件 '{plugin_setting.name}' 的格式化函数 '{plugin_setting.format_function_name}' 时发生错误。")
                response_messages.append(f"处理来自“{plugin_setting.name}”的“{search_keyword}”信息时出错。")

        if response_messages:
            # 为了避免消息过长，可以考虑分条发送或合并后判断长度
            full_response = "\n\n---\n\n".join(response_messages) # 用分隔符合并消息
            if len(full_response) > 1500: # 示例长度限制，具体根据平台调整
                 logger.warning(f"查词结果过长 ({len(full_response)} chars)，将分条发送。")
                 for msg_part in response_messages: # 分条发送
                     await matcher.send(msg_part)
            else:
                await matcher.send(full_response)
        # else 分支：理论上如果 found_entries 不为空，response_messages 至少会包含错误提示
        # 但为了保险，如果意外地 response_messages 为空但 found_entries 不为空：
        elif found_entries and not response_messages:
             await matcher.send(f"找到了“{search_keyword}”的相关条目，但在格式化输出时发生问题。")

        return # "查词" 命令处理完毕，结束

    # --- 2. 处理关键词触发的随机信息获取 (原有逻辑) ---
    for plugin_setting in current_config.plugins:
        triggered_keyword: Optional[str] = None
        for keyword in plugin_setting.keywords:
            if keyword in message_text:
                triggered_keyword = keyword
                break 

        if triggered_keyword:
            logger.info(f"RandomBrainHole (MasterHandler): 消息 '{message_text}' 命中了插件 '{plugin_setting.name}' 的关键词 '{triggered_keyword}'")
            
            info_func_key = (plugin_setting.module_name, plugin_setting.info_function_name)
            current_info_func = _loaded_funcs.get(info_func_key)

            if current_info_func is None:
                try:
                    full_module_name = f"src.plugins.RandomBrainHole.plugins.{plugin_setting.module_name}"
                    plugin_module = importlib.import_module(full_module_name)
                    current_info_func = getattr(plugin_module, plugin_setting.info_function_name)
                    _loaded_funcs[info_func_key] = cast(Callable[..., Coroutine[Any, Any, Any]], current_info_func)
                    logger.debug(f"RandomBrainHole (MasterHandler): 已加载并缓存信息函数 '{plugin_setting.info_function_name}' (模块: '{full_module_name}')")
                except ImportError:
                    logger.error(f"RandomBrainHole (MasterHandler): 导入插件模块 '{full_module_name}' (用于随机信息) 失败。")
                    continue 
                except AttributeError:
                    logger.error(f"RandomBrainHole (MasterHandler): 在模块 '{plugin_setting.module_name}' 中未找到信息函数 '{plugin_setting.info_function_name}'。")
                    continue 

            output_message: Optional[str] = None
            for attempt in range(plugin_setting.retry_attempts):
                logger.debug(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试从数据库获取信息 (表: {plugin_setting.table_name})。")
                try:
                    # 假设 info_function_name 对应的函数是异步的，并且接收一个字符串参数 (table_name)
                    # (table_name: str) -> Coroutine[Any, Any, str]
                    output_message = await current_info_func(plugin_setting.table_name)
                    logger.debug(f"{plugin_setting.name}: info_func 返回: '{output_message}'")
                    
                    if output_message and isinstance(output_message, str):
                        await matcher.send(output_message)
                        logger.info(f"{plugin_setting.name}: 成功发送消息。")
                        return 
                    else:
                        logger.warning(f"{plugin_setting.name}: info_func 返回了无效内容: {output_message}")
                        if attempt + 1 == plugin_setting.retry_attempts:
                            await matcher.send(plugin_setting.failure_message)
                            return
                
                except ValueError as ve: # 函数内部通过 raise ValueError 指示数据获取问题
                     logger.warning(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试时，函数内部报告 ValueError: {ve}")
                     if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(f"{plugin_setting.failure_message}") # 使用插件配置的失败消息
                        return
                except Exception as e:
                    logger.opt(exception=e).error(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试获取信息时发生未知错误。")
                    if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(plugin_setting.failure_message)
                        return
            return # 处理完一个匹配的插件后结束

def create_plugin_handlers():
    """
    创建并注册总的 on_message 处理器。
    """
    logger.info("RandomBrainHole (PluginLoader): 正在创建 on_message 主处理器...")
    
    master_matcher = on_message(
        priority=0, 
        block=False # 保持 False，让内部逻辑通过 return 控制是否继续传播
    )
    
    master_matcher.handle()(_master_message_handler)
    
    logger.info(f"RandomBrainHole (PluginLoader): on_message 主处理器已注册，优先级0，非阻塞模式。")
