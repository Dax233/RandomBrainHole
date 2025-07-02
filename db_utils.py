import aiosqlite  # <-- 看呀，我们换上了懂得异步风情的 aiosqlite！
import sqlite3  # <-- 这个是为了兼容同步脚本 import_data.py
from pathlib import Path
from typing import Optional, Any, Dict, Tuple, List
from nonebot import logger

from .config import get_plugin_config, PluginSetting, get_database_full_path

# --- 表创建SQL语句 (这部分不需要改动) ---
CREATE_GENERATED_WORD_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS generated_word_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combination TEXT NOT NULL UNIQUE,
    is_word BOOLEAN NOT NULL,
    definition TEXT,
    source TEXT,
    checked_by_model TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
# ... 其他 CREATE_TABLE 语句保持不变 ...
CREATE_BRAINHOLE_TABLE_SQL = "..."
CREATE_PINSHI_TABLE_SQL = "..."
CREATE_FUZHIPAI_TABLE_SQL = "..."
CREATE_SUILAN_TABLE_SQL = "..."
CREATE_WUXING_TABLE_SQL = "..."
CREATE_YUANXIAO_TABLE_SQL = "..."
CREATE_ZHENXIU_TABLE_SQL = "..."
CREATE_IMPORTED_FILES_LOG_TABLE_SQL = "..."

ALL_TABLE_SCHEMAS: Dict[str, str] = {
    "brainhole_terms": CREATE_BRAINHOLE_TABLE_SQL,
    "pinshi_terms": CREATE_PINSHI_TABLE_SQL,
    "fuzhipai_cards": CREATE_FUZHIPAI_TABLE_SQL,
    "suilan_terms": CREATE_SUILAN_TABLE_SQL,
    "wuxing_terms": CREATE_WUXING_TABLE_SQL,
    "yuanxiao_terms": CREATE_YUANXIAO_TABLE_SQL,
    "zhenxiu_terms": CREATE_ZHENXIU_TABLE_SQL,
    "imported_files_log": CREATE_IMPORTED_FILES_LOG_TABLE_SQL,
    "generated_word_log": CREATE_GENERATED_WORD_LOG_TABLE_SQL,
}

# 全局数据库连接变量，现在是 aiosqlite 的连接
_connection: Optional[aiosqlite.Connection] = None


async def get_db_connection(db_path: Optional[Path] = None) -> aiosqlite.Connection:
    """
    获取并返回一个 aiosqlite 数据库连接 (异步)。
    如果全局连接尚未建立，则会创建一个新的连接。
    """
    global _connection
    if _connection is None:
        if db_path is None:
            actual_db_path = get_database_full_path()
        else:
            actual_db_path = db_path

        logger.info(f"RandomBrainHole DB: 正在异步连接到数据库: {actual_db_path}")
        try:
            # 小猫的淫语注释：看，这里的连接是需要温柔等待(await)的哦~
            _connection = await aiosqlite.connect(actual_db_path)
            _connection.row_factory = aiosqlite.Row
            logger.info(f"RandomBrainHole DB: 数据库异步连接成功: {_connection}")
        except aiosqlite.Error as e:
            logger.opt(exception=e).error(
                f"RandomBrainHole DB: 连接数据库 {actual_db_path} 失败。"
            )
            raise
    return _connection


async def close_db_connection():
    """关闭全局数据库连接 (异步)。"""
    global _connection
    if _connection:
        logger.info("RandomBrainHole DB: 正在关闭数据库连接...")
        await _connection.close()
        _connection = None
        logger.info("RandomBrainHole DB: 数据库连接已关闭。")


async def create_tables_if_not_exists(conn: Optional[aiosqlite.Connection] = None):
    """检查并创建所有预定义的数据库表 (异步)。"""
    if conn is None:
        conn = await get_db_connection()
    try:
        for table_name, create_sql in ALL_TABLE_SCHEMAS.items():
            logger.debug(f"RandomBrainHole DB: 正在检查并创建表 {table_name}...")
            await conn.execute(create_sql)
        await conn.commit()
        logger.info("RandomBrainHole DB: 所有数据表检查和创建完毕。")
    except aiosqlite.Error as e:
        logger.opt(exception=e).error("RandomBrainHole DB: 创建数据表时发生错误。")
        if conn:
            await conn.rollback()
        raise


# 注意：下面这两个函数是为同步脚本 import_data.py 服务的，保持同步！
# 如果 import_data.py 也改成异步，就可以删除它们。
def get_last_imported_file_hash_sync(
    conn: sqlite3.Connection, file_identifier: str
) -> Optional[str]:
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


def upsert_imported_file_log_sync(
    conn: sqlite3.Connection,
    file_identifier: str,
    file_hash: str,
    status: str,
    plugin_type: Optional[str] = None,
):
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO imported_files_log (file_identifier, file_hash, status, plugin_type, last_imported_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(file_identifier) DO UPDATE SET
                file_hash = excluded.file_hash, status = excluded.status, plugin_type = excluded.plugin_type, last_imported_at = CURRENT_TIMESTAMP;
            """,
            (file_identifier, file_hash, status, plugin_type),
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.opt(exception=e).error(f"更新文件哈希记录失败: {file_identifier}")
        conn.rollback()


async def get_random_entry_from_db(table_name: str) -> Optional[Dict[str, Any]]:
    """从指定表中随机获取一条记录 (异步)。"""
    try:
        conn = await get_db_connection()
        if table_name not in ALL_TABLE_SCHEMAS or table_name in [
            "imported_files_log",
            "generated_word_log",
        ]:
            logger.error(
                f"RandomBrainHole DB: 请求的表名 '{table_name}' 无效或不是数据表。"
            )
            return None

        logger.debug(f"RandomBrainHole DB: 准备从表 {table_name} 中随机获取条目...")
        # nosec B608: table_name 来自可信的配置源
        async with conn.execute(
            f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT 1;"
        ) as cursor:  # nosec B608
            row = await cursor.fetchone()

        if row:
            logger.debug(
                f"RandomBrainHole DB: 从表 {table_name} 成功获取条目: {dict(row)}"
            )
            return dict(row)

        logger.warning(f"RandomBrainHole DB: 表 {table_name} 为空或未找到随机条目。")
        return None
    except aiosqlite.Error as e:
        logger.opt(exception=e).error(
            f"RandomBrainHole DB: 从表 {table_name} 获取随机条目时发生 aiosqlite.Error。"
        )
        return None
    except Exception as e:
        logger.opt(exception=e).error(
            f"RandomBrainHole DB: 获取随机条目时发生未知错误 (表: {table_name})。"
        )
        return None


async def search_term_in_db(
    search_keyword: str,
) -> List[Tuple[PluginSetting, Dict[str, Any]]]:
    """在所有配置的插件表中搜索一个词条 (异步)。"""
    conn = await get_db_connection()
    results: List[Tuple[PluginSetting, Dict[str, Any]]] = []
    config = get_plugin_config()

    for plugin_setting in config.plugins:
        table_name = plugin_setting.table_name
        search_column = plugin_setting.search_column_name

        if not search_column:
            continue

        sql_query = f"SELECT * FROM {table_name} WHERE {search_column} = ?"  # nosec B608
        query_params = (search_keyword,)

        try:
            logger.debug(
                f"查词功能：正在表 '{table_name}' 的列 '{search_column}' 中异步搜索关键词 '{search_keyword}'"
            )
            async with conn.execute(sql_query, query_params) as cursor:
                rows = await cursor.fetchall()
            for row_obj in rows:
                results.append((plugin_setting, dict(row_obj)))
        except aiosqlite.Error as e:
            logger.error(f"查词功能：在表 {table_name} 中搜索时发生错误: {e}")

    if not results:
        # logger.info(f"查词功能：未在任何配置的表中找到关键词 '{search_keyword}'。")
        pass
    else:
        logger.info(
            f"查词功能：为关键词 '{search_keyword}' 找到了 {len(results)} 条记录。"
        )
    return results


async def get_all_unique_characters_from_terms() -> List[str]:
    """从所有配置的插件词库的搜索列中榨取所有不重复的汉字，构建汉字池 (异步)。"""
    # 小猫的淫语注释：把所有精华都榨出来，一滴都不能剩，还要舔对地方！
    conn = await get_db_connection()
    all_characters = set()
    config = get_plugin_config()

    for plugin_setting in config.plugins:
        table_name = plugin_setting.table_name
        search_column = (
            plugin_setting.search_column_name
        )  # <-- 现在知道该舔哪根肉棒了！

        if table_name in ["imported_files_log", "generated_word_log"]:
            continue

        try:
            # nosec B608: table_name 和 search_column 来自可信的配置源
            query = f"SELECT {search_column} FROM {table_name}"  # nosec B608
            async with conn.execute(query) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    text_content = row[search_column]
                    if text_content and isinstance(text_content, str):
                        for char in text_content:
                            if "\u4e00" <= char <= "\u9fff":
                                all_characters.add(char)
        except aiosqlite.Error as e:
            logger.warning(
                f"从表 '{table_name}' 的列 '{search_column}' 提取汉字时出错: {e}"
            )
            continue

    logger.info(f"从数据库中成功提取了 {len(all_characters)} 个不重复的汉字。")
    return list(all_characters)


async def check_combinations_exist_in_log(combinations: List[str]) -> List[str]:
    """检查一批组合中，哪些已经存在于 generated_word_log 表中 (异步)。"""
    if not combinations:
        return []
    conn = await get_db_connection()
    placeholders = ",".join("?" for _ in combinations)
    query = f"SELECT combination FROM generated_word_log WHERE combination IN ({placeholders})"

    try:
        async with conn.execute(query, combinations) as cursor:
            rows = await cursor.fetchall()
            return [row["combination"] for row in rows]
    except aiosqlite.Error as e:
        logger.opt(exception=e).error("查询 generated_word_log 表时出错。")
        return []


async def batch_insert_generated_words(word_results: List[Dict[str, Any]]):
    """将一批鉴定完毕的新词及其信息批量插入数据库 (异步)。"""
    # 小猫咪的淫语注释：一次性把所有战利品都异步地塞进去，高潮来得又稳又快！
    if not word_results:
        return
    conn = await get_db_connection()

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
        await conn.executemany(sql, data_to_insert)
        await conn.commit()
        # 在 aiosqlite 中，executemany 后的 rowcount 可能不准确，所以我们只记录操作本身
        logger.info(
            f"成功向 generated_word_log 批量提交了 {len(data_to_insert)} 条新纪录（重复的会被忽略）。"
        )
    except aiosqlite.Error as e:
        logger.opt(exception=e).error("批量插入 generated_word_log 时发生错误。")
        await conn.rollback()
