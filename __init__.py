from nonebot import get_driver 
from nonebot.plugin import PluginMetadata
from nonebot.log import logger # 导入 NoneBot 的 logger

# 从同级模块导入
from .config import Config, get_plugin_config # get_plugin_config 会加载配置
# plugin_loader 和 db_utils 会在需要时导入或在钩子函数中导入

__plugin_meta__ = PluginMetadata(
    name="RandomBrainHole",
    description="这是一个随机输出各种自定义词库信息的插件集合 (数据库版)",
    usage="根据 config.toml 中配置的关键词触发，例如“随机脑洞”",
    type="application", 
    homepage="https://github.com/Dax233/RandomBrainHole", # 请替换为你的项目地址
    config=Config, 
    supported_adapters={"~onebot.v11"}, 
)

# 定义启动和关闭时执行的异步函数
async def _initialize_database_on_startup():
    """在 NoneBot 启动时初始化数据库表"""
    # 延迟导入，确保 config 已加载完毕
    from .db_utils import create_tables_if_not_exists, get_db_connection
    from .config import get_database_full_path
    
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 正在初始化数据库...")
    try:
        db_path = get_database_full_path()
        conn = get_db_connection(db_path=db_path) # 传递路径以确保连接到正确的数据库
        create_tables_if_not_exists(conn) # 传递连接
        logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 数据库初始化完毕。")
    except Exception as e:
        logger.opt(exception=e).critical(f"RandomBrainHole ({__plugin_meta__.name}): 数据库初始化失败！插件可能无法正常工作。")

async def _close_database_connection_on_shutdown():
    """在 NoneBot 关闭时关闭数据库连接"""
    from .db_utils import close_db_connection 
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 正在关闭数据库连接...")
    close_db_connection()

# 注册生命周期钩子
try:
    driver = get_driver()
    driver.on_startup(_initialize_database_on_startup)
    driver.on_shutdown(_close_database_connection_on_shutdown)
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 已成功注册数据库启动和关闭钩子。")
except RuntimeError: 
    logger.warning(f"RandomBrainHole ({__plugin_meta__.name}): 获取 Driver 实例失败（可能在非 NoneBot 运行时环境）。数据库的自动初始化和关闭钩子可能未注册。")
except Exception as e:
    logger.error(f"RandomBrainHole ({__plugin_meta__.name}): 注册数据库启动/关闭钩子时发生错误: {e}")


# 1. 加载配置 (config.py 在导入时已处理)
#    这里主要是获取配置实例并进行必要的日志记录或检查
try:
    plugin_config_instance = get_plugin_config() # 这会触发 config.py 中的加载逻辑（如果尚未加载）
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 插件配置已加载，正在初始化主逻辑...")
    if not plugin_config_instance.base_data_path or plugin_config_instance.base_data_path == "your/base/data/path/":
        logger.warning("RandomBrainHole: 关键配置项 base_data_path 未在 config.toml 中正确配置。数据导入脚本可能无法访问数据文件。")
    if not plugin_config_instance.database_path:
         logger.warning("RandomBrainHole: 关键配置项 database_path 未在 config.toml 中配置。")

except RuntimeError as e: 
    logger.critical(f"RandomBrainHole: 获取配置失败，插件初始化中止: {e}")
    raise 
except Exception as e:
    logger.opt(exception=e).critical(f"RandomBrainHole: 初始化时加载或验证配置失败。插件可能无法正常工作。")
    raise


# 2. 创建插件处理器 (这部分逻辑之后会修改为从数据库读取)
#    暂时保持原样，但其依赖的 info_func 需要重写
try:
    from .plugin_loader import create_plugin_handlers # 确保 plugin_loader 也被更新
    create_plugin_handlers() 
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 消息处理器创建完毕 (注意：目前仍可能使用旧的文件读取逻辑，待后续修改)。")
except Exception as e:
    logger.opt(exception=e).error(f"RandomBrainHole: 创建插件消息处理器时发生错误。")

