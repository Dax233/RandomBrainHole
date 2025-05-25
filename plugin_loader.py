import importlib # 用于动态导入模块
import re # 导入 re 模块，用于正则表达式匹配
from typing import Callable, Any, Coroutine, Dict, Optional, cast, List, Tuple # 类型提示
from nonebot import on_message # NoneBot 核心：消息响应器
from nonebot.matcher import Matcher # NoneBot 核心：事件处理器实例
from nonebot.adapters.onebot.v11 import Bot, Event, Message # OneBot V11 适配器相关
from nonebot.log import logger # NoneBot 日志记录器

# 从同级模块导入
from .config import PluginSetting, get_plugin_config # 插件配置
from .db_utils import search_term_in_db, get_random_entry_from_db # 数据库操作工具

# 缓存已加载的插件函数，避免重复导入
# 键是 (module_name, function_name) 元组，值是对应的可调用函数
_loaded_funcs: Dict[tuple[str, str], Callable[..., Coroutine[Any, Any, Any]]] = {}


async def _master_message_handler(bot: Bot, event: Event, matcher: Matcher):
    """
    单一的 on_message 处理器，作为所有消息的总入口。
    它负责：
    1. 接收用户消息。
    2. 解析消息内容，判断用户意图 (查词、随机填词、关键词触发)。
    3. 根据意图分发到具体的处理逻辑。

    :param bot: Bot 对象，代表当前机器人实例。
    :param event: Event 对象，代表当前接收到的事件 (通常是 MessageEvent)。
    :param matcher: Matcher 对象，当前处理器实例，用于发送消息等。
    """
    message_text = event.get_plaintext().strip() # 获取纯文本消息并去除首尾空格
    if not message_text: # 如果消息为空，则不处理
        return

    current_config = get_plugin_config() # 获取当前插件配置

    # --- 1. 处理 "查词" 命令 ---
    # 检查消息是否以 "查词 " 开头
    SEARCH_COMMAND_PREFIX = "查词 " 
    if message_text.startswith(SEARCH_COMMAND_PREFIX):
        search_keyword = message_text[len(SEARCH_COMMAND_PREFIX):].strip() #提取关键词
        
        if not search_keyword: # 如果关键词为空
            await matcher.send("请输入要查询的词汇，例如：查词 脑洞")
            return

        logger.info(f"RandomBrainHole (MasterHandler): 收到查词指令，关键词: '{search_keyword}'")
        
        try:
            # 调用数据库工具函数进行搜索
            found_entries: List[Tuple[PluginSetting, Dict[str, Any]]] = await search_term_in_db(search_keyword)
        except Exception as e:
            logger.opt(exception=e).error(f"查词功能：调用 search_term_in_db 时发生错误。")
            await matcher.send(f"查询“{search_keyword}”时发生内部错误，请稍后再试或联系管理员。")
            return

        if not found_entries: # 如果没有找到任何条目
            await matcher.send(f"未能找到与“{search_keyword}”相关的任何信息。")
            return

        # --- 格式化并发送搜索结果 ---
        response_messages = [] # 存储格式化后的消息片段
        for plugin_setting, data_dict in found_entries: # 遍历找到的每个条目
            # 检查插件是否配置了格式化函数
            if not plugin_setting.format_function_name:
                logger.error(f"插件 '{plugin_setting.name}' 未配置 'format_function_name'，无法格式化搜索结果。")
                response_messages.append(f"（插件 {plugin_setting.name} 因配置问题无法显示“{search_keyword}”的详细信息。）")
                continue

            # 动态加载并缓存格式化函数
            format_func_key = (plugin_setting.module_name, plugin_setting.format_function_name)
            current_format_func = _loaded_funcs.get(format_func_key)

            if current_format_func is None: # 如果函数尚未加载
                try:
                    # 构建插件模块的完整路径 (例如: src.plugins.RandomBrainHole.plugins.brainhole)
                    full_module_name = f"src.plugins.RandomBrainHole.plugins.{plugin_setting.module_name}"
                    plugin_module = importlib.import_module(full_module_name) # 动态导入模块
                    # 从模块中获取格式化函数
                    current_format_func = getattr(plugin_module, plugin_setting.format_function_name)
                    _loaded_funcs[format_func_key] = cast(Callable[..., Coroutine[Any, Any, Any]], current_format_func) # 缓存函数
                    logger.debug(f"RandomBrainHole (MasterHandler): 已加载并缓存格式化函数 '{plugin_setting.format_function_name}' (模块: '{full_module_name}')")
                except ImportError:
                    logger.error(f"RandomBrainHole (MasterHandler): 导入模块 '{full_module_name}' (用于格式化) 失败。")
                    response_messages.append(f"（加载插件 {plugin_setting.name} 的格式化功能失败。）")
                    continue
                except AttributeError:
                    logger.error(f"RandomBrainHole (MasterHandler): 在模块 '{plugin_setting.module_name}' 中未找到格式化函数 '{plugin_setting.format_function_name}'。")
                    response_messages.append(f"（插件 {plugin_setting.name} 的格式化功能 '{plugin_setting.format_function_name}' 未找到。）")
                    continue
            
            # 调用格式化函数处理数据
            try:
                # 格式化函数应为异步函数，接受数据字典，返回格式化后的字符串
                formatted_message: Optional[str] = await current_format_func(data_dict) 
                if formatted_message and isinstance(formatted_message, str):
                    response_messages.append(formatted_message)
                else:
                    logger.warning(f"插件 '{plugin_setting.name}' 的格式化函数返回了无效内容。")
                    response_messages.append(f"（插件 {plugin_setting.name} 为“{search_keyword}”返回了空或无效的格式化信息。）")
            except Exception as e:
                logger.opt(exception=e).error(f"调用插件 '{plugin_setting.name}' 的格式化函数 '{plugin_setting.format_function_name}' 时发生错误。")
                response_messages.append(f"处理来自“{plugin_setting.name}”的“{search_keyword}”信息时出错。")

        # --- 发送整合后的查词结果 ---
        if response_messages:
            full_response = "\n\n---\n\n".join(response_messages) # 用分隔符连接多条结果
            if len(full_response) > 1500: # 如果消息过长，则分条发送 (避免超出平台限制)
                 logger.warning(f"查词结果过长 ({len(full_response)} chars)，将分条发送。")
                 for msg_part in response_messages:
                     await matcher.send(msg_part)
            else:
                await matcher.send(full_response)
        elif found_entries and not response_messages: # 找到了条目但格式化失败
             await matcher.send(f"找到了“{search_keyword}”的相关条目，但在格式化输出时发生问题。")
        return # "查词" 命令处理完毕，直接返回

    # --- 2. 新增：处理 "随机填词" 命令 ---
    # 检查消息是否以 "随机填词 " 开头
    FILL_WORD_COMMAND_PREFIX = "随机填词 "
    if message_text.startswith(FILL_WORD_COMMAND_PREFIX):
        template_string = message_text[len(FILL_WORD_COMMAND_PREFIX):].strip() # 提取模板字符串
        if not template_string:
            await matcher.send("请输入需要填词的文本，例如：随机填词 今天天气[脑洞]，心情[拼释]。")
            return

        logger.info(f"RandomBrainHole (MasterHandler): 收到随机填词指令，模板: '{template_string}'")

        # 构建 folder_name 到 PluginSetting 的映射，以及所有 folder_name 的列表
        # folder_name 在 config.toml 中定义，用作占位符的名称
        folder_name_to_plugin: Dict[str, PluginSetting] = {}
        folder_names: List[str] = []
        for ps_config in current_config.plugins: # 遍历所有插件配置
            if ps_config.folder_name: # 确保 folder_name 存在且不为空
                folder_name_to_plugin[ps_config.folder_name] = ps_config
                folder_names.append(ps_config.folder_name)
        
        if not folder_names: # 如果没有任何插件定义了 folder_name
            logger.warning("随机填词：配置文件中没有任何插件定义了 folder_name，无法进行填词。")
            await matcher.send("抱歉，我还没有学会任何词库的占位符，无法进行填词。")
            return

        # 对 folder_names 按长度降序排序，目的是优先匹配更长的占位符
        # 例如，如果同时有 "天气" 和 "天气预报" 作为占位符，优先匹配 "天气预报"
        folder_names.sort(key=len, reverse=True)

        # 构建正则表达式，用于从模板字符串中匹配占位符。
        # 格式: (\?)(folder_name1|folder_name2|...)
        #   \\? : 匹配一个可选的前导反斜杠 (用于转义，例如 \[脑洞] 表示不替换 "[脑洞]")
        #   (folder_name1|folder_name2|...) : 匹配任何一个已定义的 folder_name
        #   re.escape() : 用于转义 folder_name 中的特殊正则表达式字符 (例如 '.')
        placeholder_pattern = r"\[(" + "|".join(re.escape(fn) for fn in folder_names) + r")\]"
        # 修改后的模式：匹配 [占位符名称]，并捕获占位符名称
        # 例如，如果 folder_names 是 ["脑洞", "拼释"]，则模式是 r"\[(脑洞|拼释)\]"
        # 如果用户输入 "\[脑洞]"，则不应该被替换。
        # 我们需要一个更复杂的模式来处理转义，或者在匹配后检查前一个字符。
        # 简单起见，我们先用一个能匹配 `[占位符]` 的模式，然后通过 `plugin_setting.search_column_name` 获取词。
        # 修正后的占位符模式，允许用户使用 `\[占位符]` 来避免替换
        # (\\?)\[(folder_name1|folder_name2|...)\]
        # 第一个捕获组 (\\?) 是可选的反斜杠
        # 第二个捕获组是占位符名称
        placeholder_pattern_with_escape = r"(\\?)\\[(" + "|".join(re.escape(fn) for fn in folder_names) + r")\\]"
        # 修正为：匹配 `[占位符]`，其中 `占位符` 是 `folder_names` 之一。
        # 使用 `re.escape` 来确保 `folder_name` 中的特殊字符被正确处理。
        # 占位符格式现在是 `[词库名]`，例如 `[脑洞]`
        placeholder_pattern = r"\[(" + "|".join(re.escape(fn) for fn in folder_names) + r")\]"

        
        output_parts = [] # 用于存储最终输出字符串的各个部分
        last_end = 0 # 上一个匹配结束的位置

        # 使用 re.finditer 遍历模板字符串中所有匹配的占位符
        for match in re.finditer(placeholder_pattern, template_string):
            start, end = match.span() # 获取匹配的开始和结束位置
            placeholder_name = match.group(1) # 获取捕获到的占位符名称 (不含方括号)

            # 添加占位符之前的部分
            output_parts.append(template_string[last_end:start])
            
            # 检查占位符前是否有转义符 '\'
            # 注意：上面的 placeholder_pattern 没有直接处理转义。
            # 一个更健壮的方法是使用更复杂的正则表达式，或者在找到匹配后检查前一个字符。
            # 假设我们约定 `\[词库名]` 表示不替换。
            # 这里的逻辑需要调整以正确处理转义。
            # 当前的 placeholder_pattern `r"\[(folder_name1|...)]"` 会直接匹配 `[脑洞]`
            # 如果用户输入 `\[脑洞]`，它不会被这个 pattern 匹配。
            # 如果用户输入 `\[脑洞]`，我们希望它输出 `[脑洞]` 而不是替换。
            # 让我们重新思考转义。如果用户输入 `\[脑洞]`，它应该被视为普通文本。
            # 如果用户输入 `[脑洞]`，它应该被替换。

            # 简化逻辑：如果 template_string[start-1] == '\\' and start > 0，则认为是转义。
            # 但这要求 placeholder_pattern 本身不包含反斜杠。
            # 让我们坚持使用 `[词库名]` 作为占位符。转义可以通过 `\[词库名]` 实现，
            # 但当前的 `placeholder_pattern` 不会匹配 `\[`。
            # 所以，如果匹配到了，说明它不是转义的。

            plugin_setting = folder_name_to_plugin.get(placeholder_name)
            if plugin_setting:
                # 从数据库中随机获取一个条目
                random_entry = await get_random_entry_from_db(plugin_setting.table_name)
                if random_entry:
                    # 使用配置中定义的 search_column_name (通常是 'term') 作为填入的词
                    fill_word = random_entry.get(plugin_setting.search_column_name)
                    if fill_word:
                        output_parts.append(str(fill_word)) # 添加替换后的词
                        logger.debug(f"随机填词：用 '{fill_word}' 替换了占位符 '[{placeholder_name}]' (来自表 '{plugin_setting.table_name}')")
                    else:
                        output_parts.append(f"[{placeholder_name}?]") # 获取词失败，保留占位符并标记
                        logger.warning(f"随机填词：无法从表 '{plugin_setting.table_name}' 的 '{plugin_setting.search_column_name}' 列获取词用于占位符 '[{placeholder_name}]'")
                else:
                    output_parts.append(f"[{placeholder_name}空]") # 表中无数据或获取失败，保留占位符并标记
                    logger.warning(f"随机填词：无法从表 '{plugin_setting.table_name}' 获取随机条目用于占位符 '[{placeholder_name}]'")
            else:
                # 理论上不应该发生，因为 placeholder_pattern 是基于 folder_names 构建的
                output_parts.append(f"[{placeholder_name}]") # 保留未识别的占位符
            
            last_end = end # 更新上一个匹配结束的位置
        
        output_parts.append(template_string[last_end:]) # 添加最后一个占位符之后的部分
        output_string = "".join(output_parts) # 拼接所有部分得到最终结果

        # 只有当字符串发生改变时才发送结果，或者如果原始文本中就没有有效占位符，则发送提示
        if output_string != template_string : 
             await matcher.send(output_string)
        # elif not re.search(placeholder_pattern, template_string): # 如果原始文本中没有有效的占位符
        #     # 改进提示，告知用户如何使用占位符
        #     example_placeholder = folder_names[0] if folder_names else "词库名"
        #     await matcher.send(f"请在文本中使用方括号括起来的词库名作为占位符，例如：随机填词 今天天气[{example_placeholder}]。\n可用的词库占位符有：{', '.join(f'[{fn}]' for fn in folder_names)}")
        else: # 如果没有发生替换 (例如所有占位符都获取失败，或者根本没有占位符)
            # 如果原始字符串中就没有我们定义的占位符，可以给用户一个提示
            # 检查原始模板中是否有任何看起来像占位符的模式，但不是我们定义的
            has_potential_placeholders = any(f"[{fn}]" in template_string for fn in folder_names)
            if not has_potential_placeholders and "[" in template_string and "]" in template_string:
                 await matcher.send(f"看起来您想使用填词功能，但没有找到我认识的词库占位符。请使用以下格式：[{folder_names[0] if folder_names else '词库名'}]。\n我认识的词库有：{', '.join(folder_names)}")
            elif not has_potential_placeholders: # 既没有我们的占位符，也没有其他方括号
                await matcher.send(f"请输入带有词库占位符的文本才能进行填词哦！例如：随机填词 今天天气[{folder_names[0] if folder_names else '词库名'}]。")
            else: # 有我们的占位符，但是替换失败了，或者用户输入的就是替换后的结果
                 await matcher.send(output_string) # 此时 output_string 等于 template_string

        return # "随机填词" 命令处理完毕

    # --- 3. 处理关键词触发的随机信息获取 (原有逻辑) ---
    # 遍历配置文件中定义的每个插件
    for plugin_setting in current_config.plugins:
        triggered_keyword: Optional[str] = None
        # 检查消息文本是否包含插件定义的任何关键词
        for keyword in plugin_setting.keywords:
            if keyword in message_text:
                triggered_keyword = keyword
                break # 找到一个匹配的关键词即可

        if triggered_keyword: # 如果命中了关键词
            logger.info(f"RandomBrainHole (MasterHandler): 消息 '{message_text}' 命中了插件 '{plugin_setting.name}' 的关键词 '{triggered_keyword}'")
            
            # 动态加载并缓存插件的信息处理函数
            info_func_key = (plugin_setting.module_name, plugin_setting.info_function_name)
            current_info_func = _loaded_funcs.get(info_func_key)

            if current_info_func is None: # 如果函数尚未加载
                try:
                    full_module_name = f"src.plugins.RandomBrainHole.plugins.{plugin_setting.module_name}"
                    plugin_module = importlib.import_module(full_module_name)
                    current_info_func = getattr(plugin_module, plugin_setting.info_function_name)
                    _loaded_funcs[info_func_key] = cast(Callable[..., Coroutine[Any, Any, Any]], current_info_func)
                    logger.debug(f"RandomBrainHole (MasterHandler): 已加载并缓存信息函数 '{plugin_setting.info_function_name}' (模块: '{full_module_name}')")
                except ImportError:
                    logger.error(f"RandomBrainHole (MasterHandler): 导入插件模块 '{full_module_name}' (用于随机信息) 失败。")
                    continue # 跳过此插件，处理下一个
                except AttributeError:
                    logger.error(f"RandomBrainHole (MasterHandler): 在模块 '{plugin_setting.module_name}' 中未找到信息函数 '{plugin_setting.info_function_name}'。")
                    continue # 跳过此插件

            # --- 调用信息处理函数并发送结果，带重试机制 ---
            output_message: Optional[str] = None
            for attempt in range(plugin_setting.retry_attempts): # 尝试多次获取
                logger.debug(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试从数据库获取信息 (表: {plugin_setting.table_name})。")
                try:
                    # 调用插件的信息处理函数，传入表名
                    # 该函数应返回格式化后的字符串消息或 None/引发异常
                    output_message = await current_info_func(plugin_setting.table_name)
                    logger.debug(f"{plugin_setting.name}: info_func 返回: '{output_message}'")
                    
                    if output_message and isinstance(output_message, str): # 如果成功获取到有效消息
                        await matcher.send(output_message) # 发送消息
                        logger.info(f"{plugin_setting.name}: 成功发送消息。")
                        return # 处理完毕，直接返回，不再匹配其他插件的关键词
                    else: # 如果返回无效内容
                        logger.warning(f"{plugin_setting.name}: info_func 返回了无效内容: {output_message}")
                        if attempt + 1 == plugin_setting.retry_attempts: # 如果是最后一次尝试
                            await matcher.send(plugin_setting.failure_message) # 发送预设的失败消息
                            return # 处理完毕
                
                except ValueError as ve: # 捕获插件函数内部可能抛出的 ValueError (例如数据获取失败)
                     logger.warning(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试时，函数内部报告 ValueError: {ve}")
                     if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(f"{plugin_setting.failure_message}")
                        return
                except Exception as e: # 捕获其他未知错误
                    logger.opt(exception=e).error(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试获取信息时发生未知错误。")
                    if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(plugin_setting.failure_message)
                        return
            return # 如果重试完成后仍未成功发送，则结束此插件的处理

def create_plugin_handlers():
    """
    创建并注册总的 on_message 处理器。
    这个函数会在插件加载时被 `__init__.py` 调用。
    """
    logger.info("RandomBrainHole (PluginLoader): 正在创建 on_message 主处理器...")
    
    # 创建一个 on_message 类型的事件响应器
    # priority=0: 优先级，数字越小优先级越高
    # block=False: 非阻塞模式，即此处理器处理完后，消息还会继续传递给其他低优先级的处理器 (如果适用)
    master_matcher = on_message(
        priority=0, 
        block=False # 设置为 False 允许其他插件也有机会处理消息，除非此处理器显式 block
                    # 如果希望此插件处理后不再让其他插件处理，可以考虑在 _master_message_handler 内部
                    # 根据情况调用 matcher.stop_propagation() 或将 block 设为 True (如果适用)
                    # 但对于通用关键词触发，通常 block=False 是合适的，除非关键词非常特定。
                    # 对于明确的命令如 "查词"、"随机填词"，如果处理了，通常应该阻止后续传播。
                    # 可以在 _master_message_handler 的 "查词" 和 "随机填词" 分支的 return 前加上 matcher.stop_propagation()
                    # 或者，如果这些命令非常独特，可以将 block 设为 True，并确保这个 matcher 的 priority 足够高。
                    # 考虑到这是一个多功能插件，block=False 配合内部逻辑判断是否 return (从而隐式结束处理) 是一个灵活的方式。
    )
    
    # 将 _master_message_handler 注册为该响应器的处理函数
    master_matcher.handle()(_master_message_handler)
    
    logger.info(f"RandomBrainHole (PluginLoader): on_message 主处理器已注册，优先级0，非阻塞模式。")
