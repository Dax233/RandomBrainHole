import asyncio
import re
from nonebot import on_message
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.log import logger

from ..word_service import word_service
from ..config import get_plugin_config

generator_matcher = on_message(rule=lambda event: isinstance(event, GroupMessageEvent))


@generator_matcher.handle()
async def handle_word_generation(bot: Bot, matcher: Matcher, event: GroupMessageEvent):
    message_text = event.get_plaintext().strip()

    trigger_word = "造词"
    if not message_text.startswith(trigger_word):
        return

    try:
        config = get_plugin_config()
        if not config.word_generator.enabled:
            return
    except Exception as e:
        logger.opt(exception=e).error("加载造词配置失败。")
        return

    arg_part = message_text[len(trigger_word) :].strip()

    n, m = 0, 1
    max_n = get_plugin_config().word_generator.max_combinations_per_request
    max_m = 20

    match = re.match(r"^\s*(\d+)(?:\s+(\d+))?\s*$", arg_part)

    if not arg_part:
        n = 5
        await matcher.send(f"只说了“造词”呀~ 我擅自为你创造 {n} 个新词好不好呀？")
    elif match:
        parts = match.groups()
        try:
            n = int(parts[0])
            if parts[1]:
                m = int(parts[1])

            if not 1 <= n <= max_n:
                await matcher.finish(
                    f"不行哦~ 每轮造词的数量(n)必须在1到{max_n}之间，这次你说的是 {n}。"
                )
                return
            if not 1 <= m <= max_m:
                await matcher.finish(
                    f"不行哦~ 造词的轮数(m)必须在1到{max_m}之间，这次你说的是 {m}。"
                )
                return
        except ValueError:
            await matcher.finish("要输入数字啦~ 像 '造词 10' 或者 '造词 20 5' 这样的。")
            return
    else:
        await matcher.finish(
            "指令格式不对哦~ 请使用 '造词 [数量]' 或 '造词 [每轮数量] [轮数]'。"
        )
        return

    total_count = n * m
    await matcher.send(
        f"收到啦~ 准备进行 {m} 轮并发造词，每轮生成 {n} 个，共计 {total_count} 个组合，请稍等片刻哦……"
    )

    all_valid_words = []
    # 小猫的淫语注释：我们现在准备一个空的小盒子(forward_nodes)，用来装每一轮的报告哦~
    forward_nodes = []

    try:
        tasks = [word_service.generate_words(n) for _ in range(m)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 小猫的淫语注释：派对结束，开始一轮一轮地清点战果和体液！
        for i, result in enumerate(results):
            round_num = i + 1
            node_nickname = f"第 {round_num} 轮记录"
            node_content = ""

            if isinstance(result, Exception):
                logger.error(f"一个造词任务在并发执行中失败: {result}")
                node_nickname = f"第 {round_num} 轮事故报告"
                node_content = f"呜呜，这一轮派对出了意外...\n错误: {result}"
            else:
                valid_words, invalid_combinations = result
                if valid_words:
                    all_valid_words.extend(valid_words)

                # --- 这里是哥哥你最喜欢的改动！ ---
                if invalid_combinations:
                    invalid_body = "、".join(list(set(invalid_combinations)))
                    node_content = f"本轮找到 {len(invalid_combinations)} 个无含义组合：\n{invalid_body}"
                else:
                    # 如果这一轮没有失败的，也要给哥哥一个交代！
                    node_content = "本轮未产生无含义组合，太棒了！"

            # 为每一轮的结果都创建一个独立的、骚骚的转发节点
            forward_nodes.append(
                MessageSegment.node_custom(
                    user_id=bot.self_id, nickname=node_nickname, content=node_content
                )
            )

    except Exception as e:
        logger.opt(exception=e).error("执行并发造词服务时发生未知异常。")
        await matcher.finish("呜呜……在过程中出错了，请主人看看后台日志吧。")
        return

    if not all_valid_words and not forward_nodes:
        await matcher.finish("呜……一场狂欢下来，什么都没有剩下，词库可能被榨干了。")
        return

    # 1. 正常发送所有找到的有效词汇
    if all_valid_words:
        # 对最终结果去重，因为不同轮次可能找到同一个词
        unique_valid_words = {item["word"]: item for item in all_valid_words}.values()
        valid_header = f"在 {total_count} 个组合中，共找到了 {len(unique_valid_words)} 个有效词汇："
        valid_body = "\n".join(
            [
                f"【{item['word']}】({item.get('source', '出处不明')})：{item.get('definition', '释义缺失')}"
                for item in unique_valid_words
            ]
        )
        final_valid_message = f"{valid_header}\n{valid_body}"
        await matcher.send(final_valid_message)
    else:
        await matcher.send(
            f"呜呜……在 {total_count} 个组合中，一个有效的词汇都没有找到呢。"
        )

    # 2. 发送我们精心准备好的、分条记录的合并转发消息
    if forward_nodes:
        await bot.send_group_forward_msg(
            group_id=event.group_id, messages=forward_nodes
        )
