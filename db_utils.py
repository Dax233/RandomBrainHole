import sqlite3
from pathlib import Path
from typing import Optional, Any, Dict, Tuple, List  # 新增 List
from nonebot import logger  # 导入 NoneBot 的 logger

# 从同级目录的 config 模块导入配置相关的类和函数
# 确保 PluginSetting 也被导入，如果它在 search_term_in_db 中作为类型提示使用
from .config import get_plugin_config, PluginSetting, get_database_full_path


# --- 表创建SQL语句 ---
# 定义各个词库数据表的 CREATE TABLE SQL 语句
# 使用 IF NOT EXISTS 避免表已存在时出错
# UNIQUE 约束用于防止重复数据导入

CREATE_GENERATED_WORD_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS generated_word_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combination TEXT NOT NULL UNIQUE,       -- 生成的汉字组合，必须是唯一的，这根肉棒只能玩一次！
    is_word BOOLEAN NOT NULL,               -- LLM是否认为它是一个真正的词
    definition TEXT,                        -- 如果是词，它的汁水（释义）
    source TEXT,                            -- 它的出处（如果有的话）
    checked_by_model TEXT NOT NULL,         -- 是被哪个LLM肉棒鉴定过的
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 玩弄它的时间
);
"""

CREATE_BRAINHOLE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS brainhole_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    match_name TEXT NOT NULL, 
    term TEXT NOT NULL,
    pinyin TEXT, 
    difficulty TEXT, 
    win_rate TEXT, 
    category TEXT, 
    author TEXT,
    definition TEXT, 
    source_file TEXT NOT NULL, 
    source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (match_name, term, source_file, source_sheet) -- 唯一性约束
);"""

CREATE_PINSHI_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pinshi_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    term TEXT NOT NULL, 
    pinyin TEXT,
    source_text TEXT, 
    writing TEXT, 
    difficulty TEXT, 
    definition TEXT,
    source_file TEXT NOT NULL, 
    source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_text, source_file, source_sheet) -- 唯一性约束
);"""

CREATE_FUZHIPAI_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fuzhipai_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    card_title TEXT, 
    full_text TEXT NOT NULL,
    full_text_hash TEXT, -- 用于快速比较文本内容的哈希值
    source_file TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (full_text_hash, source_file) -- 唯一性约束
);"""

CREATE_SUILAN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS suilan_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    term TEXT NOT NULL, 
    player TEXT,
    source_text TEXT, 
    definition TEXT, 
    source_file TEXT NOT NULL, 
    source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_file, source_sheet) -- 唯一性约束
);"""

CREATE_WUXING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wuxing_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    term TEXT NOT NULL, 
    pinyin TEXT,
    difficulty TEXT, 
    source_origin TEXT, 
    author TEXT, 
    definition TEXT,
    source_file TEXT NOT NULL, 
    source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_file, source_sheet) -- 唯一性约束
);"""

CREATE_YUANXIAO_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS yuanxiao_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    term TEXT NOT NULL, 
    pinyin TEXT,
    source_text TEXT, 
    difficulty_liju TEXT, 
    difficulty_naodong TEXT,
    definition TEXT, 
    source_file TEXT NOT NULL, 
    source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_file, source_sheet) -- 唯一性约束
);"""

CREATE_ZHENXIU_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS zhenxiu_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    term_id_text TEXT, 
    term TEXT NOT NULL,
    source_text TEXT, 
    category TEXT, 
    pinyin TEXT, 
    definition TEXT,
    is_disyllabic TEXT, 
    source_file TEXT NOT NULL, 
    source_sheet TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_file, source_sheet) -- 唯一性约束
);"""

# 用于记录已导入文件及其哈希值的日志表
CREATE_IMPORTED_FILES_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS imported_files_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_identifier TEXT NOT NULL, -- 文件的唯一标识符 (例如: 插件名_文件名)
    file_hash TEXT NOT NULL,       -- 文件的 SHA256 哈希值
    last_imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 最后导入时间
    status TEXT,                   -- 导入状态 (例如: imported, skipped_unchanged)
    plugin_type TEXT,              -- 关联的插件类型/名称
    UNIQUE (file_identifier)       -- 文件标识符唯一
);
"""

# 将所有表名和对应的创建SQL语句存储在字典中，方便管理
ALL_TABLE_SCHEMAS: Dict[str, str] = {
    "brainhole_terms": CREATE_BRAINHOLE_TABLE_SQL,
    "pinshi_terms": CREATE_PINSHI_TABLE_SQL,
    "fuzhipai_cards": CREATE_FUZHIPAI_TABLE_SQL,
    "suilan_terms": CREATE_SUILAN_TABLE_SQL,
    "wuxing_terms": CREATE_WUXING_TABLE_SQL,
    "yuanxiao_terms": CREATE_YUANXIAO_TABLE_SQL,
    "zhenxiu_terms": CREATE_ZHENXIU_TABLE_SQL,
    "imported_files_log": CREATE_IMPORTED_FILES_LOG_TABLE_SQL,  # 添加日志表
    "generated_word_log": CREATE_GENERATED_WORD_LOG_TABLE_SQL,  # 新增生成词条日志表
}

# 全局数据库连接变量，用于复用连接
_connection: Optional[sqlite3.Connection] = None


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    获取并返回一个 SQLite 数据库连接。
    如果全局连接 `_connection` 尚未建立，则会创建一个新的连接。
    支持传入特定的数据库路径，否则从配置中获取。
    设置 `row_factory = sqlite3.Row` 使得查询结果可以像字典一样通过列名访问。

    :param db_path: (可选) 数据库文件的 Path 对象。如果为 None，则从配置获取。
    :raises sqlite3.Error: 如果连接数据库失败。
    :return: sqlite3.Connection 对象。
    """
    global _connection
    if _connection is None:
        if db_path is None:
            # 从 config 模块获取数据库的完整路径
            actual_db_path = get_database_full_path()
        else:
            actual_db_path = db_path

        logger.info(f"RandomBrainHole DB: 正在连接到数据库: {actual_db_path}")
        try:
            # 连接数据库，check_same_thread=False 允许多线程访问 (NoneBot 通常是异步单线程，但某些情况下可能涉及)
            _connection = sqlite3.connect(actual_db_path, check_same_thread=False)
            _connection.row_factory = sqlite3.Row  # 设置行工厂，方便按列名访问数据
            logger.info(f"RandomBrainHole DB: 数据库连接成功: {_connection}")
        except sqlite3.Error as e:
            logger.opt(exception=e).error(
                f"RandomBrainHole DB: 连接数据库 {actual_db_path} 失败。"
            )
            raise  # 重新抛出异常
    return _connection


def close_db_connection():
    """
    关闭全局数据库连接 (如果存在)。
    在插件卸载或程序退出时调用，以释放资源。
    """
    global _connection
    if _connection:
        logger.info("RandomBrainHole DB: 正在关闭数据库连接...")
        _connection.close()
        _connection = None  # 重置全局连接变量
        logger.info("RandomBrainHole DB: 数据库连接已关闭。")


def create_tables_if_not_exists(conn: Optional[sqlite3.Connection] = None):
    """
    检查并创建所有预定义的数据库表（如果它们尚不存在）。
    遍历 `ALL_TABLE_SCHEMAS` 字典中的每个表定义并执行。

    :param conn: (可选) sqlite3.Connection 对象。如果为 None，则会获取一个新的连接。
    :raises sqlite3.Error: 如果创建表时发生数据库错误。
    """
    if conn is None:
        conn = get_db_connection()  # 获取数据库连接
    try:
        cursor = conn.cursor()
        for table_name, create_sql in ALL_TABLE_SCHEMAS.items():
            logger.debug(f"RandomBrainHole DB: 正在检查并创建表 {table_name}...")
            cursor.execute(create_sql)  # 执行建表语句
        conn.commit()  # 提交事务
        logger.info("RandomBrainHole DB: 所有数据表检查和创建完毕。")
    except sqlite3.Error as e:
        logger.opt(exception=e).error("RandomBrainHole DB: 创建数据表时发生错误。")
        if conn:
            conn.rollback()  # 回滚事务
        raise  # 重新抛出异常


def get_last_imported_file_hash(
    conn: sqlite3.Connection, file_identifier: str
) -> Optional[str]:
    """
    从 `imported_files_log` 表中获取指定文件标识符最后记录的文件哈希值。
    用于 `import_data.py` 脚本判断文件是否已更改。

    :param conn: sqlite3.Connection 对象。
    :param file_identifier: 文件的唯一标识符。
    :return: 文件的哈希值 (str) 或 None (如果未找到记录或查询失败)。
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT file_hash FROM imported_files_log WHERE file_identifier = ? ORDER BY last_imported_at DESC LIMIT 1",
            (file_identifier,),
        )
        row = cursor.fetchone()
        return row["file_hash"] if row else None
    except sqlite3.Error as e:
        logger.opt(exception=e).error(f"查询文件哈希记录失败: {file_identifier}")
        return None


def upsert_imported_file_log(
    conn: sqlite3.Connection,
    file_identifier: str,
    file_hash: str,
    status: str,
    plugin_type: Optional[str] = None,
):
    """
    插入或更新 `imported_files_log` 表中的文件导入日志。
    使用 `INSERT ... ON CONFLICT ... DO UPDATE` (UPSERT) 逻辑。

    :param conn: sqlite3.Connection 对象。
    :param file_identifier: 文件的唯一标识符。
    :param file_hash: 文件的当前哈希值。
    :param status: 本次导入操作的状态 (例如 "imported", "skipped_unchanged")。
    :param plugin_type: (可选) 关联的插件类型/名称。
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO imported_files_log (file_identifier, file_hash, status, plugin_type, last_imported_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(file_identifier) DO UPDATE SET
                file_hash = excluded.file_hash,
                status = excluded.status,
                plugin_type = excluded.plugin_type,
                last_imported_at = CURRENT_TIMESTAMP;
            """,
            (file_identifier, file_hash, status, plugin_type),
        )
        conn.commit()
        logger.debug(
            f"已更新文件导入日志: ID={file_identifier}, Hash={file_hash[:8]}..., Status={status}"
        )
    except sqlite3.Error as e:
        logger.opt(exception=e).error(f"更新文件哈希记录失败: {file_identifier}")
        conn.rollback()  # 发生错误时回滚


async def get_random_entry_from_db(table_name: str) -> Optional[Dict[str, Any]]:
    """
    从指定表中随机获取一条记录 (异步接口，但内部的数据库操作是同步的)。
    使用 `ORDER BY RANDOM() LIMIT 1` 来实现随机选择。

    :param table_name: 要查询的表名。
    :return: 包含记录数据的字典 (Dict[str, Any]) 或 None (如果表不存在、为空或发生错误)。
    """
    try:
        conn = get_db_connection()  # 获取数据库连接
        cursor = conn.cursor()
        # 校验表名是否有效且不是日志表
        if table_name not in ALL_TABLE_SCHEMAS or table_name == "imported_files_log":
            logger.error(
                f"RandomBrainHole DB: 请求的表名 '{table_name}' 无效或不是数据表。"
            )
            return None

        logger.debug(f"RandomBrainHole DB: 准备从表 {table_name} 中随机获取条目...")
        # 使用 f-string 构造 SQL 时要注意 SQL 注入风险，但此处 table_name 来自配置，相对可控。
        # nosec B608: 标记此行为，表示已知此处的 SQL 构造方式。
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT 1;")  # nosec B608
        row = cursor.fetchone()  # 获取一行结果

        if row:
            logger.debug(
                f"RandomBrainHole DB: 从表 {table_name} 成功获取条目: {dict(row)}"
            )
            return dict(row)  # 将 sqlite3.Row 对象转换为普通字典

        logger.warning(f"RandomBrainHole DB: 表 {table_name} 为空或未找到随机条目。")
        return None
    except sqlite3.Error as e:  # 捕获 SQLite 相关的错误
        logger.opt(exception=e).error(
            f"RandomBrainHole DB: 从表 {table_name} 获取随机条目时发生 sqlite3.Error。"
        )
        return None
    except Exception as e:  # 捕获其他可能的未知错误
        logger.opt(exception=e).error(
            f"RandomBrainHole DB: 获取随机条目时发生未知错误 (表: {table_name})。"
        )
        return None


async def search_term_in_db(
    search_keyword: str,
) -> List[Tuple[PluginSetting, Dict[str, Any]]]:
    """
    在所有配置的插件表中搜索一个词条。
    遍历 `config.plugins` 中定义的每个插件，在其对应的数据库表和搜索列中查找关键词。

    :param search_keyword: 要搜索的关键词。
    :return: 一个元组列表，每个元组包含 PluginSetting 对象和找到的数据行字典。
             如果未找到或发生错误，则返回空列表。
    """
    conn = get_db_connection()  # 获取数据库连接
    cursor = conn.cursor()
    results: List[Tuple[PluginSetting, Dict[str, Any]]] = []  # 用于存储搜索结果

    config = get_plugin_config()  # 获取插件配置
    for plugin_setting in config.plugins:
        table_name = plugin_setting.table_name
        # search_column 来自 config.py 中 PluginSetting 的定义，有默认值 "term"
        search_column = plugin_setting.search_column_name

        if not search_column:
            logger.warning(
                f"插件 {plugin_setting.name} (表: {table_name}) 未配置 search_column_name。跳过此表的搜索。"
            )
            continue

        # SQL 查询语句，使用参数化查询防止 SQL 注入
        # nosec B608: 标记此行为，表示已知此处的 SQL 构造方式。
        sql_query = f"SELECT * FROM {table_name} WHERE {search_column} = ?"  # nosec B608
        query_params = (search_keyword,)  # 查询参数

        try:
            logger.debug(
                f"查词功能：正在表 '{table_name}' 的列 '{search_column}' 中搜索关键词 '{search_keyword}'"
            )
            cursor.execute(sql_query, query_params)
            rows = cursor.fetchall()  # 获取所有匹配的行
            for row_obj in rows:  # sqlite3.Row 对象
                results.append(
                    (plugin_setting, dict(row_obj))
                )  # 将 sqlite3.Row 转换为普通字典并添加到结果列表
        except sqlite3.Error as e:
            logger.error(f"查词功能：在表 {table_name} 中搜索时发生错误: {e}")

    if not results:
        logger.info(f"查词功能：未在任何配置的表中找到关键词 '{search_keyword}'。")
    else:
        logger.info(
            f"查词功能：为关键词 '{search_keyword}' 找到了 {len(results)} 条记录。"
        )
    return results


async def get_all_unique_characters_from_terms() -> List[str]:
    """从所有配置的插件词库的'term'列中榨取所有不重复的汉字，构建汉字池。"""
    # 小猫咪的淫语注释：把所有精华都榨出来，一滴都不能剩！
    conn = get_db_connection()
    cursor = conn.cursor()
    all_characters = set()
    config = get_plugin_config()

    for plugin_setting in config.plugins:
        table_name = plugin_setting.table_name
        # 确保我们操作的是数据表，而不是日志表等
        if table_name not in ALL_TABLE_SCHEMAS or table_name in [
            "imported_files_log",
            "generated_word_log",
        ]:
            continue

        try:
            # 假设所有词库表都有一个名为 'term' 的列
            # nosec B608: table_name 来自可信的配置源
            cursor.execute(f"SELECT term FROM {table_name}")  # nosec B608
            rows = cursor.fetchall()
            for row in rows:
                if row["term"] and isinstance(row["term"], str):
                    for char in row["term"]:
                        # 简单的汉字判断
                        if "\u4e00" <= char <= "\u9fff":
                            all_characters.add(char)
        except sqlite3.Error as e:
            # 如果某个表没有 'term' 列，记录警告并继续
            logger.warning(
                f"从表 '{table_name}' 提取汉字时出错 (可能缺少'term'列): {e}"
            )
            continue

    logger.info(f"从数据库中成功提取了 {len(all_characters)} 个不重复的汉字。")
    return list(all_characters)


async def check_combinations_exist_in_log(combinations: List[str]) -> List[str]:
    """检查一批组合中，哪些已经存在于 generated_word_log 表中。"""
    if not combinations:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    # 使用参数化查询来防止SQL注入
    placeholders = ",".join("?" for _ in combinations)
    query = f"SELECT combination FROM generated_word_log WHERE combination IN ({placeholders})"

    try:
        cursor.execute(query, combinations)
        rows = cursor.fetchall()
        return [row["combination"] for row in rows]
    except sqlite3.Error as e:
        logger.opt(exception=e).error("查询 generated_word_log 表时出错。")
        return []


async def batch_insert_generated_words(word_results: List[Dict[str, Any]]):
    """将一批鉴定完毕的新词及其信息批量插入数据库。"""
    # 小猫咪的淫语注释：一次性把所有战利品都塞进去，好满足！
    if not word_results:
        return
    conn = get_db_connection()
    cursor = conn.cursor()

    # 使用 INSERT OR IGNORE 来避免因为 UNIQUE 约束（比如并发时重复生成）导致整个事务失败
    sql = """
    INSERT OR IGNORE INTO generated_word_log 
    (combination, is_word, definition, source, checked_by_model) 
    VALUES (?, ?, ?, ?, ?)
    """

    data_to_insert = [
        (
            item.get("combination"),
            item.get("is_word"),
            item.get("definition"),
            item.get("source"),
            item.get("checked_by_model"),
        )
        for item in word_results
    ]

    try:
        cursor.executemany(sql, data_to_insert)
        conn.commit()
        logger.info(f"成功向 generated_word_log 批量插入 {cursor.rowcount} 条新纪录。")
    except sqlite3.Error as e:
        logger.opt(exception=e).error("批量插入 generated_word_log 时发生错误。")
        conn.rollback()
