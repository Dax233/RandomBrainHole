import os
import random
import pandas as pd
from nonebot import on_keyword
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import Bot, Event

from ..config import Config

# 设置关键词触发
random_suilan = on_keyword({"随机随蓝"})

@random_suilan.handle()
async def handle_random_suilan(bot: Bot, event: Event):
    config = Config()

    # 文件夹路径，需要根据实际情况进行调整
    folder_path = 'your file path'
    file_name = random.choice([file for file in os.listdir(folder_path) if file.endswith('.xlsx')])
    file_path = os.path.join(folder_path, file_name)
    
    for i in range(2):
        try:
            card_info_output = random_suilan_info(file_path)
            await random_suilan.send(card_info_output)
            return
        except Exception as e:
            logger.info(f"第{i + 1}次尝试获取词汇失败。")
    await random_suilan.send("随机随蓝被吃掉了~")

def random_suilan_info(file_path):
    # 读取Excel文件
    xls = pd.ExcelFile(file_path)
    # 假设第二个子表是随机随蓝的词表
    df = pd.read_excel(xls, sheet_name=xls.sheet_names[1], header=0)  # 第二个子表并从第一行开始

    # 随机选择一个词汇信息
    word_info = df.iloc[random.randint(0, len(df) - 1)]

    output = (
        "[随机随蓝]\n"
        f"{word_info['题面']}\n"
        f"选手：{word_info['选手']}\n"
        f"出处：{word_info['出处']}\n"
        f"解释：{word_info['解释']}"
    )

    return output
