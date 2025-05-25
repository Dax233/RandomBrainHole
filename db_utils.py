import sqlite3
from pathlib import Path
from typing import Optional, Any, Dict
from nonebot import logger # 导入 NoneBot 的 logger

# --- 表创建SQL语句 (确保与你的数据库结构一致) ---
# 脑洞表
CREATE_BRAINHOLE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS brainhole_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_name TEXT NOT NULL,                 -- 场次/比赛名
    term TEXT NOT NULL,                       -- 词汇
    pinyin TEXT,                              -- 拼音
    difficulty TEXT,                          -- 难度
    win_rate TEXT,                            -- 胜率
    category TEXT,                            -- 类型
    author TEXT,                              -- 出题人
    definition TEXT,                          -- 释义
    source_file TEXT NOT NULL,                -- 来源文件名
    source_sheet TEXT,                        -- 来源子表名 (对于Excel多子表情况)
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 导入时间
    UNIQUE (match_name, term, source_file, source_sheet) -- 联合唯一键
);
"""
# 拼释表
CREATE_PINSHI_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pinshi_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL,                       -- 题目
    pinyin TEXT,                              -- 拼音
    source_text TEXT,                         -- 出处 (原文中的'出处')
    writing TEXT,                             -- 书写
    difficulty TEXT,                          -- 难度
    definition TEXT,                          -- 解释
    source_file TEXT NOT NULL,                -- 来源文件名
    source_sheet TEXT,                        -- 来源子表名
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (term, source_text, source_file, source_sheet) 
);
"""
# 蝠汁牌表 (使用哈希作为唯一性判断)
CREATE_FUZHIPAI_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fuzhipai_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_title TEXT,                          -- 卡牌标题 (尝试从内容提取)
    full_text TEXT NOT NULL,                  -- 完整卡牌描述
    full_text_hash TEXT,                      -- full_text的哈希值 (用于唯一性)
    source_file TEXT NOT NULL,                -- 来源文件名
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (full_text_hash, source_file)      -- 联合唯一键
);
"""
# 随蓝表
CREATE_SUILAN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS suilan_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL,                       -- 题面
    player TEXT,                              -- 选手
    source_text TEXT,                         -- 出处 (原文中的'出处')
    definition TEXT,                          -- 解释
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
    term TEXT NOT NULL,                       -- 词语
    pinyin TEXT,
    difficulty TEXT,
    source_origin TEXT,                       -- 出自 (原文中的'出自')
    author TEXT,                              -- 出题人
    definition TEXT,                          -- 释义
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
    term TEXT NOT NULL,                       -- 词汇
    pinyin TEXT,
    source_text TEXT,                         -- 出处
    difficulty_liju TEXT,                     -- 丽句难度
    difficulty_naodong TEXT,                  -- 脑洞难度
    definition TEXT,                          -- 解释
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
    term_id_text TEXT,                        -- 题号 (原文中的'题号',可能是文本)
    term TEXT NOT NULL,                       -- 词汇
    source_text TEXT,                         -- 出处
    category TEXT,                            -- 题型
    pinyin TEXT,
    definition TEXT,                          -- 解释
    is_disyllabic TEXT,                       -- 双音节 (原文中的'双音节')
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,               -- 祯休特别依赖子表名
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
    """获取并返回一个 SQLite 数据库连接。"""
    global _connection
    if _connection is None:
        if db_path is None:
            # 延迟导入以避免循环依赖，并确保 config 已加载
            from .config import get_database_full_path 
            actual_db_path = get_database_full_path()
        else:
            actual_db_path = db_path
        
        logger.info(f"RandomBrainHole DB: 正在连接到数据库: {actual_db_path}")
        try:
            # check_same_thread=False 适用于多线程环境如NoneBot
            _connection = sqlite3.connect(actual_db_path, check_same_thread=False) 
            _connection.row_factory = sqlite3.Row # 允许通过列名访问数据
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
        _connection = None # 重置全局连接变量
        logger.info("RandomBrainHole DB: 数据库连接已关闭。")

def create_tables_if_not_exists(conn: Optional[sqlite3.Connection] = None):
    """检查并创建所有预定义的数据库表（如果它们尚不存在）。"""
    is_temp_conn = False
    if conn is None:
        conn = get_db_connection() # 获取或创建全局连接
        # is_temp_conn = True # 如果是这里获取的连接，是否用完即关取决于策略

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
             conn.rollback() # 如果有连接，尝试回滚
        raise # 重新抛出异常，以便上层处理
    # finally:
    #     if is_temp_conn and conn:
    #         # 通常不在这里关闭，由 on_shutdown 钩子统一关闭全局连接
    #         pass

async def get_random_entry_from_db(table_name: str) -> Optional[Dict[str, Any]]:
    """从指定表中随机获取一条记录 (异步接口，同步执行DB操作)。"""
    try:
        conn = get_db_connection() # 获取全局或新连接
        cursor = conn.cursor()

        if table_name not in ALL_TABLE_SCHEMAS:
            logger.error(f"RandomBrainHole DB: 请求的表名 '{table_name}' 未在预定义模式中。")
            return None
        
        # 同步执行数据库查询。在async函数中，这会阻塞事件循环。
        # 对于高并发场景，应使用异步数据库驱动或 run_in_executor。
        # 对于SQLite和中低负载机器人，这通常可以接受。
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT 1;")
        row = cursor.fetchone()

        if row:
            return dict(row) # 将 sqlite3.Row 转换为字典
        
        logger.warning(f"RandomBrainHole DB: 表 {table_name} 为空或未找到随机条目。")
        return None
    except sqlite3.Error as e:
        logger.opt(exception=e).error(f"RandomBrainHole DB: 从表 {table_name} 获取随机条目时出错。")
        return None
    except Exception as e: # 捕获其他潜在错误
        logger.opt(exception=e).error(f"RandomBrainHole DB: 获取随机条目时发生未知错误 (表: {table_name})。")
        return None
