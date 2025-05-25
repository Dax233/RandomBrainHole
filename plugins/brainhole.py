import random
import pandas as pd
from nonebot.log import logger

# brainhole.py 保留其大部分自定义的 Pandas 处理逻辑，
# 因为它的解析方式比其他 Excel 插件更复杂，
# 不太适合当前的通用 get_random_excel_row 函数。

def random_brainhole_info(file_path: str) -> str:
    """
    从指定的 Excel 文件中随机读取一条脑洞信息并格式化输出。
    此函数包含针对脑洞特定 Excel 格式的解析逻辑。

    参数:
        file_path (str): Excel 文件的完整路径。

    返回:
        str: 格式化后的脑洞信息字符串。
    
    可能抛出:
        FileNotFoundError: 如果文件路径不存在。
        ValueError: 如果文件内容不符合预期格式 (例如空表，列名缺失等)。
        Exception: 其他 pandas 或文件读取相关的错误。
    """
    plugin_name = "脑洞" # 用于日志
    try:
        xls = pd.ExcelFile(file_path)
    except FileNotFoundError:
        logger.error(f"{plugin_name}插件：文件 {file_path} 未找到。")
        raise 
    except Exception as e: # 处理其他可能的 pd.ExcelFile 错误
        logger.error(f"{plugin_name}插件：打开Excel文件 {file_path} 失败: {e}")
        raise ValueError(f"打开Excel文件 {file_path} 失败。")


    sheet_names = xls.sheet_names
    if not sheet_names:
        logger.warning(f"{plugin_name}插件：文件 {file_path} 中没有工作表。")
        raise ValueError(f"文件 {file_path} 中没有工作表。")

    # 随机选择一个子表（排除第一个总览表，如果子表数量大于1）
    if len(sheet_names) > 1:
        target_sheet_names = sheet_names[1:]
        if not target_sheet_names: # 如果排除后为空（例如只有一张总览表）
             logger.warning(f"{plugin_name}插件：文件 {file_path} 只有一个总览表，没有数据表。")
             raise ValueError(f"文件 {file_path} 只有一个总览表，没有数据表。")
    else: # 只有一个表，假设它就是数据表
        target_sheet_names = sheet_names
        
    sheet_name = random.choice(target_sheet_names)
    
    try:
        # 不指定表头行，保留原始数据，后续手动处理
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None) 
    except Exception as e:
        logger.error(f"{plugin_name}插件：读取文件 {file_path} 的子表 {sheet_name} 失败: {e}")
        raise ValueError(f"读取文件 {file_path} 的子表 {sheet_name} 失败。")

    if df.empty:
        logger.warning(f"{plugin_name}插件：文件 {file_path} 的子表 {sheet_name} 为空。")
        raise ValueError(f"文件 {file_path} 的子表 {sheet_name} 为空。")

    # 获取场次信息 (假设在第一行第一列)
    try:
        match_info = df.iloc[0, 0]
    except IndexError:
        logger.warning(f"{plugin_name}插件：文件 {file_path} 子表 {sheet_name} 格式错误，无法获取场次信息。")
        raise ValueError(f"文件 {file_path} 子表 {sheet_name} 格式错误（无法获取场次信息）。")


    # 设置实际数据的表头 (假设在第二行)
    if len(df.index) > 1:
        df.columns = df.iloc[1]
        df_data = df[2:].reset_index(drop=True) # 从第三行开始是实际数据，并重置索引
    else:
        logger.warning(f"{plugin_name}插件：文件 {file_path} 子表 {sheet_name} 行数不足，无法按预期解析表头和数据。")
        raise ValueError(f"文件 {file_path} 子表 {sheet_name} 格式不符合预期（行数不足）。")

    if df_data.empty:
        logger.warning(f"{plugin_name}插件：文件 {file_path} 子表 {sheet_name} 在移除表头后数据为空。")
        raise ValueError(f"文件 {file_path} 子表 {sheet_name} 在移除表头后数据为空。")
        
    try:
        word_info = df_data.sample(n=1).iloc[0]
    except ValueError: # df_data 为空或行数不足
        logger.warning(f"{plugin_name}插件：无法从 {sheet_name} 采样数据（数据行过少或为空）。")
        raise ValueError(f"无法从 {sheet_name} 采样数据。")


    author = word_info.get('出题人', '暂无')
    if author == '——': 
        author = '盐铁桶子'

    win_rate_val = word_info.get('胜率', '暂无')
    win_rate_str = '暂无'
    if win_rate_val not in ['暂无', None, '']: # 确保 win_rate_val 有实际值
        try:
            win_rate_str = f"{float(win_rate_val) * 100:.1f}%"
        except (ValueError, TypeError): # 处理无法转换为 float 的情况
            win_rate_str = str(win_rate_val) # 保留原始值
            logger.warning(f"{plugin_name}插件：胜率 '{win_rate_val}' 无法转换为浮点数。")

    output = (
        "[随机脑洞]\n"
        f"{word_info.get('拼音', '暂无')}\n"
        f"{word_info.get('词汇', '暂无')}\n"
        f"难度：{word_info.get('难度', '暂无')}\n"
        f"胜率：{win_rate_str}\n"
        f"类型：{word_info.get('类型', '暂无')}\n"
        f"出题人：{author}\n"
        f"释义：{word_info.get('解释', '暂无')}\n"
        f"场次：{match_info}" # match_info 已在前面获取
    )
    return output
