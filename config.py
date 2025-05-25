import tomllib 
from typing import List, Optional
from pydantic import BaseModel, Field
from pathlib import Path
from nonebot import logger as nb_logger # 使用 NoneBot 的 logger

# 插件配置项模型
class PluginSetting(BaseModel):
    """
    定义单个插件的配置结构。
    """
    name: str # 插件的友好名称，例如 "脑洞"
    module_name: str # 对应的 Python 模块名 (不含 .py 后缀)，例如 "brainhole"
    info_function_name: str # 模块内处理随机信息获取的主函数名，例如 "random_brainhole_info"
    format_function_name: str # 新增：模块内处理特定词条格式化的函数名，例如 "format_brainhole_data"
    table_name: str  # 此插件对应数据库中的表名，例如 "brainhole_terms"
    search_column_name: str = "term" # 新增：用于搜索的列名，默认为 "term"
    keywords: List[str] # 触发此插件的关键词列表，例如 ["随机脑洞", "来个脑洞"]
    folder_name: str # (主要供 import_data.py 使用) 数据文件所在文件夹名称，例如 "脑洞"
    file_extensions: List[str] # (主要供 import_data.py 使用) 支持的文件扩展名，例如 [".xlsx"]
    retry_attempts: int = 2 # 获取数据失败时的重试次数
    failure_message: str # 最终失败时发送的消息，例如 "今天脑洞枯竭了，请稍后再试吧！"

# 主配置模型
class Config(BaseModel):
    """
    定义整个插件的主配置结构。
    """
    base_data_path: Optional[str] = None # (主要供 import_data.py 使用) 词库数据文件的基础路径
    database_path: str = "random_brainhole_data.db" # 数据库文件路径，默认为 "random_brainhole_data.db"
    plugins: List[PluginSetting] = Field(default_factory=list) # 插件配置列表

# 获取插件的根目录
plugin_root_path = Path(__file__).parent.resolve()
# 定义 config.toml 文件的路径
config_file_path = plugin_root_path / "config.toml"

# 全局配置实例变量
# 这个变量将在模块加载时被赋值
plugin_config_instance: Config

def _load_config_internal() -> Config:
    """
    内部函数：加载 config.toml 文件并解析配置。
    该函数负责读取 TOML 文件，使用 Pydantic 模型进行数据验证和转换。
    同时，它还会对一些关键配置项进行校验，如路径和必要字段。

    :raises FileNotFoundError: 如果配置文件未找到。
    :raises ValueError: 如果配置项校验失败 (例如 Pydantic 验证错误或自定义的必要字段缺失)。
    :raises Exception: 其他加载或解析过程中发生的未知错误。
    :return: 解析后的 Config 对象。
    """
    if not config_file_path.exists():
        nb_logger.error(f"配置文件 {config_file_path} 未找到。请根据模板创建。")
        raise FileNotFoundError(f"配置文件 {config_file_path} 未找到。")
    try:
        with open(config_file_path, "rb") as f: # 以二进制读取模式打开 TOML 文件
            data = tomllib.load(f) # 解析 TOML 数据
        loaded_config = Config(**data) # 使用 Pydantic 模型进行数据验证和转换

        # 校验 base_data_path (主要用于数据导入脚本)
        if not loaded_config.base_data_path or loaded_config.base_data_path == "your/base/data/path/":
            nb_logger.warning(f"配置文件 {config_file_path} 中的 base_data_path 未正确配置或仍为默认值 (此配置主要影响数据导入脚本)。")
        
        # 校验 database_path
        if not loaded_config.database_path:
            nb_logger.warning(f"配置文件 {config_file_path} 中的 database_path 未配置，将使用默认值 'random_brainhole_data.db'。")
            loaded_config.database_path = "random_brainhole_data.db" # 确保有个默认值

        # 校验每个 plugin 的必要配置
        for p_setting in loaded_config.plugins:
            if not hasattr(p_setting, 'table_name') or not p_setting.table_name:
                nb_logger.error(f"插件 '{p_setting.name}' 在 config.toml 中缺少必要的 'table_name' 配置项。")
                raise ValueError(f"插件 '{p_setting.name}' 缺少 'table_name' 配置。")
            if not hasattr(p_setting, 'format_function_name') or not p_setting.format_function_name:
                nb_logger.error(f"插件 '{p_setting.name}' 在 config.toml 中缺少必要的 'format_function_name' 配置项。")
                raise ValueError(f"插件 '{p_setting.name}' 缺少 'format_function_name' 配置。")
            # search_column_name 有默认值 "term"，所以不强制检查，但可以提示如果它为空
            if not hasattr(p_setting, 'search_column_name') or not p_setting.search_column_name:
                 nb_logger.warning(f"插件 '{p_setting.name}' 未明确配置 'search_column_name'，将使用默认值 'term'。")

        return loaded_config
    except ValueError as ve: # 特别捕捉 Pydantic 校验错误或我们自己抛出的 ValueError
        nb_logger.opt(exception=ve).error(f"加载配置文件 {config_file_path} 失败，配置项校验错误。")
        raise # 重新抛出，以便上层能感知到配置错误
    except Exception as e: # 捕捉其他可能的异常，例如 tomllib 解析错误
        nb_logger.opt(exception=e).error(f"加载配置文件 {config_file_path} 失败。")
        raise # 重新抛出

# 在模块首次导入时加载配置
try:
    nb_logger.info("RandomBrainHole: 正在加载插件配置 (config.py)...")
    # 将加载的配置赋值给全局变量 plugin_config_instance
    globals()['plugin_config_instance'] = _load_config_internal()
    # 访问全局变量 plugin_config_instance 来打印数据库路径信息
    _db_path_info = plugin_root_path / globals()['plugin_config_instance'].database_path
    nb_logger.info(f"RandomBrainHole: 插件配置加载完毕。数据库路径将是: {_db_path_info}")
except Exception as e:
    # 使用 opt(exception=True) 来包含异常信息，便于调试
    nb_logger.opt(exception=e).critical(f"RandomBrainHole: 初始化配置时发生严重错误 (config.py)。插件可能无法正常启动。")
    # 抛出运行时异常，因为配置对于插件的正常运行至关重要
    raise RuntimeError(f"RandomBrainHole 配置加载失败: {e}") from e


def get_plugin_config() -> Config:
    """
    获取已加载的插件配置。
    这是一个公共接口，供插件的其他部分访问配置信息。
    它会检查配置是否已成功初始化，并在未初始化时尝试重新加载（尽管这通常表示启动流程有问题）。

    :raises RuntimeError: 如果配置对象未初始化且无法重新加载。
    :return: 已加载的 Config 对象。
    """
    if 'plugin_config_instance' not in globals() or globals()['plugin_config_instance'] is None:
        nb_logger.critical("RandomBrainHole: 配置对象 plugin_config_instance 未被初始化！这通常表示启动时加载配置失败。")
        # 尝试重新加载，但这通常表示启动顺序或依赖有问题
        try:
            globals()['plugin_config_instance'] = _load_config_internal()
            nb_logger.warning("RandomBrainHole: 配置对象已尝试重新加载。")
        except Exception as e:
            raise RuntimeError(f"RandomBrainHole 插件配置未成功加载且无法重新加载: {e}")
    return globals()['plugin_config_instance']

def get_database_full_path() -> Path:
    """
    获取数据库文件的绝对路径。
    如果配置文件中指定的路径是相对路径，则会相对于插件的根目录进行解析。
    同时，此函数会确保数据库文件所在的父目录存在。

    :return: 数据库文件的绝对路径 (Path 对象)。
    """
    config = get_plugin_config() # 使用函数获取配置实例，确保配置已加载
    db_path = Path(config.database_path) # 将字符串路径转换为 Path 对象

    if not db_path.is_absolute():
        # 如果是相对路径，则相对于插件根目录构建绝对路径
        db_path = plugin_root_path / db_path
    
    # 确保数据库文件的父目录存在，如果不存在则创建
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path
