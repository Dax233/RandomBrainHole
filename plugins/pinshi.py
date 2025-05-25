import pandas as pd # 保留用于类型提示 (Optional[pd.Series])
from typing import Optional # 导入 Optional
from nonebot.log import logger
from RandomBrainHole.db_utils import get_random_excel_row # 导入新的工具函数

def random_pinshi_info(file_path: str) -> str:
    """
    从指定的 Excel 文件中随机读取一条拼释信息并格式化输出。
    使用通用的 get_random_excel_row 工具函数。

    参数:
        file_path (str): Excel 文件的完整路径。

    返回:
        str: 格式化后的拼释信息字符串。
    
    可能抛出:
        与 get_random_excel_row 相同的异常 (FileNotFoundError, ValueError, etc.)
        KeyError: 如果返回的 Series 中缺少预期的列名。
    """
    plugin_name = "拼释"
    try:
        # 拼释插件通常读取第一个工作表，表头在第一行 (index 0)
        word_info: pd.Series = get_random_excel_row( # 类型提示改为 pd.Series
            file_path,
            sheet_name_or_index=0, # 第一个工作表
            header_row=0,          # 表头在第一行
            plugin_name=plugin_name
        )
        
        # get_random_excel_row 现在会抛出异常而不是返回 None
        output = (
            f"[{plugin_name}]\n" # 使用 plugin_name 变量
            f"{word_info.get('拼音', '暂无')}\n"
            f"{word_info.get('题目', '暂无')}\n"
            f"出处：{word_info.get('出处', '暂无')}\n"
            f"书写：{word_info.get('书写', '暂无')}\n"
            f"难度：{word_info.get('难度', '暂无')}\n"
            f"解释：{word_info.get('解释', '暂无')}"
        )
        return output
    except KeyError as e:
        logger.error(f"{plugin_name}插件: 处理文件 {file_path} 时，列名 {e} 未找到。请检查 Excel 文件格式。")
        raise ValueError(f"处理文件 {file_path} 时，数据格式错误（缺少列：{e}）。")
    # get_random_excel_row 会处理 FileNotFoundError 和 ValueError (空表等)
    # 所以这里不需要重复捕获，除非要添加特定于拼释插件的额外处理
