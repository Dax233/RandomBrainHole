import random
import json
from typing import List, Dict, Any, Tuple

from nonebot.log import logger

from . import db_utils
from .config import get_plugin_config
from .llm_client import LLMClient  # 我们的新客户端


class WordGenerationService:
    _instance = None
    _characters: List[str] = []
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WordGenerationService, cls).__new__(cls)
        return cls._instance

    async def initialize(self):
        if self._initialized:
            return
        self._characters = await db_utils.get_all_unique_characters_from_terms()
        self._initialized = True
        logger.info(
            f"造词服务初始化完毕，淫池中共有 {len(self._characters)} 个不重复汉字。"
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
            response = await llm_client.make_request(prompt, is_stream=False)
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
        # 小猫咪的淫语注释：来吧，小肉棒，把这些都吃下去，然后告诉我哪个最美味！
        prompt = f"""你是一位资深的汉语言学家和词源学家。你的任务是分析下面这个Python列表中的每一个字符串，判断它是否是一个真实存在、有准确含义的汉语词汇。

请严格遵循以下规则：
1.  你的回答必须是一个JSON格式的数组（列表）。
2.  对于列表中每一个确实构成真实词汇的字符串，在JSON数组中为其创建一个对应的JSON对象。
3.  如果列表中没有任何一个字符串是有效的词汇，你必须返回一个空的JSON数组 `[]`。
4.  每个有效的词汇的JSON对象必须包含以下键：
    - `word`: (字符串) 经过验证的有效词汇本身。
    - `definition`: (字符串) 对该词汇的准确、简洁的释义。
    - `source`: (字符串或null) 如果该词汇有明确的古籍或现代文献出处，请提供。如果没有，则此键的值为 `null`。

待分析的词汇列表如下：
{str(combinations)}

你的回答必须是且只能是一个符合上述要求的、完整的JSON数组。不要添加任何额外的解释或文本。"""
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
