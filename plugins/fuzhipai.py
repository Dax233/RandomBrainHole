import os
import random
import re
from docx import Document
from nonebot import on_keyword
from nonebot.adapters.onebot.v11 import Bot, Event

from ..config import Config

# 设置关键词触发
random_fuzhipai = on_keyword({"随机蝠汁牌"})

@random_fuzhipai.handle()
async def handle_random_fuzhipai(bot: Bot, event: Event):
    config = Config()

    # 文件夹路径，需要根据实际情况进行调整
    folder_path = 'your file path'
    if not os.path.exists(folder_path):
        await random_fuzhipai.send("文件夹路径不存在")
        return

    doc_files = [file for file in os.listdir(folder_path) if file.endswith('.doc') or file.endswith('.docx')]
    if not doc_files:
        await random_fuzhipai.send("文件夹中没有找到任何 .doc 或 .docx 文件")
        return

    file_name = random.choice(doc_files)
    file_path = os.path.join(folder_path, file_name)
    
    try:
        card_info_output = random_fuzhipai_info(file_path)
        await random_fuzhipai.send(card_info_output)
    except Exception as e:
        await random_fuzhipai.send(f"发生错误：{e}")

def random_fuzhipai_info(file_path):
    # 读取Word文档
    doc = Document(file_path)
    
    cards = []
    card = []
    temp_text = ""
    is_italic = False

    # 遍历每个段落
    for para in doc.paragraphs:
        if re.match(r"[A-Za-z0-9]+【.*?】", para.text):
            if card:
                cards.append("".join(card).strip())
                card = []
        for run in para.runs:
            text = run.text
            if run.italic and not is_italic:
                temp_text += f'[{text}'
                is_italic = True
            elif run.italic and is_italic:
                temp_text += text
            elif not run.italic and is_italic:
                temp_text += f'{text}]'
                is_italic = False
            else:
                temp_text += text
        # 处理单个段落内的结尾斜体
        if is_italic:
            temp_text += ']'
            is_italic = False
        card.append(temp_text)
        temp_text = ""
        card.append("\n")

    if card:
        cards.append("".join(card).strip())

    if not cards:
        raise ValueError("没有找到符合条件的卡牌信息")

    # 随机选择一个卡牌信息
    selected_card = random.choice(cards).strip()

    # 移除多余的空行
    selected_card = re.sub(r'\n\s*\n', '\n', selected_card).strip()

    output = f"[随机蝠汁牌]\n{selected_card}"

    return output
