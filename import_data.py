import sqlite3
import hashlib
import asyncio
from pathlib import Path
import pandas as pd  # 用于解析 Excel 文件
from docx import Document  # 用于解析 Word (.docx) 文件
import re
import sys
from typing import Iterator, Dict, Any, Callable, Optional

# --- 尝试导入同级模块 ---
# 这个脚本主要用于独立运行，导入数据到数据库。
# 因此，它需要能够找到项目中的其他模块 (config, db_utils)。
# 这里的 try-except 块是为了处理直接运行此脚本时 Python 的模块搜索路径问题。
try:
    # 尝试相对导入 (当作为包的一部分被调用时)
    from .config import get_plugin_config, get_database_full_path
    from .db_utils import (
        get_db_connection,
        create_tables_if_not_exists,
        get_last_imported_file_hash,
        upsert_imported_file_log,
    )
except ImportError:
    # 如果相对导入失败 (通常是直接运行此脚本时)，则尝试修改 sys.path
    print("[IMPORT_SCRIPT_WARNING] 无法通过相对路径导入模块。尝试修改sys.path...")
    current_script_path = (
        Path(__file__).resolve().parent
    )  # 当前脚本的父目录 (RandomBrainHole)
    project_root = current_script_path.parent  # 项目根目录 (RandomBrainHole 的上一级)
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))  # 将项目根目录添加到 sys.path 的开头
        print(f"[IMPORT_SCRIPT_INFO] 已将 '{project_root}' 添加到 sys.path。")
    try:
        # 再次尝试导入 (此时应该是从项目根目录开始的绝对导入)
        from RandomBrainHole.config import (
            get_plugin_config,
            get_database_full_path,
        )
        from RandomBrainHole.db_utils import (
            get_db_connection,
            create_tables_if_not_exists,
            get_last_imported_file_hash,
            upsert_imported_file_log,
        )

        print("[IMPORT_SCRIPT_INFO] 通过修改sys.path后，模块导入成功。")
    except ImportError as e:
        print(f"[IMPORT_SCRIPT_ERROR] 修改sys.path后仍然无法导入模块: {e}")
        sys.exit(1)  # 导入失败则退出脚本


# --- 日志函数 ---
# 简单的日志函数，用于在控制台输出信息
def log_info(message: str):
    print(f"[INFO] {message}")


def log_warning(message: str):
    print(f"[WARNING] {message}")


def log_error(message: str):
    print(f"[ERROR] {message}")


# --- 辅助函数 ---
def get_user_confirmation(prompt: str) -> bool:
    """
    向用户显示一个提示，并获取用户的确认 (y/n)。

    :param prompt: 显示给用户的提示信息。
    :return: 如果用户输入 'y' 则返回 True，否则返回 False。
    """
    while True:
        response = input(f"{prompt} (y/n): ").strip().lower()
        if response == "y":
            return True
        if response == "n":
            return False
        print("无效输入，请输入 'y' 或 'n'.")


def calculate_text_sha256(text: str) -> str:
    """计算给定文本的 SHA256 哈希值。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def calculate_file_sha256(file_path: Path, buffer_size=65536) -> Optional[str]:
    """
    计算文件的 SHA256 哈希值。
    用于比较文件内容是否发生变化，避免重复导入未更改的文件。

    :param file_path: 文件的 Path 对象。
    :param buffer_size: 读取文件时使用的缓冲区大小。
    :return: 文件的 SHA256 哈希值 (str) 或 None (如果文件未找到或计算出错)。
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:  # 以二进制读取模式打开文件
            # 分块读取文件内容并更新哈希对象，适用于大文件
            for byte_block in iter(lambda: f.read(buffer_size), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()  # 返回十六进制表示的哈希值
    except FileNotFoundError:
        log_error(f"计算文件哈希失败：文件未找到 {file_path}")
        return None
    except Exception as e:
        log_error(f"计算文件哈希 {file_path} 时发生错误: {e}")
        return None


# --- 数据解析函数 ---
# 下面是一系列针对不同类型词库文件 (主要是 Excel 和 Word) 的解析函数。
# 每个解析函数都接受文件路径和文件名作为输入，并返回一个迭代器，
# 该迭代器逐条产出从文件中解析出来的数据记录 (以字典形式)。
# 解析函数内部通常会包含对数据格式的特定处理逻辑，
# 以及在处理前向用户展示示例数据并请求确认的步骤。


def parse_brainhole_excel(
    file_path: Path, source_file_name: str
) -> Iterator[Dict[str, Any]]:
    """
    解析“脑洞”类型的 Excel 文件。
    脑洞文件通常包含多个工作表 (sheet)，第一个是总览，其余为具体场次数据。
    """
    log_info(f"开始解析脑洞文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)  # 打开 Excel 文件
    except Exception as e:
        log_error(f"打开脑洞Excel文件 {file_path} 失败: {e}")
        return  # 返回空迭代器

    sheet_names = xls.sheet_names
    if not sheet_names:
        log_warning(f"脑洞文件 {source_file_name} 中没有工作表。")
        return

    # 通常第一个 sheet 是总览，数据从第二个 sheet 开始
    data_sheets = sheet_names[1:] if len(sheet_names) > 1 else sheet_names
    if not data_sheets:
        log_warning(f"脑洞文件 {source_file_name} 除去总览表后没有数据表。")
        return

    for sheet_name in data_sheets:  # 遍历每个数据工作表
        log_info(f"  正在处理子表: {sheet_name}")
        try:
            df = pd.read_excel(
                xls, sheet_name=sheet_name, header=None
            )  # 读取时不指定表头
            if df.empty:
                log_warning(f"  子表 {sheet_name} 为空。")
                continue

            # 提取场次名称 (通常在第一行第一列)
            match_name = (
                str(df.iloc[0, 0])
                if len(df.index) > 0 and len(df.columns) > 0
                else "未知场次"
            )

            # 表头通常在第二行，数据从第三行开始
            if len(df.index) > 1:
                df.columns = df.iloc[1].astype(str)  # 将第二行设为列名
                data_df = df[2:].reset_index(drop=True)  # 获取数据部分
            else:
                log_warning(f"  子表 {sheet_name} 行数不足，无法解析表头和数据。")
                continue

            if data_df.empty:
                log_warning(f"  子表 {sheet_name} 移除表头后数据为空。")
                continue

            # 示例输出与确认 (对每个子表)
            if not data_df.empty:
                sample_record = data_df.iloc[0].to_dict()  # 取第一条数据作为示例
                print("\n--- 示例数据 (脑洞) ---")
                print(
                    f"来源文件: {source_file_name}, 子表: {sheet_name}, 场次: {match_name}"
                )
                for key, value in sample_record.items():
                    print(f"  {key}: {value}")
                print("------------------------")
                if not get_user_confirmation(
                    f"以上示例数据解析是否正确？是否继续导入子表 '{sheet_name}' 的全部数据？"
                ):
                    log_info(f"跳过导入子表 '{sheet_name}'.")
                    continue  # 用户取消则跳过此子表

            # 遍历数据行，构造字典并产出
            for _, row in data_df.iterrows():
                author = str(row.get("出题人", "暂无"))
                if author == "——":
                    author = "盐铁桶子"  # 特殊处理
                win_rate_val = row.get("胜率", "暂无")
                win_rate_str = "暂无"
                if win_rate_val not in ["暂无", None, ""]:
                    try:
                        win_rate_str = (
                            f"{float(win_rate_val) * 100:.1f}%"  # 胜率格式化为百分比
                        )
                    except (ValueError, TypeError):
                        win_rate_str = str(win_rate_val)

                yield {  # 产出解析后的数据记录
                    "match_name": match_name,
                    "term": str(row.get("词汇", "")),
                    "pinyin": str(row.get("拼音", "")),
                    "difficulty": str(row.get("难度", "")),
                    "win_rate": win_rate_str,
                    "category": str(row.get("类型", "")),
                    "author": author,
                    "definition": str(row.get("解释", "")),
                    "source_file": source_file_name,  # 记录来源文件名
                    "source_sheet": sheet_name,  # 记录来源工作表名
                }
        except Exception as e:
            log_error(
                f"  处理脑洞子表 {sheet_name} (文件: {source_file_name}) 时出错: {e}"
            )
            continue  # 单个子表出错不影响其他子表或文件


def parse_fuzhipai_docx(
    file_path: Path, source_file_name: str
) -> Iterator[Dict[str, Any]]:
    """
    解析“蝠汁牌”类型的 Word (.docx) 文件。
    蝠汁牌数据通常以特定格式（如编号+【标题】）开始，卡牌内容可能包含斜体。
    """
    log_info(f"开始解析蝠汁牌文件: {source_file_name}")
    try:
        doc = Document(file_path)  # 打开 Word 文档
        cards_text_list = []  # 存储提取的卡牌文本
        active_card_content_lines = []  # 存储当前正在处理的卡牌的文本行

        # 遍历文档中的段落
        for para in doc.paragraphs:
            para_text_raw = para.text.strip()  # 获取段落原始文本并去除首尾空格

            # 使用正则表达式匹配卡牌开始的模式 (例如 "A01【卡牌标题】")
            if re.match(r"^[A-Za-z0-9]+【.*?】", para_text_raw):
                # 如果匹配到新的卡牌开始，则先处理上一张卡牌的内容
                if active_card_content_lines:
                    full_card_text = "\n".join(active_card_content_lines).strip()
                    if full_card_text:
                        cards_text_list.append(full_card_text)
                    active_card_content_lines = []  # 清空，准备存储新卡牌内容

            # 处理段落内文本，保留斜体标记 ([斜体内容])
            current_para_formatted_text = ""
            is_currently_italic = False
            for run in para.runs:  # 遍历段落中的文本片段 (run)
                if run.italic:  # 如果是斜体
                    if not is_currently_italic:
                        current_para_formatted_text += "["  # 添加斜体开始标记
                        is_currently_italic = True
                    current_para_formatted_text += run.text
                else:  # 如果不是斜体
                    if is_currently_italic:
                        current_para_formatted_text += "]"  # 添加斜体结束标记
                        is_currently_italic = False
                    current_para_formatted_text += run.text
            if is_currently_italic:
                current_para_formatted_text += "]"  # 处理段落末尾的斜体

            if current_para_formatted_text.strip():  # 如果格式化后的文本不为空
                active_card_content_lines.append(current_para_formatted_text.strip())

        # 处理文档末尾的最后一张卡牌
        if active_card_content_lines:
            full_card_text = "\n".join(active_card_content_lines).strip()
            if full_card_text:
                cards_text_list.append(full_card_text)

        if not cards_text_list:
            log_warning(f"蝠汁牌文件 {source_file_name} 未提取到卡牌。")
            return

        # 示例输出与确认 (对整个文件)
        sample_card_text = cards_text_list[0]
        # 尝试从卡牌文本的第一行提取标题
        sample_card_title = (
            sample_card_text.split("\n", 1)[0]
            if "\n" in sample_card_text
            else sample_card_text
        )
        print("\n--- 示例数据 (蝠汁牌) ---")
        print(f"来源文件: {source_file_name}")
        print(f"  示例卡牌标题 (尝试提取): {sample_card_title}")
        print(f"  示例卡牌内容 (前100字符): {sample_card_text[:100]}...")
        print("------------------------")
        if not get_user_confirmation(
            f"以上示例数据解析是否正确？是否继续导入文件 '{source_file_name}' 的全部数据？"
        ):
            log_info(f"跳过导入文件 '{source_file_name}'.")
            return

        # 遍历提取的卡牌文本，构造字典并产出
        for card_text in cards_text_list:
            # 提取标题，限制长度以适应数据库字段
            title = (
                card_text.split("\n", 1)[0][:255]
                if "\n" in card_text
                else card_text[:255]
            )
            full_text_hash = calculate_text_sha256(
                card_text
            )  # 计算卡牌全文的哈希值，用于唯一性检查
            yield {
                "card_title": title,
                "full_text": card_text,
                "full_text_hash": full_text_hash,
                "source_file": source_file_name,
            }
    except Exception as e:
        # 特别处理 docx 文件格式错误 (例如打开了 .doc 文件)
        if "File is not a zip file" in str(e) or "Package not found" in str(e):
            log_error(
                f"处理蝠汁牌文件 {source_file_name} 时出错: 文件可能不是有效的 .docx 格式 (例如是旧版 .doc)。请转换为 .docx 后重试。错误: {e}"
            )
        else:
            log_error(f"处理蝠汁牌文件 {source_file_name} 时出错: {e}")
        return


def parse_pinshi_excel(
    file_path: Path, source_file_name: str
) -> Iterator[Dict[str, Any]]:
    """解析“拼释”类型的 Excel 文件。通常只有一个工作表，第一行为表头。"""
    log_info(f"开始解析拼释文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
        actual_sheet_name = (
            xls.sheet_names[0] if xls.sheet_names else "Sheet1"
        )  # 获取第一个工作表名
        df = pd.read_excel(
            xls, sheet_name=0, header=0
        )  # 读取第一个工作表，第一行为表头

        if df.empty:
            log_warning(
                f"拼释文件 {source_file_name} (子表: {actual_sheet_name}) 数据为空。"
            )
            return

        # 示例输出与确认
        if not df.empty:
            sample_record = df.iloc[0].to_dict()
            print("\n--- 示例数据 (拼释) ---")
            print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
            for key, value in sample_record.items():
                print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(
                f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"
            ):
                log_info(f"跳过导入子表 '{actual_sheet_name}'.")
                return

        # 遍历数据行，构造字典并产出
        for _, row in df.iterrows():
            yield {
                "term": str(row.get("题目", "")),  # 对应数据库字段: term
                "pinyin": str(row.get("拼音", "")),  # 对应数据库字段: pinyin
                "source_text": str(row.get("出处", "")),  # 对应数据库字段: source_text
                "writing": str(row.get("书写", "")),  # 对应数据库字段: writing
                "difficulty": str(row.get("难度", "")),  # 对应数据库字段: difficulty
                "definition": str(row.get("解释", "")),  # 对应数据库字段: definition
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理拼释文件 {source_file_name} 时出错: {e}")
        return


# 其他类型的解析函数 (parse_suilan_excel, parse_wuxing_excel, parse_yuanxiao_excel, parse_zhenxiu_excel)
# 结构与 parse_pinshi_excel 或 parse_brainhole_excel 类似，主要区别在于：
# 1. 读取的 Excel 工作表索引或名称。
# 2. 表头所在行。
# 3. 从行数据中提取的字段名 (row.get('列名')) 及其对应的数据库字段名。
# 4. 示例输出时的提示信息。
# 这些函数的注释可以参考上述两个函数的模式进行添加，此处为简洁省略重复的详细注释结构。


def parse_suilan_excel(
    file_path: Path, source_file_name: str
) -> Iterator[Dict[str, Any]]:
    log_info(f"开始解析随蓝文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
        if len(xls.sheet_names) < 2:  # 随蓝数据在第二个子表
            log_warning(
                f"随蓝文件 {source_file_name} 工作表数量不足2，无法找到随蓝词表。"
            )
            return

        actual_sheet_name = xls.sheet_names[1]  # 第二个子表 (索引为1)
        df = pd.read_excel(xls, sheet_name=actual_sheet_name, header=0)

        if df.empty:
            log_warning(
                f"随蓝文件 {source_file_name} (子表: {actual_sheet_name}) 数据为空。"
            )
            return

        if not df.empty:  # 示例与确认
            sample_record = df.iloc[0].to_dict()
            print("\n--- 示例数据 (随蓝) ---")
            print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
            for key, value in sample_record.items():
                print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(
                f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"
            ):
                log_info(f"跳过导入子表 '{actual_sheet_name}'.")
                return

        for _, row in df.iterrows():
            yield {
                "term": str(row.get("题面", "")),
                "player": str(row.get("选手", "")),
                "source_text": str(row.get("出处", "")),
                "definition": str(row.get("解释", "")),
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理随蓝文件 {source_file_name} 时出错: {e}")
        return


def parse_wuxing_excel(
    file_path: Path, source_file_name: str
) -> Iterator[Dict[str, Any]]:
    log_info(f"开始解析五行文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
        actual_sheet_name = xls.sheet_names[0] if xls.sheet_names else "Sheet1"
        df = pd.read_excel(xls, sheet_name=0, header=0)

        if df.empty:
            log_warning(
                f"五行文件 {source_file_name} (子表: {actual_sheet_name}) 数据为空。"
            )
            return

        if not df.empty:  # 示例与确认
            sample_record = df.iloc[0].to_dict()
            print("\n--- 示例数据 (五行) ---")
            print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
            for key, value in sample_record.items():
                print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(
                f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"
            ):
                log_info(f"跳过导入子表 '{actual_sheet_name}'.")
                return

        for _, row in df.iterrows():
            yield {
                "term": str(row.get("词语", "")),
                "pinyin": str(row.get("拼音", "")),
                "difficulty": str(row.get("难度", "")),
                "source_origin": str(row.get("出自", "")),
                "author": str(row.get("出题人", "")),
                "definition": str(row.get("释义", "")),
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理五行文件 {source_file_name} 时出错: {e}")
        return


def parse_yuanxiao_excel(
    file_path: Path, source_file_name: str
) -> Iterator[Dict[str, Any]]:
    log_info(f"开始解析元晓文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
        actual_sheet_name = xls.sheet_names[0] if xls.sheet_names else "Sheet1"
        df = pd.read_excel(xls, sheet_name=0, header=0)

        if df.empty:
            log_warning(
                f"元晓文件 {source_file_name} (子表: {actual_sheet_name}) 数据为空。"
            )
            return

        if not df.empty:  # 示例与确认
            sample_record = df.iloc[0].to_dict()
            print("\n--- 示例数据 (元晓) ---")
            print(f"来源文件: {source_file_name}, 子表: {actual_sheet_name}")
            for key, value in sample_record.items():
                print(f"  {key}: {value}")
            print("------------------------")
            if not get_user_confirmation(
                f"以上示例数据解析是否正确？是否继续导入子表 '{actual_sheet_name}' 的全部数据？"
            ):
                log_info(f"跳过导入子表 '{actual_sheet_name}'.")
                return

        for _, row in df.iterrows():
            yield {
                "term": str(row.get("词汇", "")),
                "pinyin": str(row.get("拼音", "")),
                "source_text": str(row.get("出处", "")),
                "difficulty_liju": str(row.get("丽句难度", "")),
                "difficulty_naodong": str(row.get("脑洞难度", "")),
                "definition": str(row.get("解释", "")),
                "source_file": source_file_name,
                "source_sheet": actual_sheet_name,
            }
    except Exception as e:
        log_error(f"处理元晓文件 {source_file_name} 时出错: {e}")
        return


def parse_zhenxiu_excel(
    file_path: Path, source_file_name: str
) -> Iterator[Dict[str, Any]]:
    """解析“祯休”类型的 Excel 文件，祯休文件可能包含多个子表，表头在第3行。"""
    log_info(f"开始解析祯休文件: {source_file_name}")
    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        log_error(f"打开祯休Excel文件 {file_path} 失败: {e}")
        return

    for sheet_name in xls.sheet_names:  # 遍历所有子表
        log_info(f"  正在处理子表: {sheet_name}")
        try:
            df = pd.read_excel(
                xls, sheet_name=sheet_name, header=2
            )  # 表头在第3行 (0-indexed)
            if df.empty:
                log_warning(f"  祯休子表 {sheet_name} 为空。")
                continue

            df_filled = df.fillna("无")  # 将 NaN 值填充为 '无'

            if not df_filled.empty:  # 示例与确认
                sample_record = df_filled.iloc[0].to_dict()
                print("\n--- 示例数据 (祯休) ---")
                print(f"来源文件: {source_file_name}, 子表: {sheet_name}")
                for key, value in sample_record.items():
                    print(f"  {key}: {value}")
                print("------------------------")
                if not get_user_confirmation(
                    f"以上示例数据解析是否正确？是否继续导入子表 '{sheet_name}' 的全部数据？"
                ):
                    log_info(f"跳过导入子表 '{sheet_name}'.")
                    continue

            for _, row in df_filled.iterrows():
                yield {
                    "term_id_text": str(row.get("题号", "无")),
                    "term": str(row.get("词汇", "无")),
                    "source_text": str(row.get("出处", "无")),
                    "category": str(row.get("题型", "无")),
                    "pinyin": str(row.get("拼音", "无")),
                    "definition": str(row.get("解释", "无")),
                    "is_disyllabic": str(row.get("双音节", "无")),
                    "source_file": source_file_name,
                    "source_sheet": sheet_name,  # 祯休的 source_sheet 很重要
                }
        except Exception as e:
            log_error(
                f"  处理祯休子表 {sheet_name} (文件: {source_file_name}) 时出错: {e}"
            )
            continue


# --- 数据库操作 ---
def insert_data_to_db(
    conn: sqlite3.Connection, table_name: str, data_iterator: Iterator[Dict[str, Any]]
):
    """
    将从解析函数获取的数据批量插入到指定的数据库表中。
    使用 INSERT OR IGNORE 避免因唯一性约束导致重复插入失败。

    :param conn: sqlite3.Connection 对象。
    :param table_name: 目标数据库表名。
    :param data_iterator: 包含待插入数据的迭代器 (每个元素是一个字典)。
    """
    cursor = conn.cursor()
    inserted_count = 0  # 成功插入的记录数
    skipped_count = 0  # 因重复或错误而跳过的记录数

    try:
        # 获取目标表的列信息，以确保插入数据时列的顺序正确，并排除自增ID和时间戳列
        cursor.execute(f"PRAGMA table_info({table_name});")  # nosec B608 (table_name 来自配置，相对安全)
        table_columns_info = cursor.fetchall()
    except sqlite3.Error as e:
        log_error(f"无法获取表 {table_name} 的列信息: {e}。请确保表已创建。")
        return

    if not table_columns_info:
        log_error(f"表 {table_name} 的列信息为空。请确保表已创建且非空。")
        return

    # 提取需要插入数据的列名 (排除自增的 id 和自动更新的 imported_at)
    db_columns = [
        col[1] for col in table_columns_info if col[1] not in ("id", "imported_at")
    ]
    if not db_columns:
        log_error(f"表 {table_name} 中没有找到可插入的列 (已排除 id, imported_at)。")
        return

    placeholders = ", ".join(["?"] * len(db_columns))  # 生成 SQL 占位符
    # 使用 INSERT OR IGNORE，如果违反唯一约束，则忽略该条记录
    sql = f"INSERT OR IGNORE INTO {table_name} ({', '.join(db_columns)}) VALUES ({placeholders})"  # nosec B608

    batch_data = []
    batch_size = 100  # 设置批量插入的大小
    for record_dict in data_iterator:  # 遍历解析器产出的每条记录
        # 按 db_columns 的顺序从 record_dict 中获取值
        ordered_values = [record_dict.get(col_name) for col_name in db_columns]
        batch_data.append(tuple(ordered_values))  # 添加到批处理列表

        if len(batch_data) >= batch_size:  # 达到批处理大小时执行插入
            try:
                cursor.executemany(sql, batch_data)
                conn.commit()
                inserted_count += cursor.rowcount  # executemany 返回受影响的行数
                if cursor.rowcount < len(
                    batch_data
                ):  # 如果受影响行数小于批大小，说明有记录被忽略
                    skipped_count += len(batch_data) - cursor.rowcount
            except sqlite3.Error as e:
                log_error(f"批量插入数据到表 {table_name} 时出错: {e}")
                conn.rollback()
                skipped_count += len(batch_data)  # 出错则认为整批都跳过了
            finally:
                batch_data = []  # 清空批处理列表

    # 处理最后一批不足 batch_size 的数据
    if batch_data:
        try:
            cursor.executemany(sql, batch_data)
            conn.commit()
            inserted_count += cursor.rowcount
            if cursor.rowcount < len(batch_data):
                skipped_count += len(batch_data) - cursor.rowcount
        except sqlite3.Error as e:
            log_error(f"插入最后一批数据到表 {table_name} 时出错: {e}")
            conn.rollback()
            skipped_count += len(batch_data)

    log_info(
        f"表 {table_name}: 成功插入 {inserted_count} 条记录，跳过 (重复或错误) {skipped_count} 条记录。"
    )


# --- 主逻辑 ---
async def main():
    """
    数据导入脚本的主函数。
    负责加载配置、连接数据库、创建表、遍历配置文件中定义的插件、
    查找对应的数据文件、进行哈希检查、调用相应的解析函数，并将数据导入数据库。
    """
    log_info("--- 开始数据导入脚本 (带哈希检查) ---")
    db_path_for_import: Optional[Path] = None
    plugin_cfg: Optional[Any] = None  # 使用 Any 是因为 Config 类型可能在此处未完全解析

    # 1. 加载配置和数据库路径
    try:
        plugin_cfg = get_plugin_config()  # 获取插件配置
        db_path_for_import = get_database_full_path()  # 获取数据库完整路径
    except Exception as e:
        log_error(f"无法加载配置或获取数据库路径: {e}。导入中止。")
        return

    # 2. 检查数据基础路径是否配置
    if (
        not plugin_cfg.base_data_path
        or plugin_cfg.base_data_path == "your/base/data/path/"
    ):
        log_error("请在 config.toml 中正确配置 base_data_path。导入中止。")
        return
    base_data_dir = Path(plugin_cfg.base_data_path)  # 获取词库文件基础目录
    log_info(f"使用基础数据路径: {base_data_dir.resolve()}")
    if not base_data_dir.is_dir():
        log_error(f"配置的基础数据路径 ('{base_data_dir.resolve()}') 无效。导入中止。")
        return

    # 3. 连接数据库并创建表结构
    conn = None
    try:
        conn = get_db_connection(db_path=db_path_for_import)  # 连接数据库
        create_tables_if_not_exists(
            conn
        )  # 确保所有表（包括imported_files_log）都已创建
    except Exception as e:
        log_error(f"数据库初始化失败: {e}。导入中止。")
        if conn:
            conn.close()
            globals()["_connection"] = None  # 手动关闭并重置全局连接
        return

    # 4. 定义解析器映射：插件名称 -> {解析函数, 目标表名}
    parser_map: Dict[str, Dict[str, Any]] = {
        # "插件友好名称": {"parser": 解析函数名, "table": "数据库表名"}
        "脑洞": {"parser": parse_brainhole_excel, "table": "brainhole_terms"},
        "拼释": {"parser": parse_pinshi_excel, "table": "pinshi_terms"},
        "蝠汁牌": {"parser": parse_fuzhipai_docx, "table": "fuzhipai_cards"},
        "随蓝": {"parser": parse_suilan_excel, "table": "suilan_terms"},
        "五行": {"parser": parse_wuxing_excel, "table": "wuxing_terms"},
        "元晓": {"parser": parse_yuanxiao_excel, "table": "yuanxiao_terms"},
        "祯休": {"parser": parse_zhenxiu_excel, "table": "zhenxiu_terms"},
    }

    # 5. 遍历配置文件中的每个插件设置
    for plugin_setting in plugin_cfg.plugins:
        plugin_name = plugin_setting.name  # 插件的友好名称
        log_info(f"\n--- 处理插件类型: {plugin_name} ---")

        if plugin_name not in parser_map:  # 检查是否有对应的解析器配置
            log_warning(f"插件 '{plugin_name}' 没有配置对应的解析器，跳过。")
            continue

        parser_config = parser_map[plugin_name]
        parser_func: Callable[[Path, str], Iterator[Dict[str, Any]]] = parser_config[
            "parser"
        ]
        target_table: str = parser_config["table"]

        # 获取该插件的数据文件夹路径
        data_folder_str = plugin_setting.folder_name  # 配置文件中定义的文件夹名
        # 如果是绝对路径则直接使用，否则相对于 base_data_dir 构建
        data_folder = (
            Path(data_folder_str)
            if Path(data_folder_str).is_absolute()
            else base_data_dir / data_folder_str
        )

        if not data_folder.is_dir():
            log_warning(
                f"插件 '{plugin_name}' 数据文件夹 '{data_folder.resolve()}' 不存在，跳过。"
            )
            continue
        log_info(f"  正在扫描文件夹: {data_folder.resolve()}")

        file_found_for_plugin = False  # 标记是否为此插件找到了任何文件
        # 遍历该插件支持的文件扩展名
        for file_ext in plugin_setting.file_extensions:
            # 查找该文件夹下所有匹配扩展名的文件
            for file_path in data_folder.glob(f"*{file_ext}"):
                file_found_for_plugin = True
                if not file_path.is_file():
                    log_warning(f"    路径 {file_path} 不是一个文件，跳过。")
                    continue

                log_info(f"    找到文件: {file_path.name}")

                # --- 哈希检查逻辑 ---
                # 使用 "插件名_文件名" 作为文件在日志表中的唯一标识符
                file_identifier = f"{plugin_name}_{file_path.name}"

                current_file_hash = calculate_file_sha256(
                    file_path
                )  # 计算当前文件的哈希值
                if current_file_hash is None:
                    log_warning(
                        f"    无法计算文件 {file_path.name} 的哈希值，将尝试处理，但可能导致重复导入。"
                    )

                last_hash = get_last_imported_file_hash(
                    conn, file_identifier
                )  # 从数据库获取上次导入的哈希值

                # 如果当前哈希存在且与上次哈希相同，则跳过此文件
                if current_file_hash and last_hash == current_file_hash:
                    log_info(
                        f"    文件 {file_path.name} (Hash: {current_file_hash[:8]}...) 未更改，跳过处理。"
                    )
                    # 更新日志表状态为 "skipped_unchanged"
                    upsert_imported_file_log(
                        conn,
                        file_identifier,
                        current_file_hash,
                        "skipped_unchanged",
                        plugin_name,
                    )
                    continue  # 跳到下一个文件

                log_info(
                    f"    文件 {file_path.name} 是新文件或已更改 (CurrentHash: {current_file_hash[:8] if current_file_hash else 'N/A'}, LastHash: {last_hash[:8] if last_hash else 'N/A'})。准备处理..."
                )

                # 调用对应的解析函数 (解析函数内部包含用户确认逻辑)
                data_iterator = parser_func(file_path, file_path.name)

                if data_iterator:
                    # 将迭代器内容收集到列表中，以判断是否真的有数据被解析出来
                    # (因为用户可能在确认步骤取消了导入，导致迭代器为空)
                    data_to_insert = list(data_iterator)
                    if data_to_insert:  # 如果确实有数据
                        log_info(
                            f"    确认通过或无需确认，开始将 '{file_path.name}' 的数据插入表 '{target_table}'..."
                        )
                        # 将列表重新转为迭代器进行插入
                        insert_data_to_db(conn, target_table, iter(data_to_insert))
                        if current_file_hash:  # 仅当哈希计算成功时记录导入成功
                            upsert_imported_file_log(
                                conn,
                                file_identifier,
                                current_file_hash,
                                "imported",
                                plugin_name,
                            )
                    else:  # 解析后无数据或用户取消
                        log_info(
                            f"    文件 '{file_path.name}' 解析后未产生数据或用户取消导入。"
                        )
                        if (
                            current_file_hash
                        ):  # 即使没有数据，也记录为已处理（如果哈希成功）
                            upsert_imported_file_log(
                                conn,
                                file_identifier,
                                current_file_hash,
                                "processed_no_data_or_cancelled",
                                plugin_name,
                            )
                else:  # 解析函数返回 None 或空迭代器 (可能因内部错误)
                    log_warning(
                        f"    解析文件 '{file_path.name}' 未返回有效数据迭代器。"
                    )
                    if current_file_hash:  # 记录解析失败
                        upsert_imported_file_log(
                            conn,
                            file_identifier,
                            current_file_hash,
                            "parse_failed",
                            plugin_name,
                        )

        if not file_found_for_plugin:  # 如果该插件的文件夹下没有找到任何匹配的文件
            log_warning(
                f"  在文件夹 '{data_folder.resolve()}' 中未找到扩展名为 {plugin_setting.file_extensions} 的文件。"
            )

    log_info("\n--- 数据导入完成 ---")
    if conn:  # 关闭数据库连接
        conn.close()
        globals()["_connection"] = None  # 重置全局连接变量
        log_info("数据库连接已关闭。")


if __name__ == "__main__":
    asyncio.run(main())
