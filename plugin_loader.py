import importlib
import re # 导入 re 模块
from typing import Callable, Any, Coroutine, Dict, Optional, cast, List # 新增 List
from nonebot import on_message 
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Bot, Event, Message 
from nonebot.log import logger

from .config import PluginSetting, get_plugin_config
from .db_utils import search_term_in_db, get_random_entry_from_db # 导入 get_random_entry_from_db

# 缓存已加载的函数
_loaded_funcs: Dict[tuple[str, str], Callable[..., Coroutine[Any, Any, Any]]] = {}


async def _master_message_handler(bot: Bot, event: Event, matcher: Matcher):
    """
    单一的 on_message 处理器，负责接收消息并分发到具体的插件逻辑，
    包括“查词”功能、“随机填词”功能和原有的关键词触发功能。
    """
    message_text = event.get_plaintext().strip()
    if not message_text:
        return

    current_config = get_plugin_config()

    # --- 1. 处理 "查词" 命令 (已有逻辑保持不变) ---
    SEARCH_COMMAND_PREFIX = "查词 "
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
            full_response = "\n\n---\n\n".join(response_messages)
            if len(full_response) > 1500: 
                 logger.warning(f"查词结果过长 ({len(full_response)} chars)，将分条发送。")
                 for msg_part in response_messages:
                     await matcher.send(msg_part)
            else:
                await matcher.send(full_response)
        elif found_entries and not response_messages:
             await matcher.send(f"找到了“{search_keyword}”的相关条目，但在格式化输出时发生问题。")
        return

    # --- 2. 新增：处理 "随机填词" 命令 ---
    FILL_WORD_COMMAND_PREFIX = "随机填词 "
    if message_text.startswith(FILL_WORD_COMMAND_PREFIX):
        template_string = message_text[len(FILL_WORD_COMMAND_PREFIX):].strip()
        if not template_string:
            await matcher.send("请输入需要填词的文本，例如：随机填词 今天天气[脑洞]，心情[拼释]。")
            return

        logger.info(f"RandomBrainHole (MasterHandler): 收到随机填词指令，模板: '{template_string}'")

        # 构建 folder_name 到 PluginSetting 的映射，并获取 folder_name 列表
        folder_name_to_plugin: Dict[str, PluginSetting] = {}
        folder_names: List[str] = []
        for ps in current_config.plugins:
            if ps.folder_name: # 确保 folder_name 存在
                folder_name_to_plugin[ps.folder_name] = ps
                folder_names.append(ps.folder_name)
        
        if not folder_names:
            logger.warning("随机填词：配置文件中没有任何插件定义了 folder_name，无法进行填词。")
            await matcher.send("抱歉，我还没有学会任何词库的占位符，无法进行填词。")
            return

        # 对 folder_names 按长度降序排序，以优先匹配更长的占位符
        folder_names.sort(key=len, reverse=True)

        # 构建正则表达式，匹配 (\?)(folder_name1|folder_name2|...)
        # \? 匹配可选的前导反斜杠 (转义符)
        # (folder_name1|folder_name2|...) 匹配任何一个 folder_name
        # re.escape 用于转义 folder_name 中的特殊正则字符
        placeholder_pattern = r"(\\?)(" + "|".join(re.escape(fn) for fn in folder_names) + r")"
        
        output_string = template_string
        parts = []
        last_end = 0

        for match in re.finditer(placeholder_pattern, template_string):
            start, end = match.span()
            parts.append(template_string[last_end:start]) # 添加匹配前的部分

            escaped_char, placeholder_name = match.groups()

            if escaped_char: # 如果有转义符 '\'
                parts.append(placeholder_name) # 直接添加 folder_name，去除转义符
                logger.debug(f"随机填词：跳过转义的占位符 '{placeholder_name}'")
            else:
                plugin_setting = folder_name_to_plugin.get(placeholder_name)
                if plugin_setting:
                    random_entry = await get_random_entry_from_db(plugin_setting.table_name)
                    if random_entry:
                        # 使用 search_column_name (通常是 'term') 作为填入的词
                        fill_word = random_entry.get(plugin_setting.search_column_name)
                        if fill_word:
                            parts.append(str(fill_word))
                            logger.debug(f"随机填词：用 '{fill_word}' 替换了占位符 '{placeholder_name}' (来自表 '{plugin_setting.table_name}')")
                        else:
                            parts.append(f"[{placeholder_name}?]") # 获取词失败，保留并标记
                            logger.warning(f"随机填词：无法从表 '{plugin_setting.table_name}' 的 '{plugin_setting.search_column_name}' 列获取词用于占位符 '{placeholder_name}'")
                    else:
                        parts.append(f"[{placeholder_name}空]") # 表中无数据或获取失败
                        logger.warning(f"随机填词：无法从表 '{plugin_setting.table_name}' 获取随机条目用于占位符 '{placeholder_name}'")
                else:
                    #理论上不会发生，因为 pattern 是基于 folder_names 构建的
                    parts.append(placeholder_name) 
            last_end = end
        
        parts.append(template_string[last_end:]) # 添加最后一部分
        output_string = "".join(parts)

        if output_string != template_string : # 仅当发生替换时发送
             await matcher.send(output_string)
        elif not re.search(placeholder_pattern, template_string.replace("\\","")): # 如果原始文本中没有有效的占位符（排除已转义的）
            await matcher.send(f"请在文本中使用词库的占位符（例如 {folder_names[0]}）来进行填词，如：随机填词 今天天气真{folder_names[0]}。\n使用 \\{folder_names[0]} 可以避免替换。")
        else: # 有占位符但都被转义了，或者替换失败了
            await matcher.send(output_string) # 发送处理转义后的结果

        return # "随机填词" 命令处理完毕

    # --- 3. 处理关键词触发的随机信息获取 (原有逻辑) ---
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
                
                except ValueError as ve: 
                     logger.warning(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试时，函数内部报告 ValueError: {ve}")
                     if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(f"{plugin_setting.failure_message}")
                        return
                except Exception as e:
                    logger.opt(exception=e).error(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试获取信息时发生未知错误。")
                    if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(plugin_setting.failure_message)
                        return
            return 

def create_plugin_handlers():
    """
    创建并注册总的 on_message 处理器。
    """
    logger.info("RandomBrainHole (PluginLoader): 正在创建 on_message 主处理器...")
    
    master_matcher = on_message(
        priority=0, 
        block=False 
    )
    
    master_matcher.handle()(_master_message_handler)
    
    logger.info(f"RandomBrainHole (PluginLoader): on_message 主处理器已注册，优先级0，非阻塞模式。")
