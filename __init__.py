from nonebot import get_driver
from nonebot.plugin import PluginMetadata
from nonebot.log import logger

# 从同级模块导入
from .config import Config, get_plugin_config

# 定义插件元数据
__plugin_meta__ = PluginMetadata(
    name="RandomBrainHole",
    description="一个随机输出各种自定义词库信息并能自动造词的插件集合",
    usage="关键词触发, 或使用 '查词', '随机填词', '造词' 等指令",
    type="application",
    homepage="https://github.com/Dax233/RandomBrainHole",
    config=Config,
    supported_adapters={"~onebot.v11"},
)


# --- 生命周期钩子函数 ---
async def _initialize_database_on_startup():
    from .db_utils import create_tables_if_not_exists, get_db_connection
    from .config import get_database_full_path

    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 正在初始化数据库...")
    try:
        db_path = get_database_full_path()
        conn = get_db_connection(db_path=db_path)
        create_tables_if_not_exists(conn)
        logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 数据库初始化完毕。")
    except Exception as e:
        logger.opt(exception=e).critical(
            f"RandomBrainHole ({__plugin_meta__.name}): 数据库初始化失败！"
        )


async def _close_database_connection_on_shutdown():
    from .db_utils import close_db_connection

    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 正在关闭数据库连接...")
    close_db_connection()


# --- 注册生命周期钩子 ---
try:
    driver = get_driver()
    driver.on_startup(_initialize_database_on_startup)
    driver.on_shutdown(_close_database_connection_on_shutdown)
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 已注册数据库生命周期钩子。")
except (RuntimeError, Exception) as e:
    logger.warning(
        f"RandomBrainHole ({__plugin_meta__.name}): 注册钩子失败，可能在非NoneBot环境: {e}"
    )

# --- 插件主逻辑初始化 ---
try:
    get_plugin_config()  # 确保配置被加载
    logger.info(
        f"RandomBrainHole ({__plugin_meta__.name}): 插件配置已加载，正在初始化主逻辑..."
    )

    # 1. 加载原有的关键词处理器
    from .plugin_loader import create_plugin_handlers

    create_plugin_handlers()
    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 关键词消息处理器创建完毕。")

    # 2. 导入新的指令处理器模块，NoneBot会自动加载其中的on_command
    # 小猫咪的淫语注释：把我们新的接待员也拉进来一起玩嘛~
    from .plugins import generator_handler  # noqa: F401

    logger.info(f"RandomBrainHole ({__plugin_meta__.name}): 造词指令处理器已加载。")

except Exception as e:
    logger.opt(exception=e).critical(
        "RandomBrainHole: 初始化插件时发生严重错误，插件可能无法正常工作。"
    )
    raise
