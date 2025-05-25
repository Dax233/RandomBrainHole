from typing import Optional, Dict, Any
from nonebot import logger # 使用 NoneBot 的 logger
from ..db_utils import get_random_entry_from_db # 从上一级目录的 db_utils 导入

async def random_brainhole_info(table_name: str) -> str:
    """从数据库中随机读取一条脑洞信息并格式化输出。"""
    plugin_display_name = "脑洞" # 用于日志和可能的输出前缀
    try:
        # 从数据库获取随机条目
        word_info: Optional[Dict[str, Any]] = await get_random_entry_from_db(table_name)
        
        if not word_info:
            logger.warning(f"{plugin_display_name}插件：无法从数据库表 {table_name} 获取词汇。")
            # 抛出 ValueError，以便 plugin_loader 可以捕获并处理重试/失败消息
            raise ValueError(f"无法从数据库表 {table_name} 获取词汇。")

        # 根据数据库列名格式化输出
        # 假设数据库列名与之前导入脚本中定义的一致
        output = (
            f"[{plugin_display_name}]\n"
            f"{word_info.get('pinyin', '暂无')}\n"
            f"{word_info.get('term', '暂无')}\n"
            f"难度：{word_info.get('difficulty', '暂无')}\n"
            f"胜率：{word_info.get('win_rate', '暂无')}\n" 
            f"类型：{word_info.get('category', '暂无')}\n"
            f"出题人：{word_info.get('author', '暂无')}\n" 
            f"释义：{word_info.get('definition', '暂无')}\n"
            f"场次：{word_info.get('match_name', '未知场次')}"
        )
        return output
    except ValueError: # 直接重新抛出上面手动抛出的 ValueError
        raise
    except Exception as e: # 捕获其他意外错误
        logger.opt(exception=e).error(f"{plugin_display_name}插件：处理从数据库获取的信息时出错 (表: {table_name})。")
        # 抛出 ValueError，以便 plugin_loader 处理
        raise ValueError(f"{plugin_display_name}插件处理数据失败。")
