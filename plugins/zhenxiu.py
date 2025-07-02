from typing import Optional, Dict, Any
from nonebot import logger
from ..db_utils import get_random_entry_from_db  # 从上一级目录的 db_utils 导入


# --- 随机信息获取函数 ---
async def random_zhenxiu_info(table_name: str) -> str:
    """
    从数据库中随机读取一条祯休信息并格式化输出。
    这是由 plugin_loader 中的关键词触发调用的主函数。

    :param table_name: 在 config.toml 中为此插件配置的数据库表名。
    :raises ValueError: 如果无法从数据库获取词汇，或者处理数据时发生错误。
    :return: 格式化后的祯休信息字符串。
    """
    plugin_display_name = "祯休"  # 用于日志
    try:
        # 从数据库随机获取一条记录
        word_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)
        if not word_info:  # 如果未获取到数据
            logger.warning(
                f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取词汇。"
            )
            raise ValueError(f"无法从数据库表 {table_name} 获取词汇。")

        # 复用格式化函数
        return await format_zhenxiu_data(word_info, is_search_result=False)
    except ValueError:
        raise
    except Exception as e:
        logger.opt(exception=e).error(
            f"{plugin_display_name}插件：处理从数据库获取的随机信息时出错 (表: {table_name})。"
        )
        raise ValueError(f"{plugin_display_name}插件处理随机数据失败。")


# --- 数据格式化函数 ---
async def format_zhenxiu_data(
    word_info: Dict[str, Any], is_search_result: bool = True
) -> str:
    """
    格式化给定的祯休词条信息字典。
    祯休词条在导入时，空值可能被填充为 '无'。

    :param word_info: 包含词条信息的字典。
                      期望包含的键如: 'pinyin', 'term' (词汇), 'source_text' (出处),
                                     'category' (题型), 'definition' (解释),
                                     'is_disyllabic' (双音节), 'term_id_text' (题号)。
    :param is_search_result: 布尔值，指示此调用是否来自查词功能。
    :return: 格式化后的字符串。
    """
    plugin_display_name = "祯休"
    title_prefix = f"[{plugin_display_name}{' - 查词结果' if is_search_result else ''}]"

    # 祯休数据在导入时可能将空值填充为 '无'，所以默认值可以设为 '无' 或 '暂无'
    default_value = "无"  # 与 import_data.py 中的填充值保持一致

    # 安全地获取各个字段的值
    output = (
        f"{title_prefix}\n"
        f"{word_info.get('pinyin', default_value)}\n"
        f"词汇: {word_info.get('term', default_value)}\n"  # 'term' 在祯休中对应“词汇”
        f"出处：{word_info.get('source_text', default_value)}\n"
        f"题型：{word_info.get('category', default_value)}\n"
        f"解释：{word_info.get('definition', default_value)}\n"
        f"双音节：{word_info.get('is_disyllabic', default_value)}"
        # f"题号：{word_info.get('term_id_text', default_value)}" # 如果需要显示题号，可以取消注释此行
    )
    return output
