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
        
        # 复用下面的格式化逻辑
        return await format_fuzhipai_data(card_info, is_search_result=False)
    except ValueError:
        raise
    except Exception as e:
        logger.opt(exception=e).error(f"{plugin_display_name}插件：处理从数据库获取的随机信息时出错 (表: {table_name})。")
        raise ValueError(f"{plugin_display_name}插件处理随机数据失败。")

async def format_fuzhipai_data(card_info: Dict[str, Any], is_search_result: bool = True) -> str:
    """
    格式化给定的蝠汁牌词条信息。
    :param card_info: 包含词条信息的字典。
    :param is_search_result: 布尔值，指示这是否是查词结果，用于调整输出标题。
    :return: 格式化后的字符串。
    """
    plugin_display_name = "蝠汁牌"
    title_prefix = f"[{plugin_display_name}{' - 查词结果' if is_search_result else ''}]"
    
    # 确保所有 get 调用都有默认值
    card_title = card_info.get('card_title', '') # 蝠汁牌可能有标题
    full_text = card_info.get('full_text', '内容缺失')

    output_parts = [title_prefix]
    if card_title and card_title != '内容缺失': # 如果标题存在且不是默认的缺失值
        output_parts.append(f"标题: {card_title}")
    output_parts.append(full_text)
    
    return "\n".join(output_parts)
