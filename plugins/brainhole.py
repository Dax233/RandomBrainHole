from typing import Optional, Dict, Any
from nonebot import logger # 使用 NoneBot 的 logger
from ..db_utils import get_random_entry_from_db # 从上一级目录的 db_utils 导入

async def random_brainhole_info(table_name: str) -> str:
    """从数据库中随机读取一条脑洞信息并格式化输出。"""
    plugin_display_name = "脑洞" # 用于日志和可能的输出前缀
    try:
        word_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)
        
        if not word_info:
            logger.warning(f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取词汇。")
            raise ValueError(f"无法从数据库表 {table_name} 获取词汇。")

        # 复用下面的格式化逻辑
        return await format_brainhole_data(word_info, is_search_result=False)
    except ValueError: 
        raise
    except Exception as e: 
        logger.opt(exception=e).error(f"{plugin_display_name}插件：处理从数据库获取的随机信息时出错 (表: {table_name})。")
        raise ValueError(f"{plugin_display_name}插件处理随机数据失败。")

async def format_brainhole_data(word_info: Dict[str, Any], is_search_result: bool = True) -> str:
    """
    格式化给定的脑洞词条信息。
    :param word_info: 包含词条信息的字典。
    :param is_search_result: 布尔值，指示这是否是查词结果，用于调整输出标题。
    :return: 格式化后的字符串。
    """
    plugin_display_name = "脑洞"
    title_prefix = f"[{plugin_display_name}{' - 查词结果' if is_search_result else ''}]"

    # 确保所有 get 调用都有默认值，以防数据不完整
    output = (
        f"{title_prefix}\n"
        f"{word_info.get('pinyin', '拼音:暂无')}\n"
        f"词汇: {word_info.get('term', '暂无')}\n" # 明确标出“词汇”
        f"难度：{word_info.get('difficulty', '暂无')}\n"
        f"胜率：{word_info.get('win_rate', '暂无')}\n" 
        f"类型：{word_info.get('category', '暂无')}\n"
        f"出题人：{word_info.get('author', '暂无')}\n" 
        f"释义：{word_info.get('definition', '暂无')}\n"
        f"场次：{word_info.get('match_name', '未知场次')}"
    )
    return output
