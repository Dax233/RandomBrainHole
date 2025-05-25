import random
import re
from docx import Document # 需要 pip install python-docx
from nonebot.log import logger

def random_fuzhipai_info(file_path: str) -> str:
    """
    从指定的 Word 文档中随机读取一条蝠汁牌信息并格式化输出。

    参数:
        file_path (str): Word 文档 (.doc 或 .docx) 的完整路径。

    返回:
        str: 格式化后的蝠汁牌信息字符串。

    可能抛出:
        FileNotFoundError: 如果文件路径不存在。
        ValueError: 如果文档中未找到符合条件的卡牌信息或文档格式问题。
        Exception: 其他 python-docx 或文件读取相关的错误。
    """
    plugin_name = "蝠汁牌"
    try:
        doc = Document(file_path)
    except FileNotFoundError:
        logger.error(f"{plugin_name}插件：文件 {file_path} 未找到。")
        raise
    except Exception as e: # python-docx 可能抛出其他类型的错误, 如 PackageNotFoundError
        logger.error(f"{plugin_name}插件：打开或读取Word文件 {file_path} 失败: {e}")
        raise ValueError(f"打开或读取Word文件 {file_path} 失败，可能是文件损坏或格式不支持。")

    cards = []
    current_card_paragraphs_runs = [] # 存储当前卡片的 (段落文本, 是否斜体) 列表

    # 遍历文档中的每个段落来提取卡牌
    # 假设每个卡牌以 "字母数字组合【任意字符】" 开头
    # 并且卡牌之间以此模式分隔
    
    # 一个更稳健的策略是，将文档视为一个段落流，
    # 当遇到卡牌起始标志时，之前收集的内容（如果存在）构成一张卡牌。
    
    active_card_content = []

    for para in doc.paragraphs:
        para_text_raw = para.text # 获取段落的原始文本用于匹配起始标志
        
        # 使用正则表达式匹配卡牌的起始标志 (确保只在段落开头匹配)
        if re.match(r"^[A-Za-z0-9]+【.*?】", para_text_raw.lstrip()): # lstrip处理段前空格
            if active_card_content: # 如果当前卡片已有内容，则处理并存入cards
                # 将收集到的段落合并为一个卡牌字符串
                full_card_text = "\n".join(active_card_content).strip()
                if full_card_text: # 确保不是空卡
                    cards.append(full_card_text)
                active_card_content = [] # 开始收集新卡片
        
        # 收集当前段落的文本，并处理斜体
        # 原逻辑中对斜体的处理比较复杂，这里尝试还原
        processed_para_text = ""
        for run in para.runs:
            text = run.text
            if run.italic:
                # 为了简单起见，这里不添加方括号，直接输出文本
                # 如果需要严格的 [斜体内容] 格式，可以在这里添加
                # processed_para_text += f'[{text}]' # 这种方式可能导致 [[文本]]
                # 更精细的控制需要判断斜体块的开始和结束
                processed_para_text += text # 简化：只输出文本，斜体信息丢失
            else:
                processed_para_text += text
        
        # 如果不希望丢失斜体信息，但又不想处理复杂的方括号逻辑，
        # 可以考虑保留原始 para.text，或者在格式化输出时再决定是否标记斜体
        # 为了与原逻辑的输出格式（带方括号的斜体）尽量接近，我们尝试一种方式：
        # 但要注意，这种方式对于连续的斜体run和非斜体run交错的情况，
        # 可能不会完美地生成单一的 [整个斜体块]
        
        # 重新实现斜体处理，尽量接近原意图
        current_para_formatted_text = ""
        is_currently_italic = False
        for run in para.runs:
            if run.italic:
                if not is_currently_italic:
                    current_para_formatted_text += "[" # 开始斜体块
                    is_currently_italic = True
                current_para_formatted_text += run.text
            else:
                if is_currently_italic:
                    current_para_formatted_text += "]" # 结束斜体块
                    is_currently_italic = False
                current_para_formatted_text += run.text
        if is_currently_italic: # 如果段落以斜体结束
            current_para_formatted_text += "]"

        if current_para_formatted_text.strip(): # 只添加非空段落
             active_card_content.append(current_para_formatted_text.strip())

    # 处理文档末尾的最后一个卡牌
    if active_card_content:
        full_card_text = "\n".join(active_card_content).strip()
        if full_card_text:
            cards.append(full_card_text)

    if not cards:
        logger.warning(f"{plugin_name}插件：在文件 {file_path} 中没有找到符合条件的卡牌信息。")
        raise ValueError(f"在文件 {file_path} 中没有找到符合条件的卡牌信息。")

    selected_card = random.choice(cards)

    # 移除多余的空行 (原逻辑)
    # selected_card_cleaned = re.sub(r'\n\s*\n+', '\n', selected_card).strip()
    # 上面的合并逻辑应该已经处理了大部分空行问题，但可以再清理一次
    lines = [line for line in selected_card.splitlines() if line.strip()]
    selected_card_cleaned = "\n".join(lines)


    output = f"[{plugin_name}]\n{selected_card_cleaned}"
    return output
