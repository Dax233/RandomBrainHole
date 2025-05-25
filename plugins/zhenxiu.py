import pandas as pd
from typing import Optional
from nonebot.log import logger
from RandomBrainHole.db_utils import get_random_excel_row

def random_zhenxiu_info(file_path: str) -> str:
    """
    从指定的 Excel 文件中随机读取一条祯休信息并格式化输出。
    原逻辑: 随机选择一个子表，表头在第三行 (index 2), 对 NaN 值填充为 '无'。
    使用通用的 get_random_excel_row 工具函数。

    参数:
        file_path (str): Excel 文件的完整路径。

    返回:
        str: 格式化后的祯休信息字符串。
    """
    plugin_name = "祯休"
    try:
        # 祯休插件随机选择一个工作表 (sheet_name_or_index=None)，表头在第三行 (index 2)
        word_info_raw: pd.Series = get_random_excel_row(
            file_path,
            sheet_name_or_index=None, # utils 函数内部会随机选择一个 sheet
            header_row=2,            # 表头在第三行
            plugin_name=plugin_name
        )
        
        # 对 NaN 值进行填充
        word_info = word_info_raw.fillna('无') # type: ignore

        output = (
            f"[{plugin_name}]\n"
            f"{word_info.get('拼音', '无')}\n" 
            f"{word_info.get('词汇', '无')}\n"
            f"出处：{word_info.get('出处', '无')}\n"
            f"题型：{word_info.get('题型', '无')}\n"
            f"解释：{word_info.get('解释', '无')}\n"
            f"双音节：{word_info.get('双音节', '无')}" # 使用 .get 以防列名不存在，并提供默认值
        )
        return output
    except KeyError as e: # 理论上 .get() 会避免 KeyError，除非直接访问 word_info['不存在的列']
        logger.error(f"{plugin_name}插件: 处理文件 {file_path} 时，列名 {e} 未找到。请检查 Excel 文件格式。")
        raise ValueError(f"处理文件 {file_path} 时，数据格式错误（缺少列：{e}）。")
    # ValueError 等其他异常由 get_random_excel_row 抛出并由 plugin_loader 捕获
