from typing import Optional, Dict, Any
from nonebot import logger
from ..db_utils import get_random_entry_from_db

async def random_zhenxiu_info(table_name: str) -> str:
    """从数据库中随机读取一条祯休信息并格式化输出。"""
    plugin_display_name = "祯休"
    try:
        word_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)
        if not word_info:
            logger.warning(f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取词汇。")
            raise ValueError(f"无法从数据库表 {table_name} 获取词汇。")

        # 数据库列名: term_id_text, term, source_text, category, pinyin, definition, is_disyllabic
        # 导入时已处理 fillna('无')
        output = (
            f"[{plugin_display_name}]\n"
            f"{word_info.get('pinyin', '无')}\n" 
            f"{word_info.get('term', '无')}\n" 
            f"出处：{word_info.get('source_text', '无')}\n"
            f"题型：{word_info.get('category', '无')}\n" 
            f"解释：{word_info.get('definition', '无')}\n"
            f"双音节：{word_info.get('is_disyllabic', '无')}" 
            # f"题号：{word_info.get('term_id_text', '无')}" # 如果需要显示题号
        )
        return output
    except ValueError:
        raise
    except Exception as e:
        logger.opt(exception=e).error(f"{plugin_display_name}插件：处理从数据库获取的信息时出错 (表: {table_name})。")
        raise ValueError(f"{plugin_display_name}插件处理数据失败。")
