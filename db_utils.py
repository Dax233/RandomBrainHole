import sqlite3
from pathlib import Path
from typing import Optional, List, Any, Dict

# 导入 get_database_full_path 而不是 get_plugin_config 来解耦
# from .config import get_database_full_path # 避免直接依赖 config 模块的 get_plugin_config
# 改为在函数内部调用 get_database_full_path

# --- 表创建SQL语句 ---
# (与之前提供的版本相同，这里省略以减少重复，请参考之前消息中的 CREATE TABLE 语句)
# 脑洞表
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
    UNIQUE (match_name, term, source_file, source_sheet)
);
"""
# 拼释表
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
    UNIQUE (term, source_text, source_file, source_sheet) 
);
"""
# 蝠汁牌表
CREATE_FUZHIPAI_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fuzhipai_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_title TEXT,
    full_text TEXT NOT NULL,
    full_text_hash TEXT,                      -- 可选，用于更可靠的唯一性判断
    source_file TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (full_text_hash, source_file)      -- 如果使用哈希
    -- UNIQUE (card_title, source_file)       -- 如果标题可靠
);
"""
# 随蓝表
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
    UNIQUE (term, source_file, source_sheet)
);
"""
# 五行表
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
    UNIQUE (term, source_file, source_sheet)
);
"""
# 元晓表
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
    UNIQUE (term, source_file, source_sheet)
);
"""
# 祯休表
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
    UNIQUE (term, source_file, source_sheet)
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
}

_connection: Optional[sqlite3.Connection] = None

def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    获取并返回一个 SQLite 数据库连接。
    如果连接不存在，则创建它。
    如果提供了 db_path，则使用它；否则，从配置中获取。
    """
    global _connection
    if _connection is None:
        if db_path is None:
            # 延迟导入 config 模块的函数，以减少模块加载时的依赖
            from .config import get_database_full_path
            actual_db_path = get_database_full_path()
        else:
            actual_db_path = db_path
        
        print(f"[DB_UTILS] 正在连接到数据库: {actual_db_path}")
        try:
            _connection = sqlite3.connect(actual_db_path, check_same_thread=False)
            _connection.row_factory = sqlite3.Row 
            print(f"[DB_UTILS] 数据库连接成功: {_connection}")
        except sqlite3.Error as e:
            print(f"[DB_UTILS_ERROR] 连接数据库 {actual_db_path} 失败: {e}")
            raise
    return _connection

def close_db_connection():
    """关闭数据库连接 (如果存在)"""
    global _connection
    if _connection:
        print("[DB_UTILS] 正在关闭数据库连接...")
        _connection.close()
        _connection = None
        print("[DB_UTILS] 数据库连接已关闭。")

def create_tables_if_not_exists(conn: Optional[sqlite3.Connection] = None):
    """
    检查并创建所有预定义的数据库表（如果它们尚不存在）。
    如果未提供 conn，则会尝试获取一个新的连接。
    """
    close_existing_conn_after = False
    if conn is None:
        conn = get_db_connection()
        close_existing_conn_after = True # 如果是这里获取的连接，用完后应该关闭

    try:
        cursor = conn.cursor()
        for table_name, create_sql in ALL_TABLE_SCHEMAS.items():
            print(f"[DB_UTILS] 正在检查并创建表 {table_name}...")
            cursor.execute(create_sql)
        conn.commit()
        print("[DB_UTILS] 所有数据表检查和创建完毕。")
    except sqlite3.Error as e:
        print(f"[DB_UTILS_ERROR] 创建数据表时发生错误: {e}")
        if conn: # 如果有连接且非传入，尝试回滚
             conn.rollback()
        raise
    finally:
        if close_existing_conn_after and conn:
            # 如果是此函数内部获取的连接，则不关闭，让调用者管理或由全局 close_db_connection 处理
            # close_db_connection() # 或者直接关闭，取决于策略
            pass


async def get_random_entry_from_db(table_name: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """
    从指定表中随机获取一条记录 (异步版本，供NoneBot插件运行时使用)。
    返回一个字典或 None (如果表为空或出错)。
    """
    close_conn_after = False
    if conn is None:
        conn = get_db_connection() # 获取全局或新连接
        # 注意：在异步函数中直接操作全局连接变量 _connection 可能不是最佳实践，
        # 更好的做法是每次都获取连接或使用连接池。
        # 但对于SQLite和简单场景，暂时这样处理。
        # close_conn_after = True # 如果是这里获取的连接，不应该立即关闭，因为是异步

    try:
        cursor = conn.cursor()
        if table_name not in ALL_TABLE_SCHEMAS:
            print(f"[DB_UTILS_ERROR] 请求的表名 '{table_name}' 未在预定义模式中。")
            return None
        
        # 对于异步操作，数据库调用本身是阻塞的。
        # 在async函数中使用阻塞IO，需要用 nonebot.adapters.utils.run_sync 等包装，
        # 或者使用异步数据库驱动 (如 aiosqlite)。
        # 这里为了简化，暂时保持同步调用，但在真实异步环境可能导致性能问题。
        # import asyncio # 示例：如果需要异步执行
        # loop = asyncio.get_event_loop()
        # row = await loop.run_in_executor(None, cursor.execute, f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT 1;")
        # row = await loop.run_in_executor(None, cursor.fetchone)
        
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT 1;")
        row = cursor.fetchone()

        if row:
            return dict(row) 
        return None
    except sqlite3.Error as e:
        print(f"[DB_UTILS_ERROR] 从表 {table_name} 获取随机条目时出错: {e}")
        return None
    # finally:
    #     if close_conn_after and conn:
    #         pass # 在异步场景下，连接管理更复杂

