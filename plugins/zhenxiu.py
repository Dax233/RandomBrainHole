import os
import random
import pandas as pd
from nonebot import on_keyword
from nonebot.adapters.onebot.v11 import Bot, Event

from ..config import Config

# 设置关键词触发
random_zhenxiu = on_keyword({"随机祯休"})

@random_zhenxiu.handle()
async def handle_random_zhenxiu(bot: Bot, event: Event):
    config = Config()

    # 文件夹路径，需要根据实际情况进行调整
    folder_path = 'your file path'
    if not os.path.exists(folder_path):
        await random_zhenxiu.send("文件夹路径不存在")
        return

    xlsx_files = [file for file in os.listdir(folder_path) if file.endswith('.xlsx')]
    if not xlsx_files:
        await random_zhenxiu.send("文件夹中没有找到任何 .xlsx 文件")
        return

    file_name = random.choice(xlsx_files)
    file_path = os.path.join(folder_path, file_name)
    
    try:
        word_info_output = random_zhenxiu_info(file_path)
        await random_zhenxiu.send(word_info_output)
    except Exception as e:
        await random_zhenxiu.send(f"发生错误：{e}")

def random_zhenxiu_info(file_path):
    # 读取Excel文件
    xls = pd.ExcelFile(file_path)
    
    # 随机选择一个子表
    sheet_name = random.choice(xls.sheet_names)
    df = pd.read_excel(xls, sheet_name=sheet_name, header=2)
    
    if df.empty:
        raise ValueError(f"子表 {sheet_name} 为空")
    
    # 确保列名正确无误
    expected_columns = ['题号', '词汇', '出处', '题型', '拼音', '解释', '双音节']
    if list(df.columns)[:len(expected_columns)] != expected_columns:
        raise ValueError("数据框的列名不匹配，可能需要调整 header 参数")

    # 随机选择一个词汇信息
    word_info = df.iloc[random.randint(0, len(df) - 1)].fillna('无')

    output = (
        "[随机祯休]\n"
        f"{word_info['拼音']}\n"
        f"{word_info['词汇']}\n"
        f"出处：{word_info['出处']}\n"
        f"题型：{word_info['题型']}\n"
        f"解释：{word_info['解释']}\n"
        f"双音节：{word_info['双音节']}"
    )

    return output
