import importlib  # 用于动态导入模块
import re  # 导入 re 模块，用于正则表达式匹配
from typing import (
    Callable,
    Any,
    Coroutine,
    Dict,
    Optional,
    cast,
    List,
    Tuple,
)  # 类型提示
from nonebot import on_message  # NoneBot 核心：消息响应器
from nonebot.matcher import Matcher  # NoneBot 核心：事件处理器实例
from nonebot.adapters.onebot.v11 import Bot, Event  # OneBot V11 适配器相关
from nonebot.log import logger  # NoneBot 日志记录器

# 从同级模块导入
from .config import PluginSetting, get_plugin_config  # 插件配置
from .db_utils import search_term_in_db, get_random_entry_from_db  # 数据库操作工具

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
    message_text = event.get_plaintext().strip()  # 获取纯文本消息并去除首尾空格
    if not message_text:  # 如果消息为空，则不处理
        return

    current_config = get_plugin_config()  # 获取当前插件配置

    # --- 1. 处理 "查词" 命令 ---
    # 检查消息是否以 "查词 " 开头
    SEARCH_COMMAND_PREFIX = "查词 "
    if message_text.startswith(SEARCH_COMMAND_PREFIX):
        search_keyword = message_text[
            len(SEARCH_COMMAND_PREFIX) :
        ].strip()  # 提取关键词

        if not search_keyword:  # 如果关键词为空
            await matcher.send("请输入要查询的词汇，例如：查词 脑洞")
            return

        logger.info(
            f"RandomBrainHole (MasterHandler): 收到查词指令，关键词: '{search_keyword}'"
        )

        try:
            # 调用数据库工具函数进行搜索
            found_entries: List[
                Tuple[PluginSetting, Dict[str, Any]]
            ] = await search_term_in_db(search_keyword)
        except Exception as e:
            logger.opt(exception=e).error(
                "查词功能：调用 search_term_in_db 时发生错误。"
            )
            await matcher.send(
                f"查询“{search_keyword}”时发生内部错误，请稍后再试或联系管理员。"
            )
            return

        if not found_entries:  # 如果没有找到任何条目
            await matcher.send(f"未能找到与“{search_keyword}”相关的任何信息。")
            return

        # --- 格式化并发送搜索结果 ---
        response_messages = []  # 存储格式化后的消息片段
        for plugin_setting, data_dict in found_entries:  # 遍历找到的每个条目
            # 检查插件是否配置了格式化函数
            if not plugin_setting.format_function_name:
                logger.error(
                    f"插件 '{plugin_setting.name}' 未配置 'format_function_name'，无法格式化搜索结果。"
                )
                response_messages.append(
                    f"（插件 {plugin_setting.name} 因配置问题无法显示“{search_keyword}”的详细信息。）"
                )
                continue

            # 动态加载并缓存格式化函数
            format_func_key = (
                plugin_setting.module_name,
                plugin_setting.format_function_name,
            )
            current_format_func = _loaded_funcs.get(format_func_key)

            if current_format_func is None:  # 如果函数尚未加载
                try:
                    # 构建插件模块的完整路径 (例如: src.plugins.RandomBrainHole.plugins.brainhole)
                    full_module_name = f"src.plugins.RandomBrainHole.plugins.{plugin_setting.module_name}"
                    plugin_module = importlib.import_module(
                        full_module_name
                    )  # 动态导入模块
                    # 从模块中获取格式化函数
                    current_format_func = getattr(
                        plugin_module, plugin_setting.format_function_name
                    )
                    _loaded_funcs[format_func_key] = cast(
                        Callable[..., Coroutine[Any, Any, Any]], current_format_func
                    )  # 缓存函数
                    logger.debug(
                        f"RandomBrainHole (MasterHandler): 已加载并缓存格式化函数 '{plugin_setting.format_function_name}' (模块: '{full_module_name}')"
                    )
                except ImportError:
                    logger.error(
                        f"RandomBrainHole (MasterHandler): 导入模块 '{full_module_name}' (用于格式化) 失败。"
                    )
                    response_messages.append(
                        f"（加载插件 {plugin_setting.name} 的格式化功能失败。）"
                    )
                    continue
                except AttributeError:
                    logger.error(
                        f"RandomBrainHole (MasterHandler): 在模块 '{plugin_setting.module_name}' 中未找到格式化函数 '{plugin_setting.format_function_name}'。"
                    )
                    response_messages.append(
                        f"（插件 {plugin_setting.name} 的格式化功能 '{plugin_setting.format_function_name}' 未找到。）"
                    )
                    continue

            # 调用格式化函数处理数据
            try:
                # 格式化函数应为异步函数，接受数据字典，返回格式化后的字符串
                formatted_message: Optional[str] = await current_format_func(data_dict)
                if formatted_message and isinstance(formatted_message, str):
                    response_messages.append(formatted_message)
                else:
                    logger.warning(
                        f"插件 '{plugin_setting.name}' 的格式化函数返回了无效内容。"
                    )
                    response_messages.append(
                        f"（插件 {plugin_setting.name} 为“{search_keyword}”返回了空或无效的格式化信息。）"
                    )
            except Exception as e:
                logger.opt(exception=e).error(
                    f"调用插件 '{plugin_setting.name}' 的格式化函数 '{plugin_setting.format_function_name}' 时发生错误。"
                )
                response_messages.append(
                    f"处理来自“{plugin_setting.name}”的“{search_keyword}”信息时出错。"
                )

        # --- 发送整合后的查词结果 ---
        if response_messages:
            full_response = "\n\n---\n\n".join(
                response_messages
            )  # 用分隔符连接多条结果
            if len(full_response) > 1500:  # 如果消息过长，则分条发送 (避免超出平台限制)
                logger.warning(
                    f"查词结果过长 ({len(full_response)} chars)，将分条发送。"
                )
                for msg_part in response_messages:
                    await matcher.send(msg_part)
            else:
                await matcher.send(full_response)
        elif found_entries and not response_messages:  # 找到了条目但格式化失败
            await matcher.send(
                f"找到了“{search_keyword}”的相关条目，但在格式化输出时发生问题。"
            )
        return  # "查词" 命令处理完毕，直接返回

    # --- 2. 处理 "随机填词" 命令 ---
    FILL_WORD_COMMAND_PREFIX = "随机填词 "
    if message_text.startswith(FILL_WORD_COMMAND_PREFIX):
        template_string = message_text[len(FILL_WORD_COMMAND_PREFIX) :].strip()
        if not template_string:
            await matcher.send(
                "请输入需要填词的文本，例如：随机填词 今天天气真脑洞，心情有点\拼释。"
            )  # 更新示例
            return

        logger.info(
            f"RandomBrainHole (MasterHandler): 收到随机填词指令，模板: '{template_string}'"
        )

        folder_name_to_plugin: Dict[str, PluginSetting] = {}
        folder_names: List[str] = []
        for ps_config in current_config.plugins:
            if ps_config.folder_name:
                folder_name_to_plugin[ps_config.folder_name] = ps_config
                folder_names.append(ps_config.folder_name)

        if not folder_names:
            logger.warning(
                "随机填词：配置文件中没有任何插件定义了 folder_name，无法进行填词。"
            )
            await matcher.send("抱歉，我还没有学会任何词库的占位符，无法进行填词。")
            return

        folder_names.sort(key=len, reverse=True)  # 优先匹配更长的 folder_name

        # 新的正则表达式：
        # (\\?) : 捕获组1，匹配一个可选的反斜杠（用于转义）
        # (...) : 捕获组2，匹配任何一个 folder_name
        # re.escape(fn) 确保 folder_name 中的特殊字符被正确转义
        placeholder_pattern = (
            r"(\\?)(" + "|".join(re.escape(fn) for fn in folder_names) + r")"
        )

        output_parts = []
        last_end = 0
        placeholder_found_and_replaced = False  # 标记是否至少替换了一个占位符
        has_valid_placeholder_syntax = (
            False  # 标记模板中是否至少有一个看起来像占位符的语法
        )

        for match in re.finditer(placeholder_pattern, template_string):
            start, end = match.span()
            escaped_char, placeholder_name = (
                match.groups()
            )  # escaped_char 是捕获组1, placeholder_name 是捕获组2
            has_valid_placeholder_syntax = True  # 只要匹配到模式，就认为有占位符语法

            output_parts.append(template_string[last_end:start])  # 添加匹配前的部分

            if escaped_char:  # 如果存在转义符 '\'
                output_parts.append(
                    placeholder_name
                )  # 直接添加 folder_name，去除转义符
                logger.debug(f"随机填词：跳过转义的占位符 '{placeholder_name}'")
            else:  # 没有转义符，是正常的占位符
                plugin_setting = folder_name_to_plugin.get(placeholder_name)
                # plugin_setting 理论上一定能找到，因为 pattern 是基于 folder_names 构建的
                if plugin_setting:
                    random_entry = await get_random_entry_from_db(
                        plugin_setting.table_name
                    )
                    if random_entry:
                        fill_word = random_entry.get(plugin_setting.search_column_name)
                        if fill_word:
                            output_parts.append(str(fill_word))
                            placeholder_found_and_replaced = True  # 成功替换
                            logger.debug(
                                f"随机填词：用 '{fill_word}' 替换了占位符 '{placeholder_name}' (来自表 '{plugin_setting.table_name}')"
                            )
                        else:
                            output_parts.append(
                                placeholder_name + "?"
                            )  # 获取词失败，标记
                            logger.warning(
                                f"随机填词：无法从表 '{plugin_setting.table_name}' 的 '{plugin_setting.search_column_name}' 列获取词用于占位符 '{placeholder_name}'"
                            )
                    else:
                        output_parts.append(placeholder_name + "空")  # 表中无数据，标记
                        logger.warning(
                            f"随机填词：无法从表 '{plugin_setting.table_name}' 获取随机条目用于占位符 '{placeholder_name}'"
                        )
                else:
                    # 理论上不会到这里
                    output_parts.append(placeholder_name)
            last_end = end

        output_parts.append(template_string[last_end:])
        output_string = "".join(output_parts)

        if placeholder_found_and_replaced:  # 如果至少有一个占位符被成功替换
            await matcher.send(output_string)
        elif (
            has_valid_placeholder_syntax and not placeholder_found_and_replaced
        ):  # 有占位符语法，但一个都没成功替换（可能都转义了或都获取失败）
            await matcher.send(output_string)  # 发送处理转义或标记失败后的结果
        else:  # 模板中完全没有匹配到任何定义的 folder_name 作为占位符
            example_placeholder = folder_names[0] if folder_names else "词库名"
            await matcher.send(
                f"请在文本中使用词库名作为占位符，例如：随机填词 今天天气真{example_placeholder}。\n使用 \\{example_placeholder} 可以避免替换。\n我认识的词库占位符有：{', '.join(folder_names)}"
            )
        return  # "随机填词" 命令处理完毕

    # --- 3. 处理关键词触发的随机信息获取 (原有逻辑) ---
    for plugin_setting in current_config.plugins:
        triggered_keyword: Optional[str] = None
        # 检查消息文本是否包含插件定义的任何关键词
        for keyword in plugin_setting.keywords:
            if keyword in message_text:
                triggered_keyword = keyword
                break  # 找到一个匹配的关键词即可

        if triggered_keyword:  # 如果命中了关键词
            logger.info(
                f"RandomBrainHole (MasterHandler): 消息 '{message_text}' 命中了插件 '{plugin_setting.name}' 的关键词 '{triggered_keyword}'"
            )

            # 动态加载并缓存插件的信息处理函数
            info_func_key = (
                plugin_setting.module_name,
                plugin_setting.info_function_name,
            )
            current_info_func = _loaded_funcs.get(info_func_key)

            if current_info_func is None:  # 如果函数尚未加载
                try:
                    full_module_name = f"src.plugins.RandomBrainHole.plugins.{plugin_setting.module_name}"
                    plugin_module = importlib.import_module(full_module_name)
                    current_info_func = getattr(
                        plugin_module, plugin_setting.info_function_name
                    )
                    _loaded_funcs[info_func_key] = cast(
                        Callable[..., Coroutine[Any, Any, Any]], current_info_func
                    )
                    logger.debug(
                        f"RandomBrainHole (MasterHandler): 已加载并缓存信息函数 '{plugin_setting.info_function_name}' (模块: '{full_module_name}')"
                    )
                except ImportError:
                    logger.error(
                        f"RandomBrainHole (MasterHandler): 导入插件模块 '{full_module_name}' (用于随机信息) 失败。"
                    )
                    continue  # 跳过此插件，处理下一个
                except AttributeError:
                    logger.error(
                        f"RandomBrainHole (MasterHandler): 在模块 '{plugin_setting.module_name}' 中未找到信息函数 '{plugin_setting.info_function_name}'。"
                    )
                    continue  # 跳过此插件

            # --- 调用信息处理函数并发送结果，带重试机制 ---
            output_message: Optional[str] = None
            for attempt in range(plugin_setting.retry_attempts):  # 尝试多次获取
                logger.debug(
                    f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试从数据库获取信息 (表: {plugin_setting.table_name})。"
                )
                try:
                    # 调用插件的信息处理函数，传入表名
                    # 该函数应返回格式化后的字符串消息或 None/引发异常
                    output_message = await current_info_func(plugin_setting.table_name)
                    logger.debug(
                        f"{plugin_setting.name}: info_func 返回: '{output_message}'"
                    )

                    if output_message and isinstance(
                        output_message, str
                    ):  # 如果成功获取到有效消息
                        await matcher.send(output_message)  # 发送消息
                        logger.info(f"{plugin_setting.name}: 成功发送消息。")
                        return  # 处理完毕，直接返回，不再匹配其他插件的关键词
                    else:  # 如果返回无效内容
                        logger.warning(
                            f"{plugin_setting.name}: info_func 返回了无效内容: {output_message}"
                        )
                        if (
                            attempt + 1 == plugin_setting.retry_attempts
                        ):  # 如果是最后一次尝试
                            await matcher.send(
                                plugin_setting.failure_message
                            )  # 发送预设的失败消息
                            return  # 处理完毕

                except (
                    ValueError
                ) as ve:  # 捕获插件函数内部可能抛出的 ValueError (例如数据获取失败)
                    logger.warning(
                        f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试时，函数内部报告 ValueError: {ve}"
                    )
                    if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(f"{plugin_setting.failure_message}")
                        return
                except Exception as e:  # 捕获其他未知错误
                    logger.opt(exception=e).error(
                        f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试获取信息时发生未知错误。"
                    )
                    if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(plugin_setting.failure_message)
                        return
            return  # 如果重试完成后仍未成功发送，则结束此插件的处理


def create_plugin_handlers():
    """
    创建并注册总的 on_message 处理器。
    这个函数会在插件加载时被 `__init__.py` 调用。
    """
    logger.info("RandomBrainHole (PluginLoader): 正在创建 on_message 主处理器...")

    master_matcher = on_message(priority=0, block=False)

    master_matcher.handle()(_master_message_handler)

    logger.info(
        "RandomBrainHole (PluginLoader): on_message 主处理器已注册，优先级0，非阻塞模式。"
    )
