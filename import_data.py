import sqlite3
import hashlib
from pathlib import Path
import pandas as pd
from docx import Document
import re
import sys # 用于路径修正
from typing import Iterator, Dict, Any, Callable, List, Optional

# --- 尝试导入同级模块 ---
try:
    # 这种方式在作为模块运行时 (python -m RandomBrainHole.import_data) 效果最好
    from .config import get_plugin_config, PluginSetting, get_database_full_path
    from .db_utils import get_db_connection, create_tables_if_not_exists, ALL_TABLE_SCHEMAS
except ImportError:
    print("[IMPORT_SCRIPT_WARNING] 无法通过相对路径导入模块。尝试修改sys.path...")
    # 获取当前脚本所在的目录
    current_script_path = Path(__file__).resolve().parent
    # 将插件根目录 (RandomBrainHole) 的父目录添加到 sys.path
    # 假设 import_data.py 在 RandomBrainHole 目录下
    project_root = current_script_path.parent 
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        print(f"[IMPORT_SCRIPT_INFO] 已将 '{project_root}' 添加到 sys.path。")
    
    # 再次尝试绝对导入
    try:
        from RandomBrainHole.config import get_plugin_config, PluginSetting, get_database_full_path
        from RandomBrainHole.db_utils import get_db_connection, create_tables_if_not_exists, ALL_TABLE_SCHEMAS
        print("[IMPORT_SCRIPT_INFO] 通过修改sys.path后，模块导入成功。")
    except ImportError as e:
        print(f"[IMPORT_SCRIPT_ERROR] 修改sys.path后仍然无法导入模块: {e}")
        print("请确保从 RandomBrainHole 目录的上一级运行此脚本，例如: python -m RandomBrainHole.import_data")
        sys.exit(1) # 导入失败则退出


# --- 日志函数 (简单实现) ---
def log_info(message: str): print(f"[INFO] {message}")
def log_warning(message: str): print(f"[WARNING] {message}")
def log_error(message: str): print(f"[ERROR] {message}")

# --- 辅助函数 ---
def get_user_confirmation(prompt: str) -> bool:
    while True:
        response = input(f"{prompt} (y/n): ").strip().lower()
        if response == 'y': return True
        if response == 'n': return False
        print("无效输入，请输入 'y' 或 'n'.")

def calculate_sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

# --- 数据解析函数 (与之前版本类似，这里省略重复代码，请参考之前消息中的解析函数) ---
# 你需要将之前消息中的 parse_brainhole_excel, parse_pinshi_excel, 
# parse_fuzhipai_docx, parse_simple_excel, parse_zhenxiu_excel 函数粘贴到这里。
# 我在这里只放一个示例，你需要补全其他的。

def parse_pinshi_excel(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]:
    """解析拼释类型的Excel文件 (示例，你需要补全其他解析器)"""
    log_info(f"开始解析拼释文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path) # 先打开文件获取sheet名
        actual_sheet_name = xls.sheet_names[0] if xls.sheet_names else "Sheet1"

        df = pd.read_excel(xls, sheet_name=0, header=0)
        if df.empty:
            log_warning(f"拼释文件 {source_file_name} 数据为空。")
            return

        sample_record = df.iloc[0].to_dict()
        print("\n--- 示例数据 (拼释) ---")
        print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
        for key, value in sample_record.items(): print(f"  {key}: {value}")
        print("------------------------")
        if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"):
            log_info(f"跳过导入子表 '{actual_sheet_name}'.")
            return

        for _, row in df.iterrows():
            yield {
                "term": str(row.get('题目', '')),
                "pinyin": str(row.get('拼音', '')),
                "source_text": str(row.get('出处', '')),
                "writing": str(row.get('书写', '')),
                "difficulty": str(row.get('难度', '')),
                "definition": str(row.get('解释', '')),
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理拼释文件 {source_file_name} 时出错: {e}")
        return

# !!! 请在这里补全其他 parse_XXX 函数 !!!
# parse_brainhole_excel, parse_fuzhipai_docx, parse_simple_excel (用于随蓝、五行、元晓), parse_zhenxiu_excel

def parse_brainhole_excel(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]:
    log_info(f"开始解析脑洞文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        log_error(f"打开脑洞Excel文件 {file_path} 失败: {e}")
        return
    sheet_names = xls.sheet_names
    if not sheet_names:
        log_warning(f"脑洞文件 {source_file_name} 中没有工作表。")
        return
    data_sheets = sheet_names[1:] if len(sheet_names) > 1 else sheet_names
    if not data_sheets:
        log_warning(f"脑洞文件 {source_file_name} 除去总览表后没有数据表。")
        return
    for sheet_name in data_sheets:
        log_info(f"  正在处理子表: {sheet_name}")
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            if df.empty:
                log_warning(f"  子表 {sheet_name} 为空。")
                continue
            match_name = str(df.iloc[0, 0]) if len(df.index) > 0 and len(df.columns) > 0 else "未知场次"
            if len(df.index) > 1:
                df.columns = df.iloc[1].astype(str)
                data_df = df[2:].reset_index(drop=True)
            else:
                log_warning(f"  子表 {sheet_name} 行数不足，无法解析表头和数据。")
                continue
            if data_df.empty:
                log_warning(f"  子表 {sheet_name} 移除表头后数据为空。")
                continue
            sample_record = data_df.iloc[0].to_dict()
            print("\n--- 示例数据 (脑洞) ---")
            print(f"来源文件: {source_file_name}, 子表: {sheet_name}, 场次: {match_name}")
            for key, value in sample_record.items(): print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入子表 '{sheet_name}' 的全部数据？"):
                log_info(f"跳过导入子表 '{sheet_name}'.")
                continue
            for _, row in data_df.iterrows():
                author = str(row.get('出题人', '暂无'))
                if author == '——': author = '盐铁桶子'
                win_rate_val = row.get('胜率', '暂无')
                win_rate_str = '暂无'
                if win_rate_val not in ['暂无', None, '']:
                    try: win_rate_str = f"{float(win_rate_val) * 100:.1f}%"
                    except (ValueError, TypeError): win_rate_str = str(win_rate_val)
                yield {
                    "match_name": match_name, "term": str(row.get('词汇', '')),
                    "pinyin": str(row.get('拼音', '')), "difficulty": str(row.get('难度', '')),
                    "win_rate": win_rate_str, "category": str(row.get('类型', '')),
                    "author": author, "definition": str(row.get('解释', '')),
                    "source_file": source_file_name, "source_sheet": sheet_name,
                }
        except Exception as e:
            log_error(f"  处理脑洞子表 {sheet_name} (文件: {source_file_name}) 时出错: {e}")
            continue

def parse_fuzhipai_docx(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]:
    log_info(f"开始解析蝠汁牌文件: {source_file_name}")
    try:
        doc = Document(file_path)
        cards_text_list = []
        active_card_content_lines = []
        for para in doc.paragraphs:
            para_text_raw = para.text
            if re.match(r"^[A-Za-z0-9]+【.*?】", para_text_raw.lstrip()):
                if active_card_content_lines:
                    full_card_text = "\n".join(active_card_content_lines).strip()
                    if full_card_text: cards_text_list.append(full_card_text)
                    active_card_content_lines = []
            current_para_formatted_text = ""
            is_currently_italic = False
            for run in para.runs:
                if run.italic:
                    if not is_currently_italic:
                        current_para_formatted_text += "["
                        is_currently_italic = True
                    current_para_formatted_text += run.text
                else:
                    if is_currently_italic:
                        current_para_formatted_text += "]"
                        is_currently_italic = False
                    current_para_formatted_text += run.text
            if is_currently_italic: current_para_formatted_text += "]"
            if current_para_formatted_text.strip(): active_card_content_lines.append(current_para_formatted_text.strip())
        if active_card_content_lines:
            full_card_text = "\n".join(active_card_content_lines).strip()
            if full_card_text: cards_text_list.append(full_card_text)
        if not cards_text_list:
            log_warning(f"蝠汁牌文件 {source_file_name} 未提取到卡牌。")
            return
        sample_card_text = cards_text_list[0]
        sample_card_title = sample_card_text.split('\n', 1)[0] if '\n' in sample_card_text else sample_card_text
        print("\n--- 示例数据 (蝠汁牌) ---")
        print(f"来源文件: {source_file_name}")
        print(f"  示例卡牌标题 (尝试提取): {sample_card_title}")
        print(f"  示例卡牌内容 (前100字符): {sample_card_text[:100]}...")
        print("------------------------")
        if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入文件 '{source_file_name}' 的全部数据？"):
            log_info(f"跳过导入文件 '{source_file_name}'.")
            return
        for card_text in cards_text_list:
            title = card_text.split('\n', 1)[0][:255] if '\n' in card_text else card_text[:255]
            full_text_hash = calculate_sha256(card_text) # 计算哈希
            yield {
                "card_title": title, "full_text": card_text,
                "full_text_hash": full_text_hash, # 添加哈希
                "source_file": source_file_name,
            }
    except Exception as e:
        log_error(f"处理蝠汁牌文件 {source_file_name} 时出错: {e}")
        return

def parse_simple_excel(file_path: Path, source_file_name: str, sheet_index: int, header_row: int, column_map: Dict[str, str], plugin_display_name: str) -> Iterator[Dict[str, Any]]:
    log_info(f"开始解析 {plugin_display_name} 文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
        actual_sheet_name = xls.sheet_names[sheet_index] if len(xls.sheet_names) > sheet_index else f"Sheet{sheet_index+1}"
        
        df = pd.read_excel(xls, sheet_name=sheet_index, header=header_row)
        if df.empty:
            log_warning(f"{plugin_display_name} 文件 {source_file_name} (sheet: {actual_sheet_name}) 数据为空。")
            return
        sample_record = df.iloc[0].to_dict()
        print(f"\n--- 示例数据 ({plugin_display_name}) ---")
        print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
        for key, value in sample_record.items(): print(f"  {key}: {value}")
        print("------------------------")
        if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"):
            log_info(f"跳过导入子表 '{actual_sheet_name}'.")
            return
        for _, row in df.iterrows():
            data_to_yield = {"source_file": source_file_name, "source_sheet": actual_sheet_name}
            for df_col, db_col in column_map.items():
                data_to_yield[db_col] = str(row.get(df_col, ''))
            yield data_to_yield
    except Exception as e:
        log_error(f"处理 {plugin_display_name} 文件 {source_file_name} (sheet: {sheet_index}) 时出错: {e}")
        return

def parse_zhenxiu_excel(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]:
    log_info(f"开始解析祯休文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        log_error(f"打开祯休Excel文件 {file_path} 失败: {e}")
        return
    for sheet_name in xls.sheet_names:
        log_info(f"  正在处理子表: {sheet_name}")
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=2)
            if df.empty:
                log_warning(f"  祯休子表 {sheet_name} 为空。")
                continue
            df_filled = df.fillna('无')
            sample_record = df_filled.iloc[0].to_dict()
            print(f"\n--- 示例数据 (祯休) ---")
            print(f"来源文件: {source_file_name}, 子表: {sheet_name}")
            for key, value in sample_record.items(): print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入子表 '{sheet_name}' 的全部数据？"):
                log_info(f"跳过导入子表 '{sheet_name}'.")
                continue
            for _, row in df_filled.iterrows():
                yield {
                    "term_id_text": str(row.get('题号', '无')), "term": str(row.get('词汇', '无')),
                    "source_text": str(row.get('出处', '无')), "category": str(row.get('题型', '无')),
                    "pinyin": str(row.get('拼音', '无')), "definition": str(row.get('解释', '无')),
                    "is_disyllabic": str(row.get('双音节', '无')),
                    "source_file": source_file_name, "source_sheet": sheet_name,
                }
        except Exception as e:
            log_error(f"  处理祯休子表 {sheet_name} (文件: {source_file_name}) 时出错: {e}")
            continue


# --- 数据库操作 ---
def insert_data_to_db(conn: sqlite3.Connection, table_name: str, data_iterator: Iterator[Dict[str, Any]]):
    cursor = conn.cursor()
    inserted_count = 0
    skipped_count = 0
    try:
        cursor.execute(f"PRAGMA table_info({table_name});")
        table_columns_info = cursor.fetchall()
    except sqlite3.Error as e:
        log_error(f"无法获取表 {table_name} 的列信息: {e}。请确保表已创建。")
        return
        
    if not table_columns_info:
        log_error(f"表 {table_name} 的列信息为空。请确保表已创建且非空。")
        return
    
    db_columns = [col[1] for col in table_columns_info if col[1] not in ('id', 'imported_at')]
    if not db_columns:
        log_error(f"表 {table_name} 中没有找到可插入的列 (已排除 id, imported_at)。")
        return

    placeholders = ', '.join(['?'] * len(db_columns))
    sql = f"INSERT OR IGNORE INTO {table_name} ({', '.join(db_columns)}) VALUES ({placeholders})"
    
    batch_data = []
    batch_size = 100

    for record_dict in data_iterator:
        ordered_values = []
        for col_name in db_columns:
            ordered_values.append(record_dict.get(col_name)) # .get() 默认为 None
        batch_data.append(tuple(ordered_values))

        if len(batch_data) >= batch_size:
            try:
                cursor.executemany(sql, batch_data)
                conn.commit()
                inserted_count += cursor.rowcount 
                if cursor.rowcount < len(batch_data):
                    skipped_count += (len(batch_data) - cursor.rowcount)
            except sqlite3.Error as e:
                log_error(f"批量插入数据到表 {table_name} 时出错: {e}")
                conn.rollback()
                skipped_count += len(batch_data)
            finally:
                batch_data = []
    
    if batch_data:
        try:
            cursor.executemany(sql, batch_data)
            conn.commit()
            inserted_count += cursor.rowcount
            if cursor.rowcount < len(batch_data):
                 skipped_count += (len(batch_data) - cursor.rowcount)
        except sqlite3.Error as e:
            log_error(f"插入最后一批数据到表 {table_name} 时出错: {e}")
            conn.rollback()
            skipped_count += len(batch_data)

    log_info(f"表 {table_name}: 成功插入 {inserted_count} 条记录，跳过 (重复或错误) {skipped_count} 条记录。")


# --- 主逻辑 ---
def main():
    log_info("--- 开始数据导入脚本 ---")
    db_path_for_import = None
    try:
        plugin_cfg = get_plugin_config()
        db_path_for_import = get_database_full_path() # 获取数据库的绝对路径
    except Exception as e:
        log_error(f"无法加载配置或获取数据库路径: {e}。导入中止。")
        return

    if not plugin_cfg.base_data_path or plugin_cfg.base_data_path == "your/base/data/path/":
        log_error(f"请在 config.toml 中正确配置 base_data_path。当前值: '{plugin_cfg.base_data_path}'。导入中止。")
        return
    
    base_data_dir = Path(plugin_cfg.base_data_path)
    print(base_data_dir)
    if not base_data_dir.is_dir():
        log_error(f"配置的基础数据路径 base_data_path ('{base_data_dir}') 不是一个有效的目录。导入中止。")
        return

    conn = None # 初始化 conn
    try:
        # 传递数据库路径给 get_db_connection
        conn = get_db_connection(db_path=db_path_for_import) 
        create_tables_if_not_exists(conn) 
    except Exception as e:
        log_error(f"数据库初始化失败: {e}。导入中止。")
        if conn:
            conn.close() # 确保关闭连接
        return

    parser_map: Dict[str, Dict[str, Any]] = {
        "脑洞": {"parser": parse_brainhole_excel, "table": "brainhole_terms"},
        "拼释": {"parser": parse_pinshi_excel, "table": "pinshi_terms"},
        "蝠汁牌": {"parser": parse_fuzhipai_docx, "table": "fuzhipai_cards"},
        "随蓝": {
            "parser": lambda fp, sfn: parse_simple_excel(fp, sfn, 0, 0, 
                {"题面": "term", "选手": "player", "出处": "source_text", "解释": "definition"}, "随蓝"),
            "table": "suilan_terms"
        },
        "五行": {
            "parser": lambda fp, sfn: parse_simple_excel(fp, sfn, 0, 0,
                {"词语": "term", "拼音": "pinyin", "难度": "difficulty", "出自": "source_origin", "出题人": "author", "释义": "definition"}, "五行"),
            "table": "wuxing_terms"
        },
        "元晓": {
            "parser": lambda fp, sfn: parse_simple_excel(fp, sfn, 0, 0,
                {"词汇": "term", "拼音": "pinyin", "出处": "source_text", "丽句难度": "difficulty_liju", "脑洞难度": "difficulty_naodong", "解释": "definition"}, "元晓"),
            "table": "yuanxiao_terms"
        },
        "祯休": {"parser": parse_zhenxiu_excel, "table": "zhenxiu_terms"},
    }

    for plugin_setting in plugin_cfg.plugins:
        plugin_name = plugin_setting.name
        log_info(f"\n--- 处理插件类型: {plugin_name} ---")
        if plugin_name not in parser_map:
            log_warning(f"插件 '{plugin_name}' 没有配置对应的解析器，跳过。")
            continue
        parser_config = parser_map[plugin_name]
        parser_func: Callable[[Path, str], Iterator[Dict[str, Any]]] = parser_config["parser"]
        target_table: str = parser_config["table"]
        data_folder_str = plugin_setting.folder_name
        data_folder = Path(data_folder_str) if Path(data_folder_str).is_absolute() else base_data_dir / data_folder_str
        if not data_folder.is_dir():
            log_warning(f"插件 '{plugin_name}' 的数据文件夹 '{data_folder}' 不存在，跳过。")
            continue
        for file_ext in plugin_setting.file_extensions:
            for file_path in data_folder.glob(f"*{file_ext}"):
                if file_path.is_file():
                    log_info(f"  找到文件: {file_path.name}")
                    data_iterator = parser_func(file_path, file_path.name)
                    if data_iterator: # 确保迭代器有效
                        insert_data_to_db(conn, target_table, data_iterator)
                else:
                    log_warning(f"  路径 {file_path} 不是一个文件，跳过。")
        
    log_info("\n--- 数据导入完成 ---")
    if conn:
        conn.close()
        # 清理全局连接，以便下次 get_db_connection 能重新创建
        globals()['_connection'] = None 
        log_info("数据库连接已关闭。")


if __name__ == "__main__":
    main()
