import importlib
from typing import Callable, Any, Coroutine, Dict, Optional
from nonebot import on_message # 导入 on_message
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Bot, Event, Message # 导入 Message
from nonebot.log import logger
# from nonebot.rule import Rule # 如果需要更复杂的规则，可以导入 Rule

# 从同级目录的 config 模块导入配置相关的类和函数
from .config import PluginSetting, get_plugin_config

# 缓存已加载的 info_func，避免在每次消息来时都重新导入和 getattr
# 键是元组 (module_name, function_name)，值是实际的函数对象
_loaded_info_funcs: Dict[tuple[str, str], Callable[[str], Coroutine[Any, Any, str]]] = {}

async def _master_message_handler(bot: Bot, event: Event, matcher: Matcher):
    """
    单一的 on_message 处理器，负责接收消息并分发到具体的插件逻辑。
    """
    message_text = event.get_plaintext().strip() # 获取纯文本消息内容并去除首尾空格
    if not message_text: # 如果消息是空的 (例如只有图片)，则不处理
        return

    current_config = get_plugin_config() # 获取当前插件的全部配置

    # 遍历配置文件中定义的所有 "子插件" 设置
    for plugin_setting in current_config.plugins:
        triggered_keyword: Optional[str] = None
        # 检查当前消息文本是否包含此子插件配置的任何一个关键词
        for keyword in plugin_setting.keywords:
            if keyword in message_text: # 使用简单的 "in" 判断关键词是否存在
                triggered_keyword = keyword
                break # 找到一个匹配的关键词即可为这个子插件触发

        if triggered_keyword:
            logger.info(f"RandomBrainHole (MasterHandler): 消息 '{message_text}' 命中了插件 '{plugin_setting.name}' 的关键词 '{triggered_keyword}'")
            
            # 动态加载并执行对应的 info_func
            func_key = (plugin_setting.module_name, plugin_setting.info_function_name)
            current_info_func = _loaded_info_funcs.get(func_key)

            if current_info_func is None: # 如果尚未加载，则加载并缓存
                try:
                    full_module_name = f"src.plugins.RandomBrainHole.plugins.{plugin_setting.module_name}"
                    plugin_module = importlib.import_module(full_module_name)
                    current_info_func = getattr(plugin_module, plugin_setting.info_function_name)
                    _loaded_info_funcs[func_key] = current_info_func
                    logger.debug(f"RandomBrainHole (MasterHandler): 已加载并缓存函数 '{plugin_setting.info_function_name}' 从模块 '{full_module_name}'")
                except ImportError:
                    logger.error(f"RandomBrainHole (MasterHandler): 导入插件模块 '{full_module_name}' 失败。")
                    continue # 跳过这个插件，继续检查下一个
                except AttributeError:
                    logger.error(f"RandomBrainHole (MasterHandler): 在模块 '{plugin_setting.module_name}' 中未找到函数 '{plugin_setting.info_function_name}'。")
                    continue # 跳过

            # 执行获取信息的逻辑，包含重试
            output_message: Optional[str] = None
            for attempt in range(plugin_setting.retry_attempts):
                logger.debug(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试从数据库获取信息 (表: {plugin_setting.table_name})。")
                try:
                    output_message = await current_info_func(plugin_setting.table_name)
                    logger.debug(f"{plugin_setting.name}: info_func 返回: '{output_message}'")
                    
                    if output_message and isinstance(output_message, str):
                        await matcher.send(output_message) # 使用 on_message 创建的 matcher 发送消息
                        logger.info(f"{plugin_setting.name}: 成功发送消息。")
                        return # 处理完一个匹配的插件后，通常应该结束，避免一条消息触发多个回复
                    else:
                        logger.warning(f"{plugin_setting.name}: info_func 返回了无效内容: {output_message}")
                        if attempt + 1 == plugin_setting.retry_attempts:
                            await matcher.send(plugin_setting.failure_message)
                            return
                
                except ValueError as ve:
                     logger.warning(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试时，函数内部报告 ValueError: {ve}")
                     if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(f"{plugin_setting.name}：处理数据时遇到问题，请稍后再试。")
                        return
                except Exception as e:
                    logger.opt(exception=e).error(f"{plugin_setting.name}: 第 {attempt + 1}/{plugin_setting.retry_attempts} 次尝试获取信息时发生未知错误。")
                    if attempt + 1 == plugin_setting.retry_attempts:
                        await matcher.send(plugin_setting.failure_message)
                        return
            return # 如果已经匹配并处理了一个插件，就结束

def create_plugin_handlers():
    """
    创建并注册总的 on_message 处理器。
    """
    logger.info("RandomBrainHole (PluginLoader): 正在创建 on_message 主处理器...")
    
    # 创建一个 on_message 匹配器
    # priority 可以根据需要调整，确保它能在你的其他插件中获得合适的执行顺序
    # block=False 意味着即使这个处理器运行了，事件仍可能继续传递给其他插件的 on_message 处理器
    # 如果希望 RandomBrainHole 处理后就停止，可以考虑设为 block=True，并在 _master_message_handler 内部成功处理后使用 matcher.finish()
    # 但通常对于关键词匹配类的插件，在内部成功响应后直接 return 就够了，block=True 在 matcher 级别更强力。
    # 考虑到内部有多个关键词判断，我们将 block 设置为 False，在 _master_message_handler 内部匹配成功后 return。
    # 或者，如果希望一旦 RandomBrainHole 的任何一个关键词匹配，就不再让其他插件处理这条消息，可以将 block 设为 True。
    # 之前 on_keyword 用了 block=True，这里如果用 on_message 且内部有多个关键词，
    # 那么 block=True 意味着只要这个 on_message 匹配器运行了（即使内部没有关键词命中），也可能阻塞其他插件。
    # 因此，更细致的控制是在 _master_message_handler 内部匹配成功后用 matcher.stop_propagation() 或者直接让 matcher block=True 并早 return。
    # 为了尽量接近 on_keyword 的行为（一旦匹配并处理就阻塞），我们将 block 设为 True，并在内部成功处理后 return。
    
    master_matcher = on_message(
        priority=0, # 给一个适中的优先级，可以根据你的其他插件调整
        block=False  # 如果此 matcher 的 handle 被执行，则阻止事件向其他同级或更低优先级的 message matcher 传播
    )
    
    # 为这个 matcher 注册处理器函数
    master_matcher.handle()(_master_message_handler)
    
    logger.info(f"RandomBrainHole (PluginLoader): on_message 主处理器已注册，优先级0，非阻塞模式。")