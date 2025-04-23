import os
import random
import pandas as pd
from nonebot import on_keyword
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import Bot, Event

from ..config import Config

# 设置关键词触发
random_pinshi = on_keyword({"随机拼释"})

@random_pinshi.handle()
async def handle_random_pinshi(bot: Bot, event: Event):
    config = Config()

    # 文件夹路径，需要根据实际情况进行调整
    folder_path = 'your file path'
    file_name = random.choice([file for file in os.listdir(folder_path) if file.endswith('.xlsx')])
    file_path = os.path.join(folder_path, file_name)
    
    for i in range(2):
        try:
            card_info_output = random_pinshi_info(file_path)
            await random_pinshi.send(card_info_output)
            return
        except Exception as e:
            logger.info(f"第{i + 1}次尝试获取词汇失败。")
    await random_pinshi.send("随机拼释被吃掉了~")

def random_pinshi_info(file_path):
    # 读取Excel文件
    df = pd.read_excel(file_path, header=0)  # 第一行作为表头

    # 随机选择一个词汇信息
    word_info = df.iloc[random.randint(0, len(df) - 1)]

    output = (
        "[随机拼释]\n"
        f"{word_info['拼音']}\n"
        f"{word_info['题目']}\n"
        f"出处：{word_info['出处']}\n"
        f"书写：{word_info['书写']}\n"
        f"难度：{word_info['难度']}\n"
        f"解释：{word_info['解释']}"
    )

    return output
