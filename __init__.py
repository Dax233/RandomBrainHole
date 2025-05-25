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
    config=Config, # 关联配置模型
    supported_adapters={"~onebot.v11"}, # 明确支持的适配器
)

# 定义启动和关闭时执行的异步函数
async def _initialize_database_on_startup():
    """在 NoneBot 启动时初始化数据库表"""
    # 延迟导入，确保 config 已加载完毕
    from .db_utils import create_tables_if_not_exists, get_db_connection
    from .config import get_database_full_path # 确保从这里获取路径
    
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 正在初始化数据库...")
    try:
        db_path = get_database_full_path()
        # 传递数据库路径给 get_db_connection 以确保连接到正确的数据库
        # 并将连接传递给 create_tables_if_not_exists
        conn = get_db_connection(db_path=db_path) 
        create_tables_if_not_exists(conn) 
        logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 数据库初始化完毕。")
    except Exception as e:
        logger.opt(exception=e).critical(f"RandomBrainHole ({__plugin_meta__.name}): 数据库初始化失败！插件可能无法正常工作。")

async def _close_database_connection_on_shutdown():
    """在 NoneBot 关闭时关闭数据库连接"""
    from .db_utils import close_db_connection # 局部导入
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 正在关闭数据库连接...")
    close_db_connection()

# 注册生命周期钩子
try:
    driver = get_driver()
    driver.on_startup(_initialize_database_on_startup)
    driver.on_shutdown(_close_database_connection_on_shutdown)
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 已成功注册数据库启动和关闭钩子。")
except RuntimeError: 
    # 在某些环境 (例如，如果 get_driver() 在插件加载时尚未完全准备好，或者在非 NoneBot 主进程中导入此模块)
    # get_driver() 可能引发 RuntimeError。
    logger.warning(f"RandomBrainHole ({__plugin_meta__.name}): 获取 Driver 实例失败（可能在非 NoneBot 运行时环境）。数据库的自动初始化和关闭钩子可能未注册。")
except Exception as e:
    logger.error(f"RandomBrainHole ({__plugin_meta__.name}): 注册数据库启动/关闭钩子时发生错误: {e}")


# 1. 加载配置 (config.py 在导入时已处理)
#    这里主要是获取配置实例并进行必要的日志记录或检查
try:
    plugin_config_instance = get_plugin_config() # 这会触发 config.py 中的加载逻辑（如果尚未加载）
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 插件配置已加载，正在初始化主逻辑...")
    # 配置项的警告已在 config.py 中处理
except RuntimeError as e: 
    logger.critical(f"RandomBrainHole: 获取配置失败，插件初始化中止: {e}")
    raise # 重新抛出异常，阻止插件在配置错误时继续加载
except Exception as e:
    logger.opt(exception=e).critical(f"RandomBrainHole: 初始化时加载或验证配置失败。插件可能无法正常工作。")
    raise


# 2. 创建插件处理器
try:
    from .plugin_loader import create_plugin_handlers # 确保 plugin_loader 也被更新
    create_plugin_handlers() 
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 消息处理器创建完毕。")
except Exception as e:
    logger.opt(exception=e).error(f"RandomBrainHole: 创建插件消息处理器时发生错误。")
    # 可以考虑是否在此处也抛出异常，以指示插件加载不完全
