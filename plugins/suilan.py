import pandas as pd
from typing import Optional
from nonebot.log import logger
from RandomBrainHole.db_utils import get_random_excel_row

def random_suilan_info(file_path: str) -> str:
    """
    从指定的 Excel 文件中随机读取一条随蓝信息并格式化输出。
    （原逻辑假设第二个子表是词表，表头在第一行）
    使用通用的 get_random_excel_row 工具函数。

    参数:
        file_path (str): Excel 文件的完整路径。

    返回:
        str: 格式化后的随蓝信息字符串。
    """
    plugin_name = "随蓝"
    try:
        # 随蓝插件原逻辑是读取第二个工作表 (index 1)，表头在第一行 (index 0)
        word_info: pd.Series = get_random_excel_row(
            file_path,
            sheet_name_or_index=1, # 第二个工作表
            header_row=0,          # 表头在第一行
            plugin_name=plugin_name
        )

        output = (
            f"[{plugin_name}]\n"
            f"{word_info.get('题面', '暂无')}\n"
            f"选手：{word_info.get('选手', '暂无')}\n"
            f"出处：{word_info.get('出处', '暂无')}\n"
            f"解释：{word_info.get('解释', '暂无')}"
        )
        return output
    except KeyError as e:
        logger.error(f"{plugin_name}插件: 处理文件 {file_path} 时，列名 {e} 未找到。请检查 Excel 文件格式。")
        raise ValueError(f"处理文件 {file_path} 时，数据格式错误（缺少列：{e}）。")
    except IndexError as e: # get_random_excel_row 内部的 pandas 调用可能因 sheet 索引越界抛出
        logger.error(f"{plugin_name}插件: 文件 {file_path} 可能没有第二个工作表，或工作表索引配置错误: {e}")
        raise ValueError(f"文件 {file_path} 工作表配置错误（可能没有第二个工作表）。")
