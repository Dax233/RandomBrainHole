import os
import random
import pandas as pd
from nonebot import on_keyword
from nonebot.adapters.onebot.v11 import Bot, Event

from ..config import Config

# 设置关键词触发
random_brainstorm = on_keyword({"随机脑洞"})

@random_brainstorm.handle()
async def handle_random_brainstorm(bot: Bot, event: Event):
    config = Config()

    # 文件夹路径，需要根据实际情况进行调整
    folder_path = 'your file path'
    file_name = random.choice([file for file in os.listdir(folder_path) if file.endswith('.xlsx')])
    file_path = os.path.join(folder_path, file_name)
    
    try:
        word_info_output = random_word_info(file_path)
        await random_brainstorm.send(word_info_output)
    except Exception as e:
        await random_brainstorm.send(f"发生错误：{e}")

def random_word_info(file_path):
    # 读取Excel文件
    xls = pd.ExcelFile(file_path)
    # 随机选择一个子表（排除第一个总览表）
    sheet_name = random.choice(xls.sheet_names[1:])
    df = pd.read_excel(xls, sheet_name=sheet_name, header=None) # 不指定表头行，保留原始数据

    # 获取场次信息 
    match_info = df.iloc[0, 0] # 第一行第一列为场次信息

    # 设置实际数据的表头 
    df.columns = df.iloc[1] 
    df = df[2:] # 从第三行开始是实际数据

    # 随机选择一个词汇信息 
    word_info = df.iloc[random.randint(0, len(df) - 1)]

    # 给无敌的、勇敢的、性感的、神秘的、迷人的、神气的、勤勉的、强势的、华丽的、激情的、可怕的、漂亮的、强大的脑洞王子署名
    author = word_info.get('出题人', '暂无')
    if word_info.get('出题人', '暂无') == '——':
        author = '盐铁桶子'

    # 获取胜率并转换为百分比形式 
    win_rate = word_info.get('胜率', '暂无') 
    if win_rate != '暂无': 
        win_rate = f"{float(win_rate) * 100:.1f}%"

    # 使用get方法，若某项为空则填充“暂无”
    output = (
        "[随机脑洞]\n"
        f"{word_info.get('拼音', '暂无')}\n"
        f"{word_info.get('词汇', '暂无')}\n"
        f"难度：{word_info.get('难度', '暂无')}\n"
        f"胜率：{win_rate}\n"
        f"类型：{word_info.get('类型', '暂无')}\n"
        f"出题人：{author}\n"
        f"释义：{word_info.get('解释', '暂无')}\n"
        f"场次：{match_info}\n"
    )

    return output
