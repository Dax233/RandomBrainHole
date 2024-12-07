import os
import random
import pandas as pd
from nonebot import on_keyword
from nonebot.adapters.onebot.v11 import Bot, Event

from ..config import Config

# 设置关键词触发
random_wuxing = on_keyword({"随机五行"})

@random_wuxing.handle()
async def handle_random_wuxing(bot: Bot, event: Event):
    config = Config()

    # 文件夹路径，需要根据实际情况进行调整
    folder_path = 'your file path'
    file_name = random.choice([file for file in os.listdir(folder_path) if file.endswith('.xlsx')])
    file_path = os.path.join(folder_path, file_name)
    
    try:
        word_info_output = random_wuxing_info(file_path)
        await random_wuxing.send(word_info_output)
    except Exception as e:
        await random_wuxing.send(f"发生错误：{e}")

def random_wuxing_info(file_path):
    # 读取Excel文件
    df = pd.read_excel(file_path, header=0)  # 第一行作为表头

    # 随机选择一个词汇信息
    word_info = df.iloc[random.randint(0, len(df) - 1)]

    output = (
        "[随机五行]\n"
        f"{word_info['拼音']}\n"
        f"{word_info['词语']}\n"
        f"难度：{word_info['难度']}\n"
        f"出自：{word_info['出自']}\n"
        f"出题人：{word_info['出题人']}\n"
        f"释义：{word_info['释义']}"
    )

    return output
