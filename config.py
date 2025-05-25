import tomllib 
from typing import List, Optional
from pydantic import BaseModel, Field
from pathlib import Path

# 插件配置项模型
class PluginSetting(BaseModel):
    name: str
    module_name: str
    info_function_name: str # 在运行时，此函数将从数据库获取信息
    keywords: List[str]
    folder_name: str #供 import_data.py 使用
    file_extensions: List[str] #供 import_data.py 使用
    retry_attempts: int = 2
    failure_message: str

# 主配置模型
class Config(BaseModel):
    base_data_path: Optional[str] = None
    database_path: str = "random_brainhole_data.db" 
    plugins: List[PluginSetting] = Field(default_factory=list)

# 获取插件的根目录
plugin_root_path = Path(__file__).parent.resolve()
# 定义 config.toml 文件的路径
config_file_path = plugin_root_path / "config.toml"

# 全局配置实例
plugin_config_instance: Config # 修改变量名以区分函数

def _load_config_internal() -> Config:
    """
    内部函数：加载 config.toml 文件并解析配置。
    """
    if not config_file_path.exists():
        print(f"[CONFIG_ERROR] 配置文件 {config_file_path} 未找到。请根据模板创建。")
        raise FileNotFoundError(f"配置文件 {config_file_path} 未找到。请根据模板创建。")

    try:
        with open(config_file_path, "rb") as f: 
            data = tomllib.load(f)
        loaded_config = Config(**data)

        if not loaded_config.base_data_path or loaded_config.base_data_path == "your/base/data/path/":
            print(f"[CONFIG_WARNING] 配置文件 {config_file_path} 中的 base_data_path 未正确配置或仍为默认值。")
        
        if not loaded_config.database_path:
            print(f"[CONFIG_WARNING] 配置文件 {config_file_path} 中的 database_path 未配置，将使用默认值 'random_brainhole_data.db'。")
            loaded_config.database_path = "random_brainhole_data.db"

        return loaded_config
    except Exception as e:
        print(f"[CONFIG_ERROR] 加载配置文件 {config_file_path} 失败: {e}")
        raise

# 在模块首次导入时加载配置
try:
    print("[CONFIG] RandomBrainHole: 正在加载插件配置 (config.py)...")
    # 将加载的配置赋值给全局变量 plugin_config_instance
    globals()['plugin_config_instance'] = _load_config_internal()
    # 访问全局变量 plugin_config_instance 来打印路径
    _db_path_info = plugin_root_path / globals()['plugin_config_instance'].database_path if 'plugin_config_instance' in globals() and globals()['plugin_config_instance'] else 'Unknown'
    print(f"[CONFIG] RandomBrainHole: 插件配置加载完毕。数据库路径将是: {_db_path_info}")
except Exception as e:
    print(f"[CONFIG_ERROR] RandomBrainHole: 初始化配置时发生严重错误 (config.py): {e}。")
    raise RuntimeError(f"RandomBrainHole 配置加载失败: {e}") from e


def get_plugin_config() -> Config:
    """
    获取已加载的插件配置。
    """
    if 'plugin_config_instance' not in globals() or globals()['plugin_config_instance'] is None:
        print("[CONFIG_CRITICAL] RandomBrainHole: 配置对象 plugin_config_instance 未被初始化！")
        # 尝试重新加载，但这通常表示启动顺序有问题
        try:
            globals()['plugin_config_instance'] = _load_config_internal()
            print("[CONFIG_WARNING] RandomBrainHole: 配置对象已尝试重新加载。")
        except Exception as e:
            raise RuntimeError(f"RandomBrainHole 插件配置未成功加载且无法重新加载: {e}")
    return globals()['plugin_config_instance']

def get_database_full_path() -> Path: # 重命名函数以更清晰地表示其作用
    """
    获取数据库文件的绝对路径。
    """
    config = get_plugin_config() 
    db_path = Path(config.database_path)
    if not db_path.is_absolute():
        # 相对于插件根目录构建路径
        db_path = plugin_root_path / db_path
    
    # 确保数据库文件的父目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path

