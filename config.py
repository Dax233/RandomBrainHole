import tomllib
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from pathlib import Path
from nonebot import logger as nb_logger


# 插件配置项模型
class PluginSetting(BaseModel):
    name: str
    module_name: str
    info_function_name: str
    format_function_name: str
    table_name: str
    search_column_name: str = "term"
    keywords: List[str]
    folder_name: str
    file_extensions: List[str]
    retry_attempts: int = 2
    failure_message: str


# 造词功能的专属配置模型 (已更新，包含了LLM的所有配置)
class WordGeneratorSetting(BaseModel):
    enabled: bool = True
    llm_model_name: str = "deepseek-v2"
    llm_base_url: str = "https://api.siliconflow.cn/v1"  # LLM的入口地址
    llm_api_keys: List[str] = Field(default_factory=list)  # 用来捅穿LLM的钥匙们！
    max_combinations_per_request: int = 100
    generation_probabilities: Dict[str, float] = Field(
        default_factory=lambda: {"2": 0.80, "4": 0.15, "3": 0.05}
    )


# 主配置模型 (已更新，加入了代理配置)
class Config(BaseModel):
    base_data_path: Optional[str] = None
    database_path: str = "random_brainhole_data.db"
    plugins: List[PluginSetting] = Field(default_factory=list)
    word_generator: WordGeneratorSetting = Field(default_factory=WordGeneratorSetting)
    # 新增：全局代理配置，我们的秘密通道~
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None


plugin_root_path = Path(__file__).parent.resolve()
config_file_path = plugin_root_path / "config.toml"
plugin_config_instance: Config


def _load_config_internal() -> Config:
    if not config_file_path.exists():
        nb_logger.error(f"配置文件 {config_file_path} 未找到。请根据模板创建。")
        raise FileNotFoundError(f"配置文件 {config_file_path} 未找到。")
    try:
        with open(config_file_path, "rb") as f:
            data = tomllib.load(f)
        loaded_config = Config(**data)

        if (
            not loaded_config.base_data_path
            or loaded_config.base_data_path == "your/base/data/path/"
        ):
            nb_logger.warning(
                f"配置文件 {config_file_path} 中的 base_data_path 未正确配置。"
            )

        if not loaded_config.database_path:
            nb_logger.warning(
                f"配置文件 {config_file_path} 中的 database_path 未配置，将使用默认值。"
            )
            loaded_config.database_path = "random_brainhole_data.db"

        for p_setting in loaded_config.plugins:
            if not p_setting.table_name:
                raise ValueError(f"插件 '{p_setting.name}' 缺少 'table_name' 配置。")
            if not p_setting.format_function_name:
                raise ValueError(
                    f"插件 '{p_setting.name}' 缺少 'format_function_name' 配置。"
                )

        return loaded_config
    except ValueError as ve:
        nb_logger.opt(exception=ve).error(
            f"加载配置文件 {config_file_path} 失败，配置项校验错误。"
        )
        raise
    except Exception as e:
        nb_logger.opt(exception=e).error(f"加载配置文件 {config_file_path} 失败。")
        raise


try:
    nb_logger.info("RandomBrainHole: 正在加载插件配置 (config.py)...")
    globals()["plugin_config_instance"] = _load_config_internal()
    _db_path_info = plugin_root_path / globals()["plugin_config_instance"].database_path
    nb_logger.info(
        f"RandomBrainHole: 插件配置加载完毕。数据库路径将是: {_db_path_info}"
    )
except Exception as e:
    nb_logger.opt(exception=e).critical(
        "RandomBrainHole: 初始化配置时发生严重错误 (config.py)。"
    )
    raise RuntimeError(f"RandomBrainHole 配置加载失败: {e}") from e


def get_plugin_config() -> Config:
    if (
        "plugin_config_instance" not in globals()
        or globals()["plugin_config_instance"] is None
    ):
        nb_logger.critical("RandomBrainHole: 配置对象未被初始化！")
        try:
            globals()["plugin_config_instance"] = _load_config_internal()
            nb_logger.warning("RandomBrainHole: 配置对象已尝试重新加载。")
        except Exception as e:
            raise RuntimeError(f"RandomBrainHole 插件配置未成功加载且无法重新加载: {e}")
    return globals()["plugin_config_instance"]


def get_database_full_path() -> Path:
    config = get_plugin_config()
    db_path = Path(config.database_path)
    if not db_path.is_absolute():
        db_path = plugin_root_path / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path
