from typing import Optional, Dict, Any
from nonebot import logger  # 使用 NoneBot 的 logger
from ..db_utils import get_random_entry_from_db  # 从上一级目录的 db_utils 导入


# --- 随机信息获取函数 ---
async def random_brainhole_info(table_name: str) -> str:
    """
    从数据库中随机读取一条脑洞信息并格式化输出。
    这是由 plugin_loader 中的关键词触发调用的主函数。

    :param table_name: 在 config.toml 中为此插件配置的数据库表名。
    :raises ValueError: 如果无法从数据库获取词汇，或者处理数据时发生错误。
    :return: 格式化后的脑洞信息字符串。
    """
    plugin_display_name = "脑洞"  # 用于日志和可能的输出前缀，方便识别
    try:
        # 从数据库随机获取一条记录
        word_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)

        if not word_info:  # 如果没有获取到数据 (例如表为空)
            logger.warning(
                f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取词汇。"
            )
            # 抛出 ValueError，会被 plugin_loader 中的重试逻辑捕获
            raise ValueError(f"无法从数据库表 {table_name} 获取词汇。")

        # 复用下面的格式化函数来生成输出字符串
        # is_search_result=False 表示这不是查词结果，而是随机获取的结果
        return await format_brainhole_data(word_info, is_search_result=False)

    except (
        ValueError
    ):  # 如果 format_brainhole_data 或 get_random_entry_from_db 显式抛出 ValueError
        raise  # 直接重新抛出，由上层处理
    except Exception as e:  # 捕获其他所有意外错误
        logger.opt(exception=e).error(
            f"{plugin_display_name}插件：处理从数据库获取的随机信息时出错 (表: {table_name})。"
        )
        # 将未知错误包装成 ValueError 抛出，以便 plugin_loader 的重试逻辑能够统一处理
        raise ValueError(f"{plugin_display_name}插件处理随机数据失败。")


# --- 数据格式化函数 ---
async def format_brainhole_data(
    word_info: Dict[str, Any], is_search_result: bool = True
) -> str:
    """
    格式化给定的脑洞词条信息字典，生成用户友好的字符串。
    此函数被 random_brainhole_info (用于随机获取) 和 plugin_loader 中的查词逻辑调用。

    :param word_info: 包含词条信息的字典，从数据库查询得到。
                      期望包含的键如: 'pinyin', 'term', 'difficulty', 'win_rate',
                                     'category', 'author', 'definition', 'match_name'。
    :param is_search_result: 布尔值，指示此调用是否来自查词功能。
                             True: 输出标题会包含 "查词结果"。
                             False: 输出标题不含额外标记 (用于随机获取)。
    :return: 格式化后的字符串。
    """
    plugin_display_name = "脑洞"
    # 根据是否为查词结果，调整输出的标题前缀
    title_prefix = f"[{plugin_display_name}{' - 查词结果' if is_search_result else ''}]"

    # 使用 .get(key, default_value) 来安全地访问字典中的值，
    # 避免因数据不完整 (例如数据库中某些字段为空) 而引发 KeyError。
    output = (
        f"{title_prefix}\n"
        f"{word_info.get('pinyin', '拼音:暂无')}\n"
        f"词汇: {word_info.get('term', '暂无')}\n"  # 明确标出“词汇”字段
        f"难度：{word_info.get('difficulty', '暂无')}\n"
        f"胜率：{word_info.get('win_rate', '暂无')}\n"
        f"类型：{word_info.get('category', '暂无')}\n"
        f"出题人：{word_info.get('author', '暂无')}\n"
        f"释义：{word_info.get('definition', '暂无')}\n"
        f"场次：{word_info.get('match_name', '未知场次')}"  # 脑洞词条特有的“场次”信息
    )
    return output
