import pandas as pd
from typing import Optional
from nonebot.log import logger
from ..db_utils import get_random_excel_row

def random_wuxing_info(file_path: str) -> str:
    """
    从指定的 Excel 文件中随机读取一条五行信息并格式化输出。
    使用通用的 get_random_excel_row 工具函数。

    参数:
        file_path (str): Excel 文件的完整路径。

    返回:
        str: 格式化后的五行信息字符串。
    """
    plugin_name = "五行"
    try:
        # 五行插件通常读取第一个工作表，表头在第一行 (index 0)
        word_info: pd.Series = get_random_excel_row(
            file_path,
            sheet_name_or_index=0,
            header_row=0,
            plugin_name=plugin_name
        )

        output = (
            f"[{plugin_name}]\n"
            f"{word_info.get('拼音', '暂无')}\n"
            f"{word_info.get('词语', '暂无')}\n"
            f"难度：{word_info.get('难度', '暂无')}\n"
            f"出自：{word_info.get('出自', '暂无')}\n"
            f"出题人：{word_info.get('出题人', '暂无')}\n"
            f"释义：{word_info.get('释义', '暂无')}"
        )
        return output
    except KeyError as e:
        logger.error(f"{plugin_name}插件: 处理文件 {file_path} 时，列名 {e} 未找到。请检查 Excel 文件格式。")
        raise ValueError(f"处理文件 {file_path} 时，数据格式错误（缺少列：{e}）。")
