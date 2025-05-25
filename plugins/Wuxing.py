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

        # 数据库列名: term, pinyin, difficulty, source_origin, author, definition
        output = (
            f"[{plugin_display_name}]\n"
            f"{word_info.get('pinyin', '暂无')}\n"
            f"{word_info.get('term', '暂无')}\n" # 对应原 '词语'
            f"难度：{word_info.get('difficulty', '暂无')}\n"
            f"出自：{word_info.get('source_origin', '暂无')}\n" # 对应原 '出自'
            f"出题人：{word_info.get('author', '暂无')}\n"
            f"释义：{word_info.get('definition', '暂无')}"
        )
        return output
    except ValueError:
        raise
    except Exception as e:
        logger.opt(exception=e).error(f"{plugin_display_name}插件：处理从数据库获取的信息时出错 (表: {table_name})。")
        raise ValueError(f"{plugin_display_name}插件处理数据失败。")
