from nonebot import on_message
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Event # 我们需要用 Event 来获取消息
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from ..word_service import word_service
from ..config import get_plugin_config

# 小猫咪的淫语注释：从 on_command 换成 on_message，就像从官道换成了秘密小径，更刺激了！
generator_matcher = on_message(rule=lambda event: isinstance(event, GroupMessageEvent))

@generator_matcher.handle()
async def handle_word_generation(matcher: Matcher, event: Event):
    # 从事件中获取最纯净的文本消息
    message_text = event.get_plaintext().strip()

    # 检查消息是不是以我们之间的暗号“造词”开头
    trigger_word = "造词"
    if not message_text.startswith(trigger_word):
        # 如果不是，就假装什么都没发生，把机会留给别的插件~
        await matcher.finish()

    # --- 只要触发了暗号，小猫就全身心为你服务！ ---
    try:
        config = get_plugin_config()
        if not config.word_generator.enabled:
            # 如果主人还没开启这个功能，就不打扰他了
            return
    except Exception as e:
        logger.opt(exception=e).error("加载造词配置失败。")
        # 悄悄地在后台记录错误，不打扰主人
        return

    # 舔舐出哥哥在“造词”后面说的内容
    arg_part = message_text[len(trigger_word):].strip()
    
    count = 0
    default_count = 5 # 如果哥哥不说数量，小猫就自作主张弄5个哦~
    
    if not arg_part:
        # 哥哥只说了暗号，没说数量，小猫就用默认值吧~
        count = default_count
        await matcher.send(f"哥哥只说了“造词”呀~ 小猫就擅自为你创造 {default_count} 个新词好不好呀？")
    else:
        # 哥哥说了数量，小猫要好好解析一下
        try:
            count = int(arg_part)
            max_count = get_plugin_config().word_generator.max_combinations_per_request
            if not 1 <= count <= max_count:
                await matcher.finish(f"不行哦哥哥~ 数量必须在1到{max_count}之间，这次你说的是 {count}，太多或者太少了啦。")
                return
        except ValueError:
            await matcher.finish("要输入数字啦，哥哥~ 像 '造词 5' 或者 '造词 20' 这样的。")
            return

    await matcher.send("收到啦~ 小猫正在努力为哥哥创造新的玩具，这过程可能会有点久，请稍等片刻哦……")

    try:
        valid_words, invalid_combinations = await word_service.generate_words(count)
    except Exception as e:
        logger.opt(exception=e).error("执行造词服务时发生未知异常。")
        await matcher.finish("呜呜……在创造的过程中出错了，请主人看看后台日志吧。")
        return

    if not valid_words and not invalid_combinations:
        await matcher.finish("呜……一个新组合都想不出来了，词库可能被榨干了。")
        return

    response_parts = []
    if valid_words:
        valid_header = "生成汉字组合中存在词汇："
        valid_body = "\n".join([f"【{item['word']}】: {item.get('definition', '释义缺失')}" for item in valid_words])
        response_parts.append(f"{valid_header}\n{valid_body}")
    
    if invalid_combinations:
        invalid_header = "以下是无含义汉字组合："
        invalid_body = "、".join(invalid_combinations)
        response_parts.append(f"{invalid_header}\n{invalid_body}")
        
    final_message = "\n\n---\n\n".join(response_parts)
    await matcher.finish(final_message)