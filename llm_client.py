import asyncio
import logging
import random
import time
from typing import TypedDict, Unpack, Optional, List
from .config import WordGeneratorSetting

import aiohttp

# --- 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)


# --- 定义 TypedDict 用于 default_generation_config ---
class GenerationParams(TypedDict, total=False):
    temperature: float
    maxOutputTokens: int
    top_p: float
    top_k: int
    stop_sequences: list[str]
    candidate_count: int
    presence_penalty: float
    frequency_penalty: float
    seed: int
    user: str
    response_mime_type: str


# --- 异常类 ---
class LLMClientError(Exception):
    pass


class APIKeyError(LLMClientError):
    pass


class NetworkError(LLMClientError):
    pass


class RateLimitError(NetworkError):
    def __init__(
        self, message: str, status_code: int = 429, key_identifier: str | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.key_identifier = key_identifier


class PermissionDeniedError(NetworkError):
    def __init__(
        self, message: str, status_code: int, key_identifier: str | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.key_identifier = key_identifier


class APIResponseError(LLMClientError):
    pass


# --- 默认值 ---
DEFAULT_CHAT_COMPLETIONS_ENDPOINT_OPENAI: str = "/chat/completions"
DEFAULT_RATE_LIMIT_DISABLE_SECONDS: int = 30 * 60


class LLMClient:
    """一个为OpenAI API风格设计的、完全由config.toml驱动的精简LLM客户端。"""

    def __init__(
        self,
        config: WordGeneratorSetting,
        proxy_url: Optional[str] = None,
        rate_limit_disable_duration_seconds: int = DEFAULT_RATE_LIMIT_DISABLE_SECONDS,
        **kwargs: Unpack[GenerationParams],
    ) -> None:
        self.default_generation_config: GenerationParams = kwargs

        self.model_name: str = config.llm_model_name
        self.base_url: str = config.llm_base_url.rstrip("/")
        self.api_keys_config: List[str] = config.llm_api_keys

        if not self.api_keys_config:
            raise APIKeyError("造词功能配置中未提供任何API密钥 (llm_api_keys)。")

        self.rate_limit_disable_duration_seconds = rate_limit_disable_duration_seconds
        self._temporarily_disabled_keys_429: dict[str, float] = {}
        self._abandoned_keys_runtime: set[str] = set()

        self.endpoint_path = DEFAULT_CHAT_COMPLETIONS_ENDPOINT_OPENAI
        self.proxy_url = proxy_url

        logger.info(
            f"LLMClient 初始化完成。模型: {self.model_name}, 代理: {self.proxy_url or '未配置'}"
        )

    def _prepare_request_data(
        self, prompt: str, final_generation_config: GenerationParams
    ) -> tuple[dict, dict]:
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
        }
        for k, v in final_generation_config.items():
            if k == "maxOutputTokens":
                payload["max_tokens"] = v
            elif k == "stop_sequences":
                payload["stop"] = v
            elif k == "candidate_count":
                payload["n"] = v
            else:
                payload[k] = v
        return headers, payload

    def _parse_response(self, response_json: dict) -> dict:
        choice = response_json.get("choices", [{}])[0]
        message = choice.get("message", {})
        return {
            "text": message.get("content"),
            "finish_reason": choice.get("finish_reason"),
            "usage": response_json.get("usage"),
            "raw_response": response_json,
        }

    async def _make_api_call_attempt(
        self, session: aiohttp.ClientSession, api_key: str, headers: dict, payload: dict
    ) -> dict:
        full_url = f"{self.base_url}{self.endpoint_path}"
        final_headers = headers.copy()
        final_headers["Authorization"] = f"Bearer {api_key}"

        async with session.post(
            full_url,
            headers=final_headers,
            json=payload,
            proxy=self.proxy_url,
            timeout=180,
        ) as response:
            status_code = response.status
            key_info = f"...{api_key[-4:]}"

            if status_code == 200:
                response_json = await response.json()
                return self._parse_response(response_json)

            if status_code == 401 or status_code == 403:
                raise PermissionDeniedError(
                    f"权限错误 ({status_code}) - Key {key_info}",
                    status_code,
                    key_identifier=api_key,
                )
            if status_code == 429:
                raise RateLimitError(
                    f"速率限制 ({status_code}) - Key {key_info}", key_identifier=api_key
                )

            raise APIResponseError(f"API错误，状态码: {status_code}, Key: {key_info}")

    async def make_request(
        self,
        prompt: str,
        is_stream: bool = False,
        max_retries: int = 3,
        **kwargs: Unpack[GenerationParams],
    ) -> dict:
        # 小猫咪的淫语注释：这个函数现在只为非流式服务，因为哥哥的造词需求就是这样~
        if is_stream:
            raise NotImplementedError("这个精简版的客户端不支持流式输出哦~")

        async with aiohttp.ClientSession() as session:
            available_keys = self.api_keys_config[:]
            last_exception = None

            final_gen_config = self.default_generation_config.copy()
            final_gen_config.update(kwargs)

            for attempt in range(max_retries):
                current_time = time.time()
                keys_to_reactivate = [
                    k
                    for k, ts in self._temporarily_disabled_keys_429.items()
                    if ts <= current_time
                ]
                for k in keys_to_reactivate:
                    del self._temporarily_disabled_keys_429[k]

                active_keys = [
                    k
                    for k in available_keys
                    if k not in self._abandoned_keys_runtime
                    and k not in self._temporarily_disabled_keys_429
                ]
                if not active_keys:
                    logger.error("已无任何可用API密钥。")
                    break

                random.shuffle(active_keys)

                for key in active_keys:
                    try:
                        headers, payload = self._prepare_request_data(
                            prompt, final_gen_config
                        )
                        logger.info(f"第 {attempt + 1} 轮尝试，使用密钥 ...{key[-4:]}")
                        result = await self._make_api_call_attempt(
                            session, key, headers, payload
                        )
                        return result
                    except PermissionDeniedError as e:
                        logger.error(
                            f"密钥 ...{e.key_identifier[-4:]} 权限错误，永久禁用。"
                        )
                        self._abandoned_keys_runtime.add(e.key_identifier)
                        last_exception = e
                    except RateLimitError as e:
                        logger.warning(
                            f"密钥 ...{e.key_identifier[-4:]} 速率限制，临时禁用。"
                        )
                        self._temporarily_disabled_keys_429[e.key_identifier] = (
                            time.time() + self.rate_limit_disable_duration_seconds
                        )
                        last_exception = e
                    except (NetworkError, APIResponseError, Exception) as e:
                        logger.warning(f"使用密钥 ...{key[-4:]} 时发生错误: {e}")
                        last_exception = e

                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)  # 指数退避

            if last_exception:
                raise last_exception
            raise LLMClientError("所有API请求尝试均失败。")
