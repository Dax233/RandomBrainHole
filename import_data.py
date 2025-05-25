import sqlite3
import hashlib
from pathlib import Path
import pandas as pd
from docx import Document
import re
import sys 
from typing import Iterator, Dict, Any, Callable, List, Optional

# --- 尝试导入同级模块 ---
try:
    from .config import get_plugin_config, PluginSetting, get_database_full_path
    from .db_utils import get_db_connection, create_tables_if_not_exists, ALL_TABLE_SCHEMAS, \
                          get_last_imported_file_hash, upsert_imported_file_log # 新增导入
except ImportError:
    print("[IMPORT_SCRIPT_WARNING] 无法通过相对路径导入模块。尝试修改sys.path...")
    current_script_path = Path(__file__).resolve().parent
    project_root = current_script_path.parent 
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        print(f"[IMPORT_SCRIPT_INFO] 已将 '{project_root}' 添加到 sys.path。")
    try:
        from RandomBrainHole.config import get_plugin_config, PluginSetting, get_database_full_path
        from RandomBrainHole.db_utils import get_db_connection, create_tables_if_not_exists, ALL_TABLE_SCHEMAS, \
                                             get_last_imported_file_hash, upsert_imported_file_log # 新增导入
        print("[IMPORT_SCRIPT_INFO] 通过修改sys.path后，模块导入成功。")
    except ImportError as e:
        print(f"[IMPORT_SCRIPT_ERROR] 修改sys.path后仍然无法导入模块: {e}")
        sys.exit(1)

# --- 日志函数 ---
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

def calculate_text_sha256(text: str) -> str: # 原来的文本哈希函数
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def calculate_file_sha256(file_path: Path, buffer_size=65536) -> Optional[str]: # 新增文件哈希函数
    """计算文件的 SHA256 哈希值"""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(buffer_size), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        log_error(f"计算文件哈希失败：文件未找到 {file_path}")
        return None
    except Exception as e:
        log_error(f"计算文件哈希 {file_path} 时发生错误: {e}")
        return None

# --- 数据解析函数 ---

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
            
            # 示例输出与确认 (对每个子表)
            if not data_df.empty:
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
                if win_rate_val not in ['暂无', None, '']: # type: ignore
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
        
        # 示例输出与确认 (对整个文件)
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
            title = card_text.split('\n', 1)[0][:255] if '\n' in card_text else card_text[:255] # 限制标题长度
            full_text_hash = calculate_text_sha256(card_text) # 计算哈希用于唯一性
            yield {
                "card_title": title, 
                "full_text": card_text,
                "full_text_hash": full_text_hash, 
                "source_file": source_file_name,
            }
    except Exception as e: # 更具体的错误捕获，例如 docx.opc.exceptions.PackageNotFoundError
        if "File is not a zip file" in str(e):
             log_error(f"处理蝠汁牌文件 {source_file_name} 时出错: 文件可能不是有效的 .docx 格式 (而是旧版 .doc)。请转换为 .docx 后重试。错误: {e}")
        else:
            log_error(f"处理蝠汁牌文件 {source_file_name} 时出错: {e}")
        return

def parse_pinshi_excel(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]:
    log_info(f"开始解析拼释文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path) 
        actual_sheet_name = xls.sheet_names[0] if xls.sheet_names else "Sheet1"
        df = pd.read_excel(xls, sheet_name=0, header=0) # 通常第一行为表头
        if df.empty:
            log_warning(f"拼释文件 {source_file_name} (子表: {actual_sheet_name}) 数据为空。")
            return

        # 示例输出与确认 (对每个子表，虽然这里通常只有一个)
        if not df.empty:
            sample_record = df.iloc[0].to_dict()
            print("\n--- 示例数据 (拼释) ---")
            print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
            for key, value in sample_record.items(): print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"):
                log_info(f"跳过导入子表 '{actual_sheet_name}'.")
                return # 如果不导入这个sheet，对于单sheet文件相当于跳过整个文件

        for _, row in df.iterrows():
            yield {
                "term": str(row.get('题目', '')),       # DB: term
                "pinyin": str(row.get('拼音', '')),      # DB: pinyin
                "source_text": str(row.get('出处', '')), # DB: source_text
                "writing": str(row.get('书写', '')),    # DB: writing
                "difficulty": str(row.get('难度', '')), # DB: difficulty
                "definition": str(row.get('解释', '')),  # DB: definition
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理拼释文件 {source_file_name} 时出错: {e}")
        return

def parse_suilan_excel(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]: #
    log_info(f"开始解析随蓝文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
        if len(xls.sheet_names) < 2: # 原逻辑是读取第二个子表
            log_warning(f"随蓝文件 {source_file_name} 工作表数量不足2，无法找到随蓝词表。")
            return
        
        actual_sheet_name = xls.sheet_names[1] # 第二个子表 (索引为1)
        df = pd.read_excel(xls, sheet_name=actual_sheet_name, header=0) # 第一行为表头

        if df.empty:
            log_warning(f"随蓝文件 {source_file_name} (子表: {actual_sheet_name}) 数据为空。")
            return

        if not df.empty:
            sample_record = df.iloc[0].to_dict()
            print("\n--- 示例数据 (随蓝) ---")
            print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
            for key, value in sample_record.items(): print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"):
                log_info(f"跳过导入子表 '{actual_sheet_name}'.")
                return

        for _, row in df.iterrows():
            yield {
                "term": str(row.get('题面', '')),         # DB: term
                "player": str(row.get('选手', '')),       # DB: player
                "source_text": str(row.get('出处', '')),  # DB: source_text
                "definition": str(row.get('解释', '')),   # DB: definition
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理随蓝文件 {source_file_name} 时出错: {e}")
        return

def parse_wuxing_excel(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]: #
    log_info(f"开始解析五行文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
        actual_sheet_name = xls.sheet_names[0] if xls.sheet_names else "Sheet1"
        df = pd.read_excel(xls, sheet_name=0, header=0) # 第一行作为表头

        if df.empty:
            log_warning(f"五行文件 {source_file_name} (子表: {actual_sheet_name}) 数据为空。")
            return

        if not df.empty:
            sample_record = df.iloc[0].to_dict()
            print("\n--- 示例数据 (五行) ---")
            print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
            for key, value in sample_record.items(): print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"):
                log_info(f"跳过导入子表 '{actual_sheet_name}'.")
                return

        for _, row in df.iterrows():
            yield {
                "term": str(row.get('词语', '')),           # DB: term
                "pinyin": str(row.get('拼音', '')),          # DB: pinyin
                "difficulty": str(row.get('难度', '')),     # DB: difficulty
                "source_origin": str(row.get('出自', '')), # DB: source_origin
                "author": str(row.get('出题人', '')),       # DB: author
                "definition": str(row.get('释义', '')),      # DB: definition
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理五行文件 {source_file_name} 时出错: {e}")
        return

def parse_yuanxiao_excel(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]: #
    log_info(f"开始解析元晓文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
        actual_sheet_name = xls.sheet_names[0] if xls.sheet_names else "Sheet1"
        df = pd.read_excel(xls, sheet_name=0, header=0) # 第一行作为表头

        if df.empty:
            log_warning(f"元晓文件 {source_file_name} (子表: {actual_sheet_name}) 数据为空。")
            return
        
        if not df.empty:
            sample_record = df.iloc[0].to_dict()
            print("\n--- 示例数据 (元晓) ---")
            print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
            for key, value in sample_record.items(): print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"):
                log_info(f"跳过导入子表 '{actual_sheet_name}'.")
                return

        for _, row in df.iterrows():
            yield {
                "term": str(row.get('词汇', '')),                   # DB: term
                "pinyin": str(row.get('拼音', '')),                  # DB: pinyin
                "source_text": str(row.get('出处', '')),              # DB: source_text
                "difficulty_liju": str(row.get('丽句难度', '')),     # DB: difficulty_liju
                "difficulty_naodong": str(row.get('脑洞难度', '')), # DB: difficulty_naodong
                "definition": str(row.get('解释', '')),              # DB: definition
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理元晓文件 {source_file_name} 时出错: {e}")
        return

def parse_zhenxiu_excel(file_path: Path, source_file_name: str) -> Iterator[Dict[str, Any]]: #
    log_info(f"开始解析祯休文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        log_error(f"打开祯休Excel文件 {file_path} 失败: {e}")
        return

    for sheet_name in xls.sheet_names: # 祯休是随机选择一个子表，导入时我们处理所有子表
        log_info(f"  正在处理子表: {sheet_name}")
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=2) # 表头在第3行 (0-indexed)
            if df.empty:
                log_warning(f"  祯休子表 {sheet_name} 为空。")
                continue
            
            df_filled = df.fillna('无') # 填充NaN

            if not df_filled.empty:
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
                    "term_id_text": str(row.get('题号', '无')),    # DB: term_id_text
                    "term": str(row.get('词汇', '无')),          # DB: term
                    "source_text": str(row.get('出处', '无')),   # DB: source_text
                    "category": str(row.get('题型', '无')),     # DB: category
                    "pinyin": str(row.get('拼音', '无')),        # DB: pinyin
                    "definition": str(row.get('解释', '无')),    # DB: definition
                    "is_disyllabic": str(row.get('双音节', '无')),# DB: is_disyllabic
                    "source_file": source_file_name,
                    "source_sheet": sheet_name,                 # source_sheet 对祯休很重要
                }
        except Exception as e:
            log_error(f"  处理祯休子表 {sheet_name} (文件: {source_file_name}) 时出错: {e}")
            continue

# --- 数据库操作 (保持不变) ---
def insert_data_to_db(conn: sqlite3.Connection, table_name: str, data_iterator: Iterator[Dict[str, Any]]):
    # ... (与之前版本相同的 insert_data_to_db 函数代码) ...
    cursor = conn.cursor()
    inserted_count = 0
    skipped_count = 0
    try:
        cursor.execute(f"PRAGMA table_info({table_name});") # nosec
        table_columns_info = cursor.fetchall()
    except sqlite3.Error as e:
        log_error(f"无法获取表 {table_name} 的列信息: {e}。请确保表已创建。"); return
    if not table_columns_info:
        log_error(f"表 {table_name} 的列信息为空。请确保表已创建且非空。"); return
    db_columns = [col[1] for col in table_columns_info if col[1] not in ('id', 'imported_at')]
    if not db_columns:
        log_error(f"表 {table_name} 中没有找到可插入的列 (已排除 id, imported_at)。"); return
    placeholders = ', '.join(['?'] * len(db_columns))
    sql = f"INSERT OR IGNORE INTO {table_name} ({', '.join(db_columns)}) VALUES ({placeholders})" # nosec
    batch_data = []; batch_size = 100
    for record_dict in data_iterator:
        ordered_values = [record_dict.get(col_name) for col_name in db_columns]
        batch_data.append(tuple(ordered_values))
        if len(batch_data) >= batch_size:
            try:
                cursor.executemany(sql, batch_data); conn.commit(); inserted_count += cursor.rowcount
                if cursor.rowcount < len(batch_data): skipped_count += (len(batch_data) - cursor.rowcount)
            except sqlite3.Error as e:
                log_error(f"批量插入数据到表 {table_name} 时出错: {e}"); conn.rollback(); skipped_count += len(batch_data)
            finally: batch_data = []
    if batch_data:
        try:
            cursor.executemany(sql, batch_data); conn.commit(); inserted_count += cursor.rowcount
            if cursor.rowcount < len(batch_data): skipped_count += (len(batch_data) - cursor.rowcount)
        except sqlite3.Error as e:
            log_error(f"插入最后一批数据到表 {table_name} 时出错: {e}"); conn.rollback(); skipped_count += len(batch_data)
    log_info(f"表 {table_name}: 成功插入 {inserted_count} 条记录，跳过 (重复或错误) {skipped_count} 条记录。")

# --- 主逻辑 (修改以集成哈希检查) ---
def main():
    log_info("--- 开始数据导入脚本 (带哈希检查) ---")
    db_path_for_import: Optional[Path] = None
    plugin_cfg: Optional[Any] = None
    try:
        plugin_cfg = get_plugin_config()
        db_path_for_import = get_database_full_path()
    except Exception as e:
        log_error(f"无法加载配置或获取数据库路径: {e}。导入中止。"); return

    if not plugin_cfg.base_data_path or plugin_cfg.base_data_path == "your/base/data/path/":
        log_error(f"请在 config.toml 中正确配置 base_data_path。导入中止。"); return
    base_data_dir = Path(plugin_cfg.base_data_path)
    log_info(f"使用基础数据路径: {base_data_dir.resolve()}")
    if not base_data_dir.is_dir():
        log_error(f"配置的基础数据路径 ('{base_data_dir.resolve()}') 无效。导入中止。"); return

    conn = None
    try:
        conn = get_db_connection(db_path=db_path_for_import) 
        create_tables_if_not_exists(conn) # 确保所有表（包括imported_files_log）都已创建
    except Exception as e:
        log_error(f"数据库初始化失败: {e}。导入中止。");
        if conn: conn.close(); globals()['_connection'] = None
        return

    parser_map: Dict[str, Dict[str, Any]] = {
        "脑洞": {"parser": parse_brainhole_excel, "table": "brainhole_terms"},
        "拼释": {"parser": parse_pinshi_excel, "table": "pinshi_terms"},
        "蝠汁牌": {"parser": parse_fuzhipai_docx, "table": "fuzhipai_cards"},
        "随蓝": {"parser": parse_suilan_excel, "table": "suilan_terms"},
        "五行": {"parser": parse_wuxing_excel, "table": "wuxing_terms"},
        "元晓": {"parser": parse_yuanxiao_excel, "table": "yuanxiao_terms"},
        "祯休": {"parser": parse_zhenxiu_excel, "table": "zhenxiu_terms"},
    }

    for plugin_setting in plugin_cfg.plugins:
        plugin_name = plugin_setting.name
        log_info(f"\n--- 处理插件类型: {plugin_name} ---")
        if plugin_name not in parser_map:
            log_warning(f"插件 '{plugin_name}' 没有配置对应的解析器，跳过。"); continue
        
        parser_config = parser_map[plugin_name]
        parser_func = parser_config["parser"]
        target_table = parser_config["table"]
        
        data_folder_str = plugin_setting.folder_name
        data_folder = Path(data_folder_str) if Path(data_folder_str).is_absolute() else base_data_dir / data_folder_str
        
        if not data_folder.is_dir():
            log_warning(f"插件 '{plugin_name}' 数据文件夹 '{data_folder.resolve()}' 不存在，跳过。"); continue
        log_info(f"  正在扫描文件夹: {data_folder.resolve()}")

        file_found_for_plugin = False
        for file_ext in plugin_setting.file_extensions:
            for file_path in data_folder.glob(f"*{file_ext}"):
                file_found_for_plugin = True
                if not file_path.is_file():
                    log_warning(f"    路径 {file_path} 不是一个文件，跳过。"); continue
                
                log_info(f"    找到文件: {file_path.name}")
                
                # --- 哈希检查逻辑 ---
                # 使用相对路径作为文件标识符（相对于 base_data_dir），或者文件名+plugin_name
                try:
                    file_identifier = f"{plugin_name}_{file_path.name}" # 简化标识符
                except Exception: # Path object may not be relative if base_data_dir is not its parent
                    file_identifier = f"{plugin_name}_{file_path.name}"

                current_file_hash = calculate_file_sha256(file_path)
                if current_file_hash is None: # 哈希计算失败
                    log_warning(f"    无法计算文件 {file_path.name} 的哈希值，将尝试处理。");
                    # 如果哈希失败，可以选择跳过或继续处理，这里选择继续但会有风险
                
                last_hash = get_last_imported_file_hash(conn, file_identifier)

                if current_file_hash and last_hash == current_file_hash:
                    log_info(f"    文件 {file_path.name} (Hash: {current_file_hash[:8]}...) 未更改，跳过处理。")
                    upsert_imported_file_log(conn, file_identifier, current_file_hash, "skipped_unchanged", plugin_name)
                    continue # 跳到下一个文件
                
                log_info(f"    文件 {file_path.name} 是新文件或已更改 (CurrentHash: {current_file_hash[:8] if current_file_hash else 'N/A'}, LastHash: {last_hash[:8] if last_hash else 'N/A'})。准备处理...")

                # --- 用户确认逻辑 (现在在哈希检查之后) ---
                # 为了简化，这里的示例确认放在解析函数内部进行（如果解析函数返回了数据）
                # 更优的做法是将解析和确认分离，先解析一部分获取示例
                
                data_iterator = parser_func(file_path, file_path.name) # 解析函数内部现在包含用户确认
                
                if data_iterator:
                    # 收集迭代器内容以判断是否真的有数据被yield（因为确认后可能不yield）
                    data_to_insert = list(data_iterator)
                    if data_to_insert:
                        log_info(f"    确认通过，开始将 '{file_path.name}' 的数据插入表 '{target_table}'...")
                        insert_data_to_db(conn, target_table, iter(data_to_insert)) # 重新转为迭代器
                        if current_file_hash: # 仅当哈希计算成功时记录
                             upsert_imported_file_log(conn, file_identifier, current_file_hash, "imported", plugin_name)
                    else:
                        log_info(f"    文件 '{file_path.name}' 解析后未产生数据或用户取消导入。")
                        if current_file_hash: # 即使没有数据，也记录为检查过（如果哈希成功）
                            upsert_imported_file_log(conn, file_identifier, current_file_hash, "processed_no_data_or_cancelled", plugin_name)
                else: # 解析函数可能因为内部错误直接返回 None 或空的迭代器
                    log_warning(f"    解析文件 '{file_path.name}' 未返回有效数据迭代器。")
                    if current_file_hash:
                        upsert_imported_file_log(conn, file_identifier, current_file_hash, "parse_failed", plugin_name)


        if not file_found_for_plugin:
            log_warning(f"  在文件夹 '{data_folder.resolve()}' 中未找到扩展名为 {plugin_setting.file_extensions} 的文件。")
        
    log_info("\n--- 数据导入完成 ---")
    if conn:
        conn.close()
        globals()['_connection'] = None
        log_info("数据库连接已关闭。")

if __name__ == "__main__":
    main()