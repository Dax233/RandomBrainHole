import tomllib 
from typing import List, Optional
from pydantic import BaseModel, Field
from pathlib import Path
from nonebot import logger as nb_logger # 使用 NoneBot 的 logger

# 插件配置项模型
class PluginSetting(BaseModel):
    name: str # 插件的友好名称
    module_name: str # 对应的 Python 模块名 (不含 .py)
    info_function_name: str # 模块内处理随机信息的主函数名
    format_function_name: str # 新增：模块内处理特定词条格式化的函数名
    table_name: str  # 此插件对应数据库中的表名
    search_column_name: str = "term" # 新增：用于搜索的列名，默认为 "term"
    keywords: List[str] # 触发此插件的关键词列表
    folder_name: str # (主要供 import_data.py 使用) 数据文件所在文件夹名称
    file_extensions: List[str] # (主要供 import_data.py 使用) 支持的文件扩展名
    retry_attempts: int = 2 # 获取数据失败时的重试次数
    failure_message: str # 最终失败时发送的消息

# 主配置模型
class Config(BaseModel):
    base_data_path: Optional[str] = None # (主要供 import_data.py 使用)
    database_path: str = "random_brainhole_data.db" # 数据库文件路径
    plugins: List[PluginSetting] = Field(default_factory=list)

# 获取插件的根目录
plugin_root_path = Path(__file__).parent.resolve()
# 定义 config.toml 文件的路径
config_file_path = plugin_root_path / "config.toml"

# 全局配置实例变量
plugin_config_instance: Config

def _load_config_internal() -> Config:
    """内部函数：加载 config.toml 文件并解析配置。"""
    if not config_file_path.exists():
        nb_logger.error(f"配置文件 {config_file_path} 未找到。请根据模板创建。")
        raise FileNotFoundError(f"配置文件 {config_file_path} 未找到。")
    try:
        with open(config_file_path, "rb") as f: 
            data = tomllib.load(f)
        loaded_config = Config(**data)

        # 校验 base_data_path (主要用于数据导入脚本)
        if not loaded_config.base_data_path or loaded_config.base_data_path == "your/base/data/path/":
            nb_logger.warning(f"配置文件 {config_file_path} 中的 base_data_path 未正确配置或仍为默认值 (此配置主要影响数据导入脚本)。")
        
        # 校验 database_path
        if not loaded_config.database_path:
            nb_logger.warning(f"配置文件 {config_file_path} 中的 database_path 未配置，将使用默认值 'random_brainhole_data.db'。")
            loaded_config.database_path = "random_brainhole_data.db" # 确保有个值

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
        raise
    except Exception as e:
        nb_logger.opt(exception=e).error(f"加载配置文件 {config_file_path} 失败。")
        raise

# 在模块首次导入时加载配置
try:
    nb_logger.info("RandomBrainHole: 正在加载插件配置 (config.py)...")
    globals()['plugin_config_instance'] = _load_config_internal()
    # 访问全局变量 plugin_config_instance 来打印路径
    _db_path_info = plugin_root_path / globals()['plugin_config_instance'].database_path
    nb_logger.info(f"RandomBrainHole: 插件配置加载完毕。数据库路径将是: {_db_path_info}")
except Exception as e:
    # 使用 opt(exception=True) 来包含异常信息
    nb_logger.opt(exception=e).critical(f"RandomBrainHole: 初始化配置时发生严重错误 (config.py)。")
    # 抛出异常，因为配置对于插件至关重要
    raise RuntimeError(f"RandomBrainHole 配置加载失败: {e}") from e


def get_plugin_config() -> Config:
    """获取已加载的插件配置。"""
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
    """获取数据库文件的绝对路径。"""
    config = get_plugin_config() # 使用函数获取配置实例
    db_path = Path(config.database_path)
    if not db_path.is_absolute():
        # 相对于插件根目录构建路径
        db_path = plugin_root_path / db_path
    
    # 确保数据库文件的父目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path
