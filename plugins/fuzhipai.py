from typing import Optional, Dict, Any
from nonebot import logger
from ..db_utils import get_random_entry_from_db  # 从上一级目录的 db_utils 导入


# --- 随机信息获取函数 ---
async def random_fuzhipai_info(table_name: str) -> str:
    """
    从数据库中随机读取一条蝠汁牌信息并格式化输出。
    这是由 plugin_loader 中的关键词触发调用的主函数。

    :param table_name: 在 config.toml 中为此插件配置的数据库表名。
    :raises ValueError: 如果无法从数据库获取卡牌，或者处理数据时发生错误。
    :return: 格式化后的蝠汁牌信息字符串。
    """
    plugin_display_name = "蝠汁牌"  # 用于日志和可能的输出前缀
    try:
        # 从数据库随机获取一条记录
        card_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)

        if not card_info:  # 如果没有获取到数据
            logger.warning(
                f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取卡牌。"
            )
            raise ValueError(f"无法从数据库表 {table_name} 获取卡牌。")

        # 复用格式化函数
        return await format_fuzhipai_data(card_info, is_search_result=False)
    except ValueError:
        raise
    except Exception as e:
        logger.opt(exception=e).error(
            f"{plugin_display_name}插件：处理从数据库获取的随机信息时出错 (表: {table_name})。"
        )
        raise ValueError(f"{plugin_display_name}插件处理随机数据失败。")


# --- 数据格式化函数 ---
async def format_fuzhipai_data(
    card_info: Dict[str, Any], is_search_result: bool = True
) -> str:
    """
    格式化给定的蝠汁牌词条信息字典。
    蝠汁牌的特点是可能有较长的文本内容 (full_text)。

    :param card_info: 包含词条信息的字典。
                      期望包含的键如: 'card_title', 'full_text'。
    :param is_search_result: 布尔值，指示此调用是否来自查词功能。
    :return: 格式化后的字符串。
    """
    plugin_display_name = "蝠汁牌"
    title_prefix = f"[{plugin_display_name}{' - 查词结果' if is_search_result else ''}]"

    # 安全地获取卡牌标题和完整文本
    card_title = card_info.get("card_title", "")  # 蝠汁牌可能有独立的标题字段
    full_text = card_info.get("full_text", "内容缺失")  # 主要内容

    output_parts = [title_prefix]  # 开始构建输出列表

    # 如果卡牌标题存在且不是默认的缺失值，则添加到输出中
    if (
        card_title and card_title != "内容缺失" and card_title.strip()
    ):  # 确保标题有实际内容
        output_parts.append(f"标题: {card_title}")

    output_parts.append(full_text)  # 添加卡牌的完整文本

    # 使用换行符连接所有部分
    return "\n".join(output_parts)
