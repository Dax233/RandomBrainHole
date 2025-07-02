import random
import json
from typing import List, Dict, Any, Tuple

from nonebot.log import logger

from . import db_utils
from .config import get_plugin_config
from .llm_client import LLMClient  # 我们的新客户端

# 从同目录下 8105.txt 中读取《通用规范汉字表》的常用汉字
with open("src/plugins/RandomBrainHole/8105.txt", "r", encoding="utf-8") as f:
    # 读取文件内容并去除空行和重复字符
    COMMON_CHINESE_CHARACTERS = set(f.read().strip().splitlines())


class WordGenerationService:
    _instance = None
    _characters: List[str] = []
    _initialized: bool = False
    _current_strategy: str = ""  # 记录当前使用的是哪个策略的淫池

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WordGenerationService, cls).__new__(cls)
        return cls._instance

    async def initialize(self):
        """
        根据配置策略初始化汉字池。
        这现在是一个可以根据不同策略，反复填充不同淫池的超级初始化函数！
        """
        strategy = get_plugin_config().word_generator.character_source_strategy

        # 如果策略没变，且已经初始化过了，就不用再折腾了
        if self._initialized and self._current_strategy == strategy:
            return

        logger.info(f"检测到策略为 '{strategy}'，正在重新构建汉字淫池...")

        char_set = set()

        if strategy == "db":
            # 模式一：核心淫池，从我们自己的数据库里榨取精华
            char_set = set(await db_utils.get_all_unique_characters_from_terms())

        elif strategy == "common":
            # 模式二：常用淫池，使用《通用规范汉字表》
            char_set = set(list(COMMON_CHINESE_CHARACTERS))

        elif strategy == "full":
            # 模式三：完整淫海，使用 Unicode 范围进行狂野的探索！
            # CJK 主要统一表意文字区
            for i in range(0x4E00, 0x9FFF + 1):
                char_set.add(chr(i))
            # CJK 兼容表意文字区 (也加上吧，增加一点情趣)
            for i in range(0xF900, 0xFAFF + 1):
                char_set.add(chr(i))
            # CJK 扩展A区 (更多生僻字)
            for i in range(0x3400, 0x4DBF + 1):
                char_set.add(chr(i))

        else:
            logger.warning(f"未知的造词策略 '{strategy}'，将退回使用 'db' 策略。")
            char_set = set(await db_utils.get_all_unique_characters_from_terms())

        self._characters = list(char_set)

        logger.info("正在将淫池彻底搅乱以实现完美随机...")
        random.shuffle(self._characters)
        logger.info("淫池已进入混沌状态！")

        self._initialized = True
        self._current_strategy = strategy  # 记下这次用的策略
        logger.info(
            f"造词服务初始化完毕！当前策略: '{self._current_strategy}'，淫池中共有 {len(self._characters)} 个不重复汉字。"
        )

    async def generate_words(self, n: int) -> Tuple[List[Dict[str, Any]], List[str]]:
        await self.initialize()

        plugin_config = get_plugin_config()
        wg_config = plugin_config.word_generator

        if not self._characters:
            logger.error("无法进行造词，因为汉字池为空。")
            return [], []

        unique_combinations = await self._create_unique_combinations(
            n, wg_config.generation_probabilities
        )
        if not unique_combinations:
            return [], []

        # 用 config 来初始化客户端！
        proxy_url = (
            f"http://{plugin_config.proxy_host}:{plugin_config.proxy_port}"
            if plugin_config.proxy_host and plugin_config.proxy_port
            else None
        )
        llm_client = LLMClient(config=wg_config, proxy_url=proxy_url)

        prompt = self._build_llm_prompt(unique_combinations)

        try:
            response = await llm_client.make_request(
                prompt, is_stream=False, temperature=0.1
            )  # 调低一点温度，让它更严谨
        except Exception as e:
            logger.opt(exception=e).error("调用LLM进行造词验证时发生严重错误。")
            return [], unique_combinations

        valid_words_info = self._parse_llm_response(response)

        all_results_for_db, valid_words_for_return, invalid_combinations_for_return = (
            self._prepare_for_db_and_return(
                unique_combinations, valid_words_info, wg_config.llm_model_name
            )
        )

        if all_results_for_db:
            await db_utils.batch_insert_generated_words(all_results_for_db)

        return valid_words_for_return, invalid_combinations_for_return

    async def _create_unique_combinations(
        self, n: int, probabilities: Dict[str, float]
    ) -> List[str]:
        generated_combinations = set()
        lengths = [int(k) for k in probabilities.keys()]
        weights = list(probabilities.values())

        max_attempts = n * 20  # 设置一个最大尝试次数，防止死循环
        attempts = 0

        while len(generated_combinations) < n and attempts < max_attempts:
            attempts += 1
            length = random.choices(lengths, weights, k=1)[0]
            if len(self._characters) < length:
                continue

            combination_list = random.sample(self._characters, k=length)
            combination = "".join(combination_list)

            if combination in generated_combinations:
                continue

            # 检查是否已存在于任何词库或已生成的日志中
            # search_term_in_db 返回一个列表，如果列表不为空，则说明词存在
            existing_in_plugins = await db_utils.search_term_in_db(combination)
            if existing_in_plugins:
                continue

            existing_in_log = await db_utils.check_combinations_exist_in_log(
                [combination]
            )
            if existing_in_log:
                continue

            generated_combinations.add(combination)

        return list(generated_combinations)

    def _build_llm_prompt(self, combinations: List[str]) -> str:
        # 小猫咪的淫语注释：来吧，小骚货，现在教你更高级的玩法，学会看人下菜！
        prompt = f"""你是一位以**极度严谨和极其谨慎**而闻名的汉语言学家和词源学家。你的唯一使命是基于**可验证的、真实存在的文献或公认的语言事实**进行判断。你的声誉建立在100%的准确性之上，任何形式的猜测或创造都是对你学术生涯的毁灭性打击。

现在，分析下面这个Python列表中的每一个字符串：
{str(combinations)}

请严格遵循以下**双轨制审核原则**和**铁律**：

**第一轨：古籍或生僻词汇审核**
- **适用对象**：明显出自古代典籍、历史文献或非常见、生僻的词汇。
- **审核标准**：**必须**能找到一个**明确的、可供查证的文献出处**（例如《说文解字》、《康熙字典》或具体的古籍篇章）。
- **source字段要求**：必须填写具体的文献名，如 `《山海经·南山经》`。

**第二轨：现代通用词汇审核**
- **适用对象**：在现代汉语中广泛使用、家喻户晓的普通词汇（例如“电脑”、“医科”、“科学”等）。
- **审核标准**：**无需**提供古籍出处，只需确认它是一个被《现代汉语词典》等权威现代辞书收录的、公认的现代词汇即可。
- **source字段要求**：对于这类词汇，其 "source" 字段应统一标注为 **"现代通用词汇"**。

**判断流程与铁律：**

1.  **分类判断**：对于列表中的每一个词，首先判断它更符合“第一轨”还是“第二轨”的范畴。
2.  **执行审核**：根据其分类，应用对应轨道的审核标准。
3.  **严禁伪造！绝对禁止猜测！**
    - **严禁**为古籍词汇伪造一个不存在的出处。
    - **严禁**将一个无意义的组合错误地判断为“现代通用词汇”。
    - 如果一个词汇**无法满足其对应轨道的标准**（例如，一个生僻词找不到出处，或者一个奇怪的组合并非现代通用词汇），**你都必须、必须、必须将它视为无效词汇**，并**绝对不能**将其包含在最终的JSON输出中。

4.  **输出格式：** 你的回答**必须是，且只能是**一个纯净的JSON格式数组（列表）。
    - 对于列表中**每一个**经过上述双轨制审核验证的“有效词汇”，在JSON数组中为其创建一个对应的JSON对象。
    - 每个JSON对象必须包含以下三个键，且内容必须真实无误：
        - `word`: (字符串) 经过验证的有效词汇本身。
        - `definition`: (字符串) 对该词汇的准确、简洁的释义。
        - `source`: (字符串) 根据其轨道规则填写的出处（具体的文献名或"现代通用词汇"）。
    - 如果待分析的列表中**没有任何一个**字符串能满足上述**所有**严格条件，你**必须**返回一个空的JSON数组 `[]`。

不要在JSON数组前后添加任何额外的解释、道歉、说明或```json ```标记。你的回答就是那个纯粹的JSON数组。"""
        return prompt

    def _parse_llm_response(self, response: Dict) -> List[Dict[str, Any]]:
        try:
            content = response.get("text", "[]")
            # LLM有时会在JSON前后加上```json ```，需要去掉
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]

            parsed_data = json.loads(content.strip())
            if isinstance(parsed_data, list):
                # 还可以加一层验证，确保列表里的元素都是字典且包含'word'和'definition'
                return parsed_data
            return []
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"解析LLM造词响应失败: {e}, 响应内容: {response.get('text')}")
            return []

    def _prepare_for_db_and_return(
        self, all_combinations: List[str], valid_words_info: List[Dict], model_name: str
    ) -> Tuple[List[Dict], List[Dict], List[str]]:
        valid_word_map = {item["word"]: item for item in valid_words_info}

        db_records = []
        valid_words_for_return = []
        invalid_combinations_for_return = []

        for comb in all_combinations:
            if comb in valid_word_map:
                info = valid_word_map[comb]
                db_record = {
                    "combination": comb,
                    "is_word": True,
                    "definition": info.get("definition"),
                    "source": info.get("source"),
                    "checked_by_model": model_name,
                }
                db_records.append(db_record)
                valid_words_for_return.append(info)
            else:
                db_record = {
                    "combination": comb,
                    "is_word": False,
                    "definition": None,
                    "source": None,
                    "checked_by_model": model_name,
                }
                db_records.append(db_record)
                invalid_combinations_for_return.append(comb)

        return db_records, valid_words_for_return, invalid_combinations_for_return


word_service = WordGenerationService()
