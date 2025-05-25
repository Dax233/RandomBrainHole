from typing import Optional, Dict, Any
from nonebot import logger
from ..db_utils import get_random_entry_from_db

async def random_fuzhipai_info(table_name: str) -> str:
    """从数据库中随机读取一条蝠汁牌信息并格式化输出。"""
    plugin_display_name = "蝠汁牌"
    try:
        card_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)
        if not card_info:
            logger.warning(f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取卡牌。")
            raise ValueError(f"无法从数据库表 {table_name} 获取卡牌。")

        # 数据库列名: card_title, full_text (full_text_hash 用于唯一性，不直接显示)
        # full_text 在导入时已处理斜体标记和多余换行
        selected_card_cleaned = card_info.get('full_text', '内容缺失')
        
        # 可以选择是否显示 card_title
        # title_display = f"标题：{card_info.get('card_title', '无标题')}\n" if card_info.get('card_title') else ""
        # output = f"[{plugin_display_name}]\n{title_display}{selected_card_cleaned}"
        
        output = f"[{plugin_display_name}]\n{selected_card_cleaned}"
        return output
    except ValueError:
        raise
    except Exception as e:
        logger.opt(exception=e).error(f"{plugin_display_name}插件：处理从数据库获取的信息时出错 (表: {table_name})。")
        raise ValueError(f"{plugin_display_name}插件处理数据失败。")
