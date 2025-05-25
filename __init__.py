from nonebot import get_driver 
from nonebot.plugin import PluginMetadata
from nonebot.log import logger # 导入 NoneBot 的 logger

# 从同级模块导入
from .config import Config, get_plugin_config # get_plugin_config 会在首次调用时加载配置
# plugin_loader 和 db_utils 会在需要时动态导入或在钩子函数中导入，以避免循环导入或过早初始化

# 定义插件元数据，用于 NoneBot 插件商店等场景展示信息
__plugin_meta__ = PluginMetadata(
    name="RandomBrainHole", # 插件名称
    description="这是一个随机输出各种自定义词库信息的插件集合 (数据库版)", # 插件描述
    usage="根据 config.toml 中配置的关键词触发，例如“随机脑洞”、“查词 词条”、“随机填词 模板[词库名]”", # 插件使用方法
    type="application", # 插件类型，"application" 表示应用类插件
    homepage="https://github.com/Dax233/RandomBrainHole", # 插件项目主页
    config=Config, # 关联 Pydantic 配置模型，NoneBot 会自动生成配置模板
    supported_adapters={"~onebot.v11"}, # 明确支持的适配器，例如 OneBot V11
)

# --- 生命周期钩子函数 ---

async def _initialize_database_on_startup():
    """
    在 NoneBot 启动时执行的异步函数。
    主要负责初始化数据库连接和创建数据表结构。
    """
    # 延迟导入，确保 config 已加载完毕，并避免在模块顶层过早执行数据库操作
    from .db_utils import create_tables_if_not_exists, get_db_connection
    from .config import get_database_full_path # 确保从这里获取数据库的绝对路径
    
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 正在初始化数据库...")
    try:
        db_path = get_database_full_path() # 获取数据库文件路径
        # 传递数据库路径给 get_db_connection 以确保连接到正确的数据库
        # 并将连接传递给 create_tables_if_not_exists
        conn = get_db_connection(db_path=db_path) # 获取数据库连接
        create_tables_if_not_exists(conn) # 创建所有在 db_utils.ALL_TABLE_SCHEMAS 中定义的表
        logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 数据库初始化完毕。")
    except Exception as e:
        logger.opt(exception=e).critical(f"RandomBrainHole ({__plugin_meta__.name}): 数据库初始化失败！插件可能无法正常工作。")
        # 此处不应重新抛出异常，否则可能导致 NoneBot 启动失败

async def _close_database_connection_on_shutdown():
    """
    在 NoneBot 关闭时执行的异步函数。
    负责关闭数据库连接，释放资源。
    """
    from .db_utils import close_db_connection # 局部导入，在需要时才导入
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 正在关闭数据库连接...")
    close_db_connection() # 调用 db_utils 中的关闭连接函数

# --- 注册生命周期钩子 ---
# 使用 try-except 块来处理在非标准 NoneBot 环境中 (如测试、独立脚本执行) 可能发生的错误
try:
    driver = get_driver() # 获取 NoneBot Driver 实例
    # 注册启动钩子，在 NoneBot 启动完成后调用 _initialize_database_on_startup
    driver.on_startup(_initialize_database_on_startup)
    # 注册关闭钩子，在 NoneBot 关闭前调用 _close_database_connection_on_shutdown
    driver.on_shutdown(_close_database_connection_on_shutdown)
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 已成功注册数据库启动和关闭钩子。")
except RuntimeError: 
    # 在某些环境 (例如，如果 get_driver() 在插件加载时尚未完全准备好，
    # 或者在非 NoneBot 主进程中导入此模块，例如直接运行 import_data.py 时)
    # get_driver() 可能引发 RuntimeError。
    logger.warning(f"RandomBrainHole ({__plugin_meta__.name}): 获取 Driver 实例失败（可能在非 NoneBot 运行时环境）。数据库的自动初始化和关闭钩子可能未注册。")
except Exception as e:
    logger.error(f"RandomBrainHole ({__plugin_meta__.name}): 注册数据库启动/关闭钩子时发生错误: {e}")


# --- 插件主逻辑初始化 ---

# 1. 加载配置 (config.py 在其被导入时已自动加载配置到全局变量)
#    这里主要是获取配置实例并进行必要的日志记录或检查。
try:
    # 调用 get_plugin_config() 会确保配置已加载（如果尚未加载），并返回配置实例。
    # config.py 内部有日志记录配置加载过程。
    plugin_config_instance = get_plugin_config() 
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 插件配置已加载，正在初始化主逻辑...")
    # 关于配置项的警告和错误已在 config.py 的 _load_config_internal 函数中处理。
except RuntimeError as e: 
    # 如果 get_plugin_config 内部的 _load_config_internal 抛出 RuntimeError (例如文件找不到或解析严重错误)
    logger.critical(f"RandomBrainHole: 获取或加载配置失败，插件初始化中止: {e}")
    raise # 重新抛出异常，阻止插件在配置错误时继续加载和运行
except Exception as e:
    # 捕获其他在配置加载或验证过程中可能发生的未知异常
    logger.opt(exception=e).critical(f"RandomBrainHole: 初始化时加载或验证配置失败。插件可能无法正常工作。")
    raise # 重新抛出，以明确指示插件初始化失败


# 2. 创建插件的消息处理器
#    这通常涉及到从 plugin_loader.py 中导入并调用一个函数来设置 on_message 监听器。
try:
    from .plugin_loader import create_plugin_handlers # 导入创建处理器集合的函数
    create_plugin_handlers() # 调用该函数，注册消息处理器
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 消息处理器创建完毕。")
except Exception as e:
    logger.opt(exception=e).error(f"RandomBrainHole: 创建插件消息处理器时发生错误。")
    # 可以考虑是否在此处也抛出异常，以指示插件加载不完全或失败。
    # 如果消息处理器是插件核心功能，抛出异常可能是合理的。
    # raise
