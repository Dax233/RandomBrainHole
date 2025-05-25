from typing import Optional, Dict, Any
from nonebot import logger
from ..db_utils import get_random_entry_from_db

async def random_suilan_info(table_name: str) -> str:
    """从数据库中随机读取一条随蓝信息并格式化输出。"""
    plugin_display_name = "随蓝"
    try:
        word_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)
        if not word_info:
            logger.warning(f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取词汇。")
            raise ValueError(f"无法从数据库表 {table_name} 获取词汇。")

        # 数据库列名: term, player, source_text, definition
        output = (
            f"[{plugin_display_name}]\n"
            f"{word_info.get('term', '暂无')}\n" # 对应原 '题面'
            f"选手：{word_info.get('player', '暂无')}\n"
            f"出处：{word_info.get('source_text', '暂无')}\n"
            f"解释：{word_info.get('definition', '暂无')}"
        )
        return output
    except ValueError:
        raise
    except Exception as e:
        logger.opt(exception=e).error(f"{plugin_display_name}插件：处理从数据库获取的信息时出错 (表: {table_name})。")
        raise ValueError(f"{plugin_display_name}插件处理数据失败。")
