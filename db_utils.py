import sqlite3
from pathlib import Path
from typing import Optional, Any, Dict, Tuple, List # 新增 List
from nonebot import logger # 导入 NoneBot 的 logger

# 从同级目录的 config 模块导入配置相关的类和函数
# 确保 PluginSetting 也被导入，如果它在 search_term_in_db 中作为类型提示使用
from .config import get_plugin_config, PluginSetting, get_database_full_path


# --- 表创建SQL语句 ---
# (保留所有原有的词库表 CREATE TABLE 语句)
CREATE_BRAINHOLE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS brainhole_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, match_name TEXT NOT NULL, term TEXT NOT NULL,
    pinyin TEXT, difficulty TEXT, win_rate TEXT, category TEXT, author TEXT,
    definition TEXT, source_file TEXT NOT NULL, source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (match_name, term, source_file, source_sheet)
);"""
CREATE_PINSHI_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pinshi_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, term TEXT NOT NULL, pinyin TEXT,
    source_text TEXT, writing TEXT, difficulty TEXT, definition TEXT,
    source_file TEXT NOT NULL, source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_text, source_file, source_sheet) 
);"""
CREATE_FUZHIPAI_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fuzhipai_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT, card_title TEXT, full_text TEXT NOT NULL,
    full_text_hash TEXT, source_file TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (full_text_hash, source_file)
);"""
CREATE_SUILAN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS suilan_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, term TEXT NOT NULL, player TEXT,
    source_text TEXT, definition TEXT, source_file TEXT NOT NULL, source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_file, source_sheet)
);"""
CREATE_WUXING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wuxing_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, term TEXT NOT NULL, pinyin TEXT,
    difficulty TEXT, source_origin TEXT, author TEXT, definition TEXT,
    source_file TEXT NOT NULL, source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_file, source_sheet)
);"""
CREATE_YUANXIAO_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS yuanxiao_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, term TEXT NOT NULL, pinyin TEXT,
    source_text TEXT, difficulty_liju TEXT, difficulty_naodong TEXT,
    definition TEXT, source_file TEXT NOT NULL, source_sheet TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_file, source_sheet)
);"""
CREATE_ZHENXIU_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS zhenxiu_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT, term_id_text TEXT, term TEXT NOT NULL,
    source_text TEXT, category TEXT, pinyin TEXT, definition TEXT,
    is_disyllabic TEXT, source_file TEXT NOT NULL, source_sheet TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_file, source_sheet)
);"""

CREATE_IMPORTED_FILES_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS imported_files_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_identifier TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    last_imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT,
    plugin_type TEXT,
    UNIQUE (file_identifier)
);
"""

ALL_TABLE_SCHEMAS: Dict[str, str] = {
    "brainhole_terms": CREATE_BRAINHOLE_TABLE_SQL,
    "pinshi_terms": CREATE_PINSHI_TABLE_SQL,
    "fuzhipai_cards": CREATE_FUZHIPAI_TABLE_SQL,
    "suilan_terms": CREATE_SUILAN_TABLE_SQL,
    "wuxing_terms": CREATE_WUXING_TABLE_SQL,
    "yuanxiao_terms": CREATE_YUANXIAO_TABLE_SQL,
    "zhenxiu_terms": CREATE_ZHENXIU_TABLE_SQL,
    "imported_files_log": CREATE_IMPORTED_FILES_LOG_TABLE_SQL,
}

_connection: Optional[sqlite3.Connection] = None

def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取并返回一个 SQLite 数据库连接。"""
    global _connection
    if _connection is None:
        if db_path is None:
            # from .config import get_database_full_path # 已在模块顶部导入
            actual_db_path = get_database_full_path()
        else:
            actual_db_path = db_path
        
        logger.info(f"RandomBrainHole DB: 正在连接到数据库: {actual_db_path}")
        try:
            _connection = sqlite3.connect(actual_db_path, check_same_thread=False)
            _connection.row_factory = sqlite3.Row 
            logger.info(f"RandomBrainHole DB: 数据库连接成功: {_connection}")
        except sqlite3.Error as e:
            logger.opt(exception=e).error(f"RandomBrainHole DB: 连接数据库 {actual_db_path} 失败。")
            raise
    return _connection

def close_db_connection():
    """关闭数据库连接 (如果存在)"""
    global _connection
    if _connection:
        logger.info("RandomBrainHole DB: 正在关闭数据库连接...")
        _connection.close()
        _connection = None 
        logger.info("RandomBrainHole DB: 数据库连接已关闭。")

def create_tables_if_not_exists(conn: Optional[sqlite3.Connection] = None):
    """检查并创建所有预定义的数据库表（如果它们尚不存在）。"""
    # is_temp_conn = False # 此变量未使用，可以移除
    if conn is None:
        conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for table_name, create_sql in ALL_TABLE_SCHEMAS.items():
            logger.debug(f"RandomBrainHole DB: 正在检查并创建表 {table_name}...")
            cursor.execute(create_sql)
        conn.commit()
        logger.info("RandomBrainHole DB: 所有数据表检查和创建完毕。")
    except sqlite3.Error as e:
        logger.opt(exception=e).error("RandomBrainHole DB: 创建数据表时发生错误。")
        if conn: 
             conn.rollback() 
        raise

def get_last_imported_file_hash(conn: sqlite3.Connection, file_identifier: str) -> Optional[str]:
    """获取指定文件标识符最后记录的文件哈希值。"""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT file_hash FROM imported_files_log WHERE file_identifier = ? ORDER BY last_imported_at DESC LIMIT 1",
            (file_identifier,)
        )
        row = cursor.fetchone()
        return row['file_hash'] if row else None
    except sqlite3.Error as e:
        logger.opt(exception=e).error(f"查询文件哈希记录失败: {file_identifier}")
        return None

def upsert_imported_file_log(conn: sqlite3.Connection, file_identifier: str, file_hash: str, status: str, plugin_type: Optional[str] = None):
    """插入或更新文件导入日志。"""
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
            (file_identifier, file_hash, status, plugin_type)
        )
        conn.commit()
        logger.debug(f"已更新文件导入日志: ID={file_identifier}, Hash={file_hash[:8]}..., Status={status}")
    except sqlite3.Error as e:
        logger.opt(exception=e).error(f"更新文件哈希记录失败: {file_identifier}")
        conn.rollback()


async def get_random_entry_from_db(table_name: str) -> Optional[Dict[str, Any]]:
    """从指定表中随机获取一条记录 (异步接口，同步执行DB操作)。"""
    try:
        conn = get_db_connection() 
        cursor = conn.cursor()
        if table_name not in ALL_TABLE_SCHEMAS or table_name == "imported_files_log":
            logger.error(f"RandomBrainHole DB: 请求的表名 '{table_name}' 无效或不是数据表。")
            return None
        
        logger.debug(f"RandomBrainHole DB: 准备从表 {table_name} 中随机获取条目...")
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT 1;") # nosec B608
        row = cursor.fetchone()

        if row:
            logger.debug(f"RandomBrainHole DB: 从表 {table_name} 成功获取条目: {dict(row)}")
            return dict(row) 
        
        logger.warning(f"RandomBrainHole DB: 表 {table_name} 为空或未找到随机条目。")
        return None
    except sqlite3.Error as e:
        logger.opt(exception=e).error(f"RandomBrainHole DB: 从表 {table_name} 获取随机条目时发生 sqlite3.Error。")
        return None
    except Exception as e: 
        logger.opt(exception=e).error(f"RandomBrainHole DB: 获取随机条目时发生未知错误 (表: {table_name})。")
        return None

async def search_term_in_db(search_keyword: str) -> List[Tuple[PluginSetting, Dict[str, Any]]]:
    """
    在所有配置的插件表中搜索一个词条。
    返回一个元组列表，每个元组包含 PluginSetting 和找到的数据行字典。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    results: List[Tuple[PluginSetting, Dict[str, Any]]] = []
    
    config = get_plugin_config()
    for plugin_setting in config.plugins:
        table_name = plugin_setting.table_name
        # search_column 来自 config.py 中 PluginSetting 的定义，有默认值 "term"
        search_column = plugin_setting.search_column_name 

        if not search_column: 
            logger.warning(f"插件 {plugin_setting.name} (表: {table_name}) 未配置 search_column_name。跳过此表的搜索。")
            continue
        
        # 注意：这里的SQL查询是区分大小写的（对于大多数SQLite配置）。如果需要不区分大小写，可以使用LOWER()或COLLATE NOCASE。
        # 例如: f"SELECT * FROM {table_name} WHERE LOWER({search_column}) = LOWER(?)"
        # 或者在创建表时为列指定 COLLATE NOCASE。
        # 目前，我们使用精确匹配。
        # 对于蝠汁牌的 full_text 搜索，如果需要模糊匹配，可以使用 LIKE。
        # 例如: sql_query = f"SELECT * FROM {table_name} WHERE {search_column} LIKE ?"
        #       query_params = (f"%{search_keyword}%",)
        # 但当前配置 search_column_name 指向一个明确的列进行精确查找。
        sql_query = f"SELECT * FROM {table_name} WHERE {search_column} = ?" # nosec B608
        query_params = (search_keyword,)

        try:
            logger.debug(f"查词功能：正在表 '{table_name}' 的列 '{search_column}' 中搜索关键词 '{search_keyword}'")
            cursor.execute(sql_query, query_params)
            rows = cursor.fetchall() # fetchall() 返回一个列表的元组，sqlite3.Row使其可以像字典一样访问
            for row_obj in rows:
                results.append((plugin_setting, dict(row_obj))) # 将 sqlite3.Row 转换为普通字典
        except sqlite3.Error as e:
            logger.error(f"查词功能：在表 {table_name} 中搜索时发生错误: {e}")
            
    if not results:
        logger.info(f"查词功能：未在任何配置的表中找到关键词 '{search_keyword}'。")
    else:
        logger.info(f"查词功能：为关键词 '{search_keyword}' 找到了 {len(results)} 条记录。")
    return results
