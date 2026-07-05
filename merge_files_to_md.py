# -*- coding: utf-8 -*-
"""
文件内容合并为 Markdown 工具
版本：v2.2.0
功能：读取同目录同名 INI 配置，按顺序将多个文件内容合并为单个 Markdown 文件
      支持目录通配符批量引入文件，支持忽略规则过滤
      可选按原目录结构打包源文件为同名压缩包作为备份
      可选在标题后显示文件编码信息
      新增 MD 文件自动分片功能，单文件块完整不截断，支持单独输出完整总文档
"""

import os
import sys
import fnmatch
import zipfile
from datetime import datetime

# ============== 配置区 ==============
# 脚本版本号
VERSION = 'v2.2.0'

# 后缀匹配语言映射表
LANG_MAP = {
    '.lua': 'lua',
    '.py': 'python',
    '.ps1': 'powershell',
    '.psm1': 'powershell',
    '.bat': 'batch',
    '.cmd': 'batch',
    '.md': 'markdown',
    '.txt': 'text',
    '.json': 'json',
    '.xml': 'xml',
    '.html': 'html',
    '.css': 'css',
    '.js': 'javascript',
    '.ts': 'typescript',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.toml': 'toml',
    '.ini': 'ini',
    '.cfg': 'ini',
    '.sh': 'bash',
    '.log': 'text',
}

# 文件名精确匹配语言映射
DEFAULT_FILE_LANG_MAP = {
    '.env': 'ini',
    '.env.example': 'ini',
    'Dockerfile': 'dockerfile',
    'Makefile': 'makefile',
    '.gitignore': 'text',
}

# 默认语言标识
DEFAULT_LANG = 'text'

# 空文件占位文本
EMPTY_FILE_PLACEHOLDER = '(内容为空)'

# 文件读取编码尝试顺序
READ_ENCODINGS = ['utf-8-sig', 'gbk', 'latin-1']

# 编码友好显示名称映射
ENCODING_DISPLAY_MAP = {
    'utf-8-sig': 'UTF-8 with BOM',
    'utf-8': 'UTF-8',
    'gbk': 'GBK',
    'latin-1': 'Latin-1 (兼容模式)',
}

# 分片内置常量（无需用户配置）
SPLIT_LINE_MAX_FILE_COUNT = 6  # 单行最多6个文件，超出换行

# 控制台颜色 ANSI 转义码
COLOR_INFO = ''
COLOR_SUCCESS = '\033[92m'
COLOR_WARNING = '\033[93m'
COLOR_ERROR = '\033[91m'
COLOR_RESET = '\033[0m'
COLOR_BOLD = '\033[1m'
# ====================================


# -------------------- 输出辅助函数 --------------------
def print_info(msg: str):
    print(f"{COLOR_INFO}[信息] {msg}{COLOR_RESET}")


def print_success(msg: str):
    print(f"{COLOR_SUCCESS}[成功] {msg}{COLOR_RESET}")


def print_warning(msg: str):
    print(f"{COLOR_WARNING}[提示] {msg}{COLOR_RESET}")


def print_error(msg: str):
    print(f"{COLOR_ERROR}[错误] {msg}{COLOR_RESET}")


def print_separator():
    print(f"{COLOR_BOLD}{'=' * 50}{COLOR_RESET}")


# -------------------- 通用工具函数 --------------------
def get_script_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def str_to_bool(value: str, default: bool = True) -> bool:
    val = value.strip().lower()
    if val in ('true', '1', 'yes', 'on', '启用', '开启'):
        return True
    if val in ('false', '0', 'no', 'off', '禁用', '关闭'):
        return False
    return default


def normalize_path(path: str) -> str:
    return path.replace('\\', '/')


def read_file_auto_encoding(file_path: str) -> tuple[str, str, bool]:
    last_err = None
    for enc in READ_ENCODINGS:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                content = f.read()
            warn = (enc == 'latin-1')
            return content, enc, warn
        except UnicodeDecodeError as e:
            last_err = e
            continue
        except Exception as e:
            raise e
    raise last_err


def get_encoding_display_name(enc: str) -> str:
    return ENCODING_DISPLAY_MAP.get(enc.lower(), enc)


def wrap_file_list_lines(file_list: list[str]) -> list[str]:
    """文件列表自动分行，单行最多SPLIT_LINE_MAX_FILE_COUNT个"""
    lines = []
    buf = []
    for fn in file_list:
        buf.append(fn)
        if len(buf) >= SPLIT_LINE_MAX_FILE_COUNT:
            lines.append(", ".join(buf))
            buf = []
    if buf:
        lines.append(", ".join(buf))
    return lines


def build_split_note(part_idx: int, total_parts: int, file_names: list[str], is_over_size: bool) -> str:
    """构建分片首行提示文本"""
    line_list = wrap_file_list_lines(file_names)
    note_parts = [f"> 分片 {part_idx} / {total_parts} | 包含文件：{line_list[0]}"]
    for line in line_list[1:]:
        note_parts.append(f">  {line}")
    if is_over_size:
        note_parts.append(f"> ⚠️ 警告：此文件单块内容超过设定分片上限，独立存放")
    return "\n".join(note_parts)


# -------------------- INI 解析 --------------------
def parse_ini_file(ini_path: str) -> dict:
    with open(ini_path, 'r', encoding='utf-8-sig') as f:
        lines = f.read().splitlines()

    sections = {}
    cur_sec = None
    cur_content = []
    for line in lines:
        if line.startswith('[') and line.endswith(']'):
            if cur_sec is not None:
                sections[cur_sec] = cur_content
            cur_sec = line[1:-1].strip()
            cur_content = []
            continue
        if cur_sec is None:
            continue
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith(';'):
            continue
        cur_content.append(line)
    if cur_sec is not None:
        sections[cur_sec] = cur_content

    # OutputFolder
    out_folder = ""
    if "OutputFolder" in sections:
        for line in sections["OutputFolder"]:
            s = line.strip()
            if s:
                out_folder = s
                break

    # OutputFileName
    out_prefix = ""
    if "OutputFileName" in sections:
        for line in sections["OutputFileName"]:
            s = line.strip()
            if s:
                out_prefix = s
                break

    # Title
    title_text = ""
    if "Title" in sections:
        for line in sections["Title"]:
            s = line.strip()
            if s:
                title_text = s
                break

    # Options
    enable_zip_backup = True
    show_file_encoding = False
    split_max_kb = 0
    export_whole_single = False
    if "Options" in sections:
        for line in sections["Options"]:
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k == "enablebackupzip":
                enable_zip_backup = str_to_bool(v, True)
            elif k == "showfileencoding":
                show_file_encoding = str_to_bool(v, False)
            elif k == "splitmdmaxsize":
                try:
                    split_max_kb = int(v)
                except ValueError:
                    split_max_kb = 0
            elif k == "exportwholesinglefile":
                export_whole_single = str_to_bool(v, False)

    # LangMap
    lang_map = {}
    if "LangMap" in sections:
        for line in sections["LangMap"]:
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            lang_map[k.strip()] = v.strip()

    # IgnoreList
    ignore_rules = []
    if "IgnoreList" in sections:
        ignore_rules = [x.strip() for x in sections["IgnoreList"] if x.strip()]

    # FileList
    raw_file_entries = []
    if "FileList" in sections:
        raw_file_entries = [x.strip() for x in sections["FileList"] if x.strip()]

    return {
        "output_folder": out_folder,
        "output_prefix": out_prefix,
        "title_text": title_text,
        "lang_map": lang_map,
        "ignore_list": ignore_rules,
        "raw_file_list": raw_file_entries,
        "enable_backup_zip": enable_zip_backup,
        "show_file_encoding": show_file_encoding,
        "split_max_kb": split_max_kb,
        "export_whole_single": export_whole_single,
    }


# -------------------- 文件清单展开、忽略过滤 --------------------
def is_file_ignored(rel_path: str, ignore_patterns: list[str]) -> bool:
    norm_p = normalize_path(rel_path)
    for pat in ignore_patterns:
        norm_pat = normalize_path(pat)
        if fnmatch.fnmatch(norm_p, norm_pat):
            return True
    return False


def expand_raw_file_list(base_dir: str, raw_list: list[str], ignore_rules: list[str]) -> tuple[list[str], int]:
    final_list = []
    seen_set = set()
    warn_cnt = 0
    for entry in raw_list:
        if entry.endswith("\\*") or entry.endswith("/*"):
            dir_rel = entry[:-2]
            dir_abs = os.path.join(base_dir, dir_rel)
            if not os.path.isdir(dir_abs):
                print_warning(f"通配符目录 {dir_rel} 不存在，已跳过")
                warn_cnt += 1
                continue
            try:
                entries = os.listdir(dir_abs)
                file_names = []
                for item in entries:
                    item_abs = os.path.join(dir_abs, item)
                    if os.path.isfile(item_abs):
                        file_names.append(item)
                file_names.sort(key=lambda x: x.lower())
                orig_count = len(file_names)
                add_count = 0
                for fn in file_names:
                    rel_p = os.path.join(dir_rel, fn)
                    if is_file_ignored(rel_p, ignore_rules):
                        continue
                    norm_p = normalize_path(rel_p)
                    if norm_p not in seen_set:
                        seen_set.add(norm_p)
                        final_list.append(rel_p)
                        add_count += 1
                if orig_count == 0:
                    print_warning(f"通配符目录 {dir_rel} 下无直接文件，已跳过")
                    warn_cnt += 1
                elif add_count == 0:
                    print_warning(f"通配符目录 {dir_rel} 下所有文件均被忽略规则过滤，已跳过")
                    warn_cnt += 1
            except Exception as e:
                print_warning(f"读取通配符目录 {dir_rel} 失败（{e}），已跳过")
                warn_cnt += 1
            continue
        # 普通文件条目
        norm_p = normalize_path(entry)
        if is_file_ignored(entry, ignore_rules):
            continue
        if norm_p not in seen_set:
            seen_set.add(norm_p)
            final_list.append(entry)
    return final_list, warn_cnt


# -------------------- 代码块生成 --------------------
def build_code_block(content: str, lang: str) -> str:
    max_tick = 0
    cur = 0
    for c in content:
        if c == "`":
            cur += 1
            max_tick = max(max_tick, cur)
        else:
            cur = 0
    fence = "`" * max(3, max_tick + 1)
    return f"{fence}{lang}\n{content}\n{fence}"


def get_file_lang(rel_path: str, custom_lang: dict) -> str:
    fn = os.path.basename(rel_path)
    if fn in custom_lang:
        return custom_lang[fn]
    if fn in DEFAULT_FILE_LANG_MAP:
        return DEFAULT_FILE_LANG_MAP[fn]
    ext = os.path.splitext(fn)[1].lower()
    return LANG_MAP.get(ext, DEFAULT_LANG)


# -------------------- 备份 ZIP 生成 --------------------
def create_backup_zip(zip_path: str, base_dir: str, file_list: list[str]) -> int:
    cnt = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_p in file_list:
            abs_p = os.path.join(base_dir, rel_p)
            if not os.path.isfile(abs_p):
                continue
            try:
                arc = os.path.relpath(abs_p, base_dir)
                arc = normalize_path(arc)
                zf.write(abs_p, arc)
                cnt += 1
            except Exception:
                continue
    if cnt == 0 and os.path.exists(zip_path):
        os.remove(zip_path)
    return cnt


# -------------------- 分片分组工具 --------------------
class FileBlockItem:
    def __init__(self, full_md: str, byte_len: int, rel_path: str):
        self.full_md = full_md
        self.byte_len = byte_len
        self.rel_path = rel_path


def split_group_blocks(
    block_list: list[FileBlockItem],
    max_bytes: int,
    head_fixed_bytes: int,
    split_note_base_bytes: int,
    split_sep_bytes: int
) -> list[tuple[list[FileBlockItem], list[str], bool]]:
    """
    返回 [(块列表, 文件路径列表, 是否超大单块)]
    """
    groups = []
    if not block_list:
        return groups
    idx = 0
    total = len(block_list)
    while idx < total:
        cur_block = block_list[idx]
        # 单个块超过上限，单独一组
        single_over = cur_block.byte_len + split_note_base_bytes + split_sep_bytes > max_bytes
        if single_over:
            groups.append(([cur_block], [cur_block.rel_path], True))
            idx += 1
            continue
        # 新建分组，基础占用：分片提示 + 分割线
        group_blocks = [cur_block]
        group_files = [cur_block.rel_path]
        used = split_note_base_bytes + split_sep_bytes + cur_block.byte_len
        idx += 1
        # 第一组预留全局头部空间
        if len(groups) == 0:
            used += head_fixed_bytes
        # 持续追加剩余块
        while idx < total:
            next_b = block_list[idx]
            add_size = next_b.byte_len
            if used + add_size <= max_bytes:
                group_blocks.append(next_b)
                group_files.append(next_b.rel_path)
                used += add_size
                idx += 1
            else:
                break
        groups.append((group_blocks, group_files, False))
    return groups


# -------------------- 主逻辑入口 --------------------
def main():
    warn_total = 0
    err_total = 0
    success_file_cnt = 0

    print_separator()
    print(f"{COLOR_BOLD}  文件内容合并工具 {VERSION}{COLOR_RESET}")
    print(f"  运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_separator()
    print()

    base_dir = get_script_base_dir()
    script_stem = os.path.splitext(os.path.basename(__file__))[0]
    ini_path = os.path.join(base_dir, f"{script_stem}.ini")
    header_file_path = os.path.join(base_dir, f"{script_stem}.header")

    # 1. 加载配置
    print_info(f"加载配置文件：{ini_path}")
    if not os.path.exists(ini_path):
        print_error(f"未找到配置文件 {ini_path}")
        err_total += 1
        print()
        print_separator()
        print(f"{COLOR_ERROR}  运行失败{COLOR_RESET}")
        print(f"  错误：{err_total} 条")
        print_separator()
        input("\n按回车键退出...")
        return
    try:
        cfg = parse_ini_file(ini_path)
    except Exception as e:
        print_error(f"解析配置文件失败：{e}")
        err_total += 1
        print()
        print_separator()
        print(f"{COLOR_ERROR}  运行失败{COLOR_RESET}")
        print(f"  错误：{err_total} 条")
        print_separator()
        input("\n按回车键退出...")
        return
    print_success("配置文件解析完成")
    print()

    out_folder = cfg["output_folder"]
    out_prefix = cfg["output_prefix"]
    title_text = cfg["title_text"]
    custom_lang_map = cfg["lang_map"]
    ignore_list = cfg["ignore_list"]
    raw_file_entries = cfg["raw_file_list"]
    enable_zip = cfg["enable_backup_zip"]
    show_enc_title = cfg["show_file_encoding"]
    split_max_kb = cfg["split_max_kb"]
    export_whole = cfg["export_whole_single"]

    if not out_prefix:
        print_error("配置文件中 OutputFileName 不能为空")
        err_total += 1
        print()
        print_separator()
        print(f"{COLOR_ERROR}  运行失败{COLOR_RESET}")
        print(f"  错误：{err_total} 条")
        print_separator()
        input("\n按回车键退出...")
        return

    # 2. 展开文件清单
    print_info(f"开始处理文件清单（共 {len(raw_file_entries)} 条原始条目）")
    if ignore_list:
        print_info(f"已加载 {len(ignore_list)} 条忽略规则")
    valid_file_list, expand_warn = expand_raw_file_list(base_dir, raw_file_entries, ignore_list)
    warn_total += expand_warn
    if not valid_file_list:
        print_warning("没有符合条件的待处理文件")
        warn_total += 1
        print()
        print_separator()
        print(f"{COLOR_WARNING}  运行结束{COLOR_RESET}")
        print(f"  警告：{warn_total} 条")
        print(f"  错误：{err_total} 条")
        print_separator()
        input("\n按回车键退出...")
        return
    print_success(f"文件清单处理完成，有效文件：{len(valid_file_list)} 个")
    print()

    # 3. 预读取.header全局头部内容
    header_global_text = ""
    if os.path.isfile(header_file_path):
        try:
            h_content, h_enc, h_warn = read_file_auto_encoding(header_file_path)
            if h_warn:
                print_warning(f"头部说明文件编码异常，兼容模式读取（{h_enc}）")
                warn_total += 1
            header_global_text = h_content.rstrip()
        except Exception as e:
            print_warning(f"读取头部说明文件失败（{e}），已跳过")
            warn_total += 1

    # 组装全局固定头部（仅第一个分片使用）
    global_head_parts = []
    if title_text.strip():
        global_head_parts.append(f"# {title_text}")
    if header_global_text.strip():
        global_head_parts.append("")
        global_head_parts.append(header_global_text)
        global_head_parts.append("\n---")
    global_head_full = "\n".join(global_head_parts)
    global_head_bytes = len(global_head_full.encode("utf-8"))

    # 4. 预渲染所有文件MD块，计算字节
    print_info("预渲染所有文件Markdown内容...")
    block_item_list: list[FileBlockItem] = []
    whole_md_all_parts = []
    # 完整总文档先拼接头部
    if global_head_full.strip():
        whole_md_all_parts.append(global_head_full)
        whole_md_all_parts.append("")

    for rel_p in valid_file_list:
        abs_p = os.path.join(base_dir, rel_p)
        if not os.path.isfile(abs_p):
            print_warning(f"文件 {rel_p} 不存在，已跳过")
            warn_total += 1
            continue
        try:
            f_content, f_enc, f_warn = read_file_auto_encoding(abs_p)
            if f_warn:
                print_warning(f"文件 {rel_p} 编码异常，兼容模式读取（{f_enc}）")
                warn_total += 1
        except Exception as e:
            print_warning(f"读取文件 {rel_p} 失败（{e}），已跳过")
            warn_total += 1
            continue
        # 空文件替换占位
        if not f_content.strip():
            f_content = EMPTY_FILE_PLACEHOLDER
        lang_tag = get_file_lang(rel_p, custom_lang_map)
        code_block = build_code_block(f_content, lang_tag)
        # 构建二级标题
        if show_enc_title:
            enc_name = get_encoding_display_name(f_enc)
            sec_title = f"\n## {rel_p} ({enc_name})"
        else:
            sec_title = f"\n## {rel_p}"
        full_file_md = f"{sec_title}\n{code_block}"
        byte_len = len(full_file_md.encode("utf-8"))
        block_item_list.append(FileBlockItem(full_file_md, byte_len, rel_p))
        whole_md_all_parts.append(full_file_md)
        success_file_cnt += 1
    print_success(f"文件内容渲染完成，有效渲染：{success_file_cnt} 个")
    print()

    # 基准时间戳
    time_stamp = datetime.now().strftime("%Y%m%d%H%M")
    base_filename_stem = f"{out_prefix}-{time_stamp}"
    out_dir_abs = os.path.join(base_dir, out_folder)
    os.makedirs(out_dir_abs, exist_ok=True)

    # 5. 分支：不分片 / 分片
    split_enabled = split_max_kb > 0
    if not split_enabled:
        # 旧逻辑：单一完整MD
        print_info("未开启分片，生成单一合并文档")
        full_md_text = "\n".join(whole_md_all_parts) + "\n"
        single_md_path = os.path.join(out_dir_abs, f"{base_filename_stem}.md")
        try:
            with open(single_md_path, "w", encoding="utf-8") as f:
                f.write(full_md_text)
            print_success("Markdown 文件生成完成")
            print(f"  路径：{single_md_path}")
            print(f"  包含：{success_file_cnt} 个文件")
        except Exception as e:
            print_error(f"写入 Markdown 文件失败：{e}")
            err_total += 1
    else:
        # 开启分片逻辑
        print_info(f"开启分片功能，单分片最大 {split_max_kb} KB")
        max_total_bytes = split_max_kb * 1024
        split_sep_text = "---\n"
        split_sep_bytes = len(split_sep_text.encode("utf-8"))
        # 先计算空提示基础字节
        empty_note = build_split_note(1, 9999, [], False)
        split_note_base_bytes = len(empty_note.encode("utf-8"))

        # 分组
        group_data = split_group_blocks(
            block_item_list,
            max_total_bytes,
            global_head_bytes,
            split_note_base_bytes,
            split_sep_bytes
        )
        total_part = len(group_data)
        print_info(f"自动分组完成，总分片数量：{total_part}")
        # 循环生成每个分片
        for part_num, (group_blocks, group_files, is_over_single) in enumerate(group_data, start=1):
            part_md_parts = []
            # 分片提示首行
            note_text = build_split_note(part_num, total_part, group_files, is_over_single)
            part_md_parts.append(note_text)
            part_md_parts.append(split_sep_text.strip())
            # 仅第一个分片追加全局头部
            if part_num == 1 and global_head_full.strip():
                part_md_parts.append(global_head_full)
                part_md_parts.append("")
            # 写入本组所有文件块
            for b in group_blocks:
                part_md_parts.append(b.full_md)
            # 拼接写入文件
            part_full_text = "\n".join(part_md_parts) + "\n"
            part_file_name = f"{base_filename_stem}_part{part_num}.md"
            part_path = os.path.join(out_dir_abs, part_file_name)
            try:
                with open(part_path, "w", encoding="utf-8") as f:
                    f.write(part_full_text)
                print_success(f"分片 {part_num}/{total_part} 已生成：{part_file_name}")
            except Exception as e:
                print_error(f"写入分片 {part_num} 失败：{e}")
                err_total += 1
        # 判断是否额外输出完整单文件
        if export_whole:
            print_info("配置开启同时输出完整不分片文档")
            full_md_text = "\n".join(whole_md_all_parts) + "\n"
            whole_file_path = os.path.join(out_dir_abs, f"{base_filename_stem}_full.md")
            try:
                with open(whole_file_path, "w", encoding="utf-8") as f:
                    f.write(full_md_text)
                print_success(f"完整总文档已生成：{os.path.basename(whole_file_path)}")
            except Exception as e:
                print_error(f"写入完整总文档失败：{e}")
                err_total += 1
    print()

    # 6. 备份 ZIP（完全不受分片影响）
    if enable_zip:
        print_info("正在生成同源备份压缩包...")
        zip_file_name = f"{base_filename_stem}.zip"
        zip_full_path = os.path.join(out_dir_abs, zip_file_name)
        zip_cnt = create_backup_zip(zip_full_path, base_dir, valid_file_list)
        if zip_cnt > 0:
            print_success("备份压缩包生成完成")
            print(f"  路径：{zip_full_path}")
            print(f"  包含：{zip_cnt} 个原始文件")
        else:
            print_warning("无有效原始文件，未生成压缩包")
            warn_total += 1
    print()

    # 底部汇总
    print_separator()
    if err_total > 0:
        status = f"{COLOR_ERROR}  运行完成（存在错误）{COLOR_RESET}"
    elif warn_total > 0:
        status = f"{COLOR_WARNING}  运行完成（存在警告）{COLOR_RESET}"
    else:
        status = f"{COLOR_SUCCESS}  运行完成{COLOR_RESET}"
    print(status)
    print(f"  成功处理文件：{success_file_cnt} 个")
    print(f"  警告总数：{warn_total} 条")
    print(f"  错误总数：{err_total} 条")
    if split_enabled:
        print(f"  MD分片总数：{len(group_data)}")
    print_separator()
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
