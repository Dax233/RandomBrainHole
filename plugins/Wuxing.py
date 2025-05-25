from typing import Optional, Dict, Any
from nonebot import logger
from ..db_utils import get_random_entry_from_db

async def random_wuxing_info(table_name: str) -> str:
    """从数据库中随机读取一条五行信息并格式化输出。"""
    plugin_display_name = "五行"
    try:
        word_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)
        if not word_info:
            logger.warning(f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取词汇。")
            raise ValueError(f"无法从数据库表 {table_name} 获取词汇。")

        # 复用下面的格式化逻辑
        return await format_wuxing_data(word_info, is_search_result=False)
    except ValueError:
        raise
    except Exception as e:
        logger.opt(exception=e).error(f"{plugin_display_name}插件：处理从数据库获取的随机信息时出错 (表: {table_name})。")
        raise ValueError(f"{plugin_display_name}插件处理随机数据失败。")

async def format_wuxing_data(word_info: Dict[str, Any], is_search_result: bool = True) -> str:
    """
    格式化给定的五行词条信息。
    :param word_info: 包含词条信息的字典。
    :param is_search_result: 布尔值，指示这是否是查词结果，用于调整输出标题。
    :return: 格式化后的字符串。
    """
    plugin_display_name = "五行"
    title_prefix = f"[{plugin_display_name}{' - 查词结果' if is_search_result else ''}]"

    # 确保所有 get 调用都有默认值
    output = (
        f"{title_prefix}\n"
        f"{word_info.get('pinyin', '拼音:暂无')}\n"
        f"词语: {word_info.get('term', '暂无')}\n"
        f"难度：{word_info.get('difficulty', '暂无')}\n"
        f"出自：{word_info.get('source_origin', '暂无')}\n"
        f"出题人：{word_info.get('author', '暂无')}\n"
        f"释义：{word_info.get('definition', '暂无')}"
    )
    return output
