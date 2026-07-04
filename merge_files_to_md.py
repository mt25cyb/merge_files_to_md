# -*- coding: utf-8 -*-
"""
文件内容合并为 Markdown 工具
版本：v2.0.0
功能：读取同目录同名 INI 配置，按顺序将多个文件内容合并为单个 Markdown 文件
      支持目录通配符批量引入文件，支持忽略规则过滤
      可选按原目录结构打包源文件为同名压缩包作为备份
"""

import os
import sys
import fnmatch
import zipfile
from datetime import datetime

# ============== 配置区 ==============
# 脚本版本号
VERSION = 'v2.0.0'

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

# 文件名精确匹配语言映射（优先级高于后缀匹配，内置常见特殊文件名）
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

# 文件读取编码尝试顺序（从前到后依次尝试）
READ_ENCODINGS = ['utf-8-sig', 'gbk', 'latin-1']

# 控制台颜色定义（ANSI 转义码，Windows 10+/PowerShell 原生支持）
COLOR_INFO = ''
COLOR_SUCCESS = '\033[92m'
COLOR_WARNING = '\033[93m'
COLOR_ERROR = '\033[91m'
COLOR_RESET = '\033[0m'
COLOR_BOLD = '\033[1m'
# ====================================


# -------------------- 输出辅助函数 --------------------
def print_info(msg: str):
    """普通信息输出"""
    print(f"{COLOR_INFO}[信息] {msg}{COLOR_RESET}")


def print_success(msg: str):
    """成功信息输出（绿色）"""
    print(f"{COLOR_SUCCESS}[成功] {msg}{COLOR_RESET}")


def print_warning(msg: str):
    """警告/提示信息输出（黄色）"""
    print(f"{COLOR_WARNING}[提示] {msg}{COLOR_RESET}")


def print_error(msg: str):
    """错误信息输出（红色）"""
    print(f"{COLOR_ERROR}[错误] {msg}{COLOR_RESET}")


def print_separator():
    """打印分隔线"""
    print(f"{COLOR_BOLD}{'=' * 50}{COLOR_RESET}")


# -------------------- 核心工具函数 --------------------
def get_script_base_dir() -> str:
    """获取脚本所在的绝对目录路径"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def str_to_bool(value: str, default: bool = True) -> bool:
    """字符串转布尔值，兼容多种写法，不区分大小写"""
    value = value.strip().lower()
    if value in ('true', '1', 'yes', 'on', '启用', '开启'):
        return True
    if value in ('false', '0', 'no', 'off', '禁用', '关闭'):
        return False
    return default


def normalize_path(path: str) -> str:
    """统一路径分隔符为正斜杠，用于通配符匹配比较"""
    return path.replace('\\', '/')


def read_file_auto_encoding(file_path: str) -> tuple[str, str, bool]:
    """
    自动尝试多种编码读取文件
    返回 (内容, 使用的编码, 是否存在编码警告)
    """
    last_error = None
    for encoding in READ_ENCODINGS:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            # latin-1 属于兜底编码，标记为有警告
            has_warning = (encoding == 'latin-1')
            return content, encoding, has_warning
        except UnicodeDecodeError as e:
            last_error = e
            continue
        except Exception as e:
            raise e

    # 理论上 latin-1 不会报错，这里做兜底
    raise last_error


def parse_ini_file(ini_path: str) -> dict:
    """
    自定义解析 INI 文件，支持注释与自定义语言映射
    返回字典：output_folder, output_file_prefix, title_content, file_list,
              ignore_list, custom_lang_map, enable_backup_zip
    """
    # 使用 utf-8-sig 自动兼容带/不带 BOM 的 UTF-8 文件
    with open(ini_path, 'r', encoding='utf-8-sig') as f:
        lines = f.read().splitlines()

    sections = {}
    current_section = None
    current_content = []

    for line in lines:
        # 识别节标题
        if line.startswith('[') and line.endswith(']'):
            # 保存上一个节的内容
            if current_section is not None:
                sections[current_section] = current_content
            current_section = line[1:-1].strip()
            current_content = []
            continue

        # 未进入任何节时，跳过所有行（文件开头的注释、空行）
        if current_section is None:
            continue

        # 所有配置节统一过滤整行注释（# 或 ; 开头）
        stripped_line = line.strip()
        if stripped_line.startswith('#') or stripped_line.startswith(';'):
            continue

        current_content.append(line)

    # 保存最后一个节
    if current_section is not None:
        sections[current_section] = current_content

    # 提取 OutputFolder：取第一行非空内容
    output_folder = ''
    if 'OutputFolder' in sections:
        for line in sections['OutputFolder']:
            if line.strip():
                output_folder = line.strip()
                break

    # 提取 OutputFileName：取第一行非空内容
    output_file_prefix = ''
    if 'OutputFileName' in sections:
        for line in sections['OutputFileName']:
            if line.strip():
                output_file_prefix = line.strip()
                break

    # 提取 Title：取第一行非空内容作为一级标题文本
    title_content = ''
    if 'Title' in sections:
        for line in sections['Title']:
            stripped = line.strip()
            if stripped:
                title_content = stripped
                break

    # Options：全局开关配置
    enable_backup_zip = True  # 默认开启，兼容旧配置
    if 'Options' in sections:
        for line in sections['Options']:
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip().lower()
            if key == 'enablebackupzip':
                enable_backup_zip = str_to_bool(value.strip(), default=True)

    # LangMap：用户自定义文件名 → 语言映射
    custom_lang_map = {}
    if 'LangMap' in sections:
        for line in sections['LangMap']:
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, value = line.split('=', 1)
            custom_lang_map[key.strip()] = value.strip()

    # IgnoreList：忽略规则列表
    ignore_list = []
    if 'IgnoreList' in sections:
        ignore_list = [line.strip() for line in sections['IgnoreList'] if line.strip()]

    # FileList：过滤空行，保留顺序
    file_list = []
    if 'FileList' in sections:
        file_list = [line.strip() for line in sections['FileList'] if line.strip()]

    return {
        'output_folder': output_folder,
        'output_file_prefix': output_file_prefix,
        'title_content': title_content,
        'custom_lang_map': custom_lang_map,
        'ignore_list': ignore_list,
        'file_list': file_list,
        'enable_backup_zip': enable_backup_zip
    }


def is_file_ignored(file_rel_path: str, ignore_patterns: list) -> bool:
    """
    判断文件是否匹配忽略规则
    支持精确匹配和 glob 通配符匹配，路径层级严格对应
    """
    norm_path = normalize_path(file_rel_path)
    for pattern in ignore_patterns:
        norm_pattern = normalize_path(pattern)
        if fnmatch.fnmatch(norm_path, norm_pattern):
            return True
    return False


def expand_file_list(base_dir: str, raw_file_list: list, ignore_patterns: list):
    """
    展开文件清单：处理目录通配符（目录/*），应用忽略规则，自动去重
    返回 (最终文件列表, 警告计数)
    """
    result = []
    seen = set()
    warning_count = 0

    for item in raw_file_list:
        # 判断是否为目录通配符（以 \* 或 /* 结尾）
        if item.endswith('\\*') or item.endswith('/*'):
            # 提取目录路径
            dir_path = item[:-2]  # 去掉末尾的 \*
            dir_abs_path = os.path.join(base_dir, dir_path)

            if not os.path.isdir(dir_abs_path):
                print_warning(f"通配符目录 {dir_path} 不存在，已跳过")
                warning_count += 1
                continue

            try:
                # 获取目录下所有直接条目，筛选文件，跳过子目录
                entries = os.listdir(dir_abs_path)
                files = []
                for entry in entries:
                    entry_abs = os.path.join(dir_abs_path, entry)
                    if os.path.isfile(entry_abs):
                        files.append(entry)
                # 按文件名升序排列（不区分大小写）
                files.sort(key=lambda x: x.lower())

                original_count = len(files)
                added_count = 0

                for filename in files:
                    # 拼接完整相对路径
                    rel_path = os.path.join(dir_path, filename)
                    norm_path = normalize_path(rel_path)

                    # 先检查忽略规则
                    if is_file_ignored(rel_path, ignore_patterns):
                        continue

                    # 去重
                    if norm_path not in seen:
                        seen.add(norm_path)
                        result.append(rel_path)
                        added_count += 1

                # 分场景输出提示
                if original_count == 0:
                    print_warning(f"通配符目录 {dir_path} 下无直接文件，已跳过")
                    warning_count += 1
                elif added_count == 0:
                    print_warning(f"通配符目录 {dir_path} 下所有文件均被忽略规则过滤，已跳过")
                    warning_count += 1

            except Exception as e:
                print_warning(f"读取通配符目录 {dir_path} 失败（{e}），已跳过")
                warning_count += 1
            continue

        # 普通文件条目
        norm_path = normalize_path(item)

        # 先检查忽略规则
        if is_file_ignored(item, ignore_patterns):
            continue

        # 去重
        if norm_path not in seen:
            seen.add(norm_path)
            result.append(item)

    return result, warning_count


def get_lang_by_filename(file_path: str, custom_lang_map: dict = None) -> str:
    """
    获取代码块语言标识，优先级从高到低：
    1. INI 中自定义的文件名映射
    2. 内置的特殊文件名精确匹配
    3. 文件后缀匹配
    4. 默认 text
    """
    if custom_lang_map is None:
        custom_lang_map = {}

    filename = os.path.basename(file_path)

    # 1. 优先匹配用户自定义
    if filename in custom_lang_map:
        return custom_lang_map[filename]

    # 2. 匹配内置特殊文件名
    if filename in DEFAULT_FILE_LANG_MAP:
        return DEFAULT_FILE_LANG_MAP[filename]

    # 3. 按后缀匹配
    ext = os.path.splitext(filename)[1].lower()
    return LANG_MAP.get(ext, DEFAULT_LANG)


def build_code_block(content: str, lang: str) -> str:
    """
    生成安全的 Markdown 代码块
    自动检测内容中的反引号长度，外层使用更长的反引号避免格式冲突
    """
    max_backticks = 0
    current = 0
    for char in content:
        if char == '`':
            current += 1
            max_backticks = max(max_backticks, current)
        else:
            current = 0

    fence_length = max(3, max_backticks + 1)
    fence = '`' * fence_length

    return f"{fence}{lang}\n{content}\n{fence}"


def generate_output_path(base_dir: str, output_folder: str, prefix: str) -> str:
    """生成输出 Markdown 文件完整路径，同名自动追加秒数避免覆盖"""
    folder_path = os.path.join(base_dir, output_folder)
    os.makedirs(folder_path, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    filename = f"{prefix}-{timestamp}.md"
    full_path = os.path.join(folder_path, filename)

    if os.path.exists(full_path):
        timestamp_full = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{prefix}-{timestamp_full}.md"
        full_path = os.path.join(folder_path, filename)

    return full_path


def create_backup_zip(zip_path: str, base_dir: str, file_list: list) -> int:
    """
    根据文件清单创建备份压缩包，保留原始相对目录结构
    返回成功打包的文件数量
    """
    success_count = 0
    # 使用 ZIP_DEFLATED 压缩模式，减小体积
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_rel_path in file_list:
            file_abs_path = os.path.abspath(os.path.join(base_dir, file_rel_path))
            if not os.path.isfile(file_abs_path):
                continue

            # 计算压缩包内的路径：优先保留相对于基准目录的目录结构
            try:
                arcname = os.path.relpath(file_abs_path, base_dir)
            except ValueError:
                # Windows 跨盘符无法计算相对路径时，仅保留文件名
                arcname = os.path.basename(file_abs_path)

            # 统一使用正斜杠，跨平台兼容性更好
            arcname = arcname.replace('\\', '/')
            zipf.write(file_abs_path, arcname)
            success_count += 1

    # 没有有效文件时删除空压缩包
    if success_count == 0 and os.path.exists(zip_path):
        os.remove(zip_path)

    return success_count


def main():
    # 运行统计
    warning_count = 0
    error_count = 0
    process_success = 0

    # 顶部标题栏
    print_separator()
    print(f"{COLOR_BOLD}  文件内容合并工具 {VERSION}{COLOR_RESET}")
    print(f"  运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_separator()
    print()

    base_dir = get_script_base_dir()
    script_name = os.path.splitext(os.path.basename(__file__))[0]
    ini_path = os.path.join(base_dir, f"{script_name}.ini")
    header_file_path = os.path.join(base_dir, f"{script_name}.header")

    # 阶段1：加载配置
    print_info(f"加载配置文件：{ini_path}")
    if not os.path.exists(ini_path):
        print_error(f"未找到配置文件 {ini_path}")
        error_count += 1
        print()
        print_separator()
        print(f"{COLOR_ERROR}  运行失败{COLOR_RESET}")
        print(f"  错误：{error_count} 条")
        print_separator()
        input("\n按回车键退出...")
        return

    try:
        config = parse_ini_file(ini_path)
    except Exception as e:
        print_error(f"解析配置文件失败：{e}")
        error_count += 1
        print()
        print_separator()
        print(f"{COLOR_ERROR}  运行失败{COLOR_RESET}")
        print(f"  错误：{error_count} 条")
        print_separator()
        input("\n按回车键退出...")
        return

    print_success("配置文件解析完成")
    print()

    output_folder = config['output_folder']
    file_prefix = config['output_file_prefix']
    title_content = config['title_content']
    custom_lang_map = config['custom_lang_map']
    ignore_list = config['ignore_list']
    raw_file_list = config['file_list']
    enable_backup_zip = config['enable_backup_zip']

    if not file_prefix:
        print_error("配置文件中 OutputFileName 不能为空")
        error_count += 1
        print()
        print_separator()
        print(f"{COLOR_ERROR}  运行失败{COLOR_RESET}")
        print(f"  错误：{error_count} 条")
        print_separator()
        input("\n按回车键退出...")
        return

    # 阶段2：展开文件清单
    print_info(f"开始处理文件清单（共 {len(raw_file_list)} 条原始条目）")
    if ignore_list:
        print_info(f"已加载 {len(ignore_list)} 条忽略规则")

    final_file_list, expand_warnings = expand_file_list(base_dir, raw_file_list, ignore_list)
    warning_count += expand_warnings

    if not final_file_list:
        print_warning("没有符合条件的待处理文件")
        warning_count += 1
        print()
        print_separator()
        print(f"{COLOR_WARNING}  运行结束{COLOR_RESET}")
        print(f"  警告：{warning_count} 条")
        print(f"  错误：{error_count} 条")
        print_separator()
        input("\n按回车键退出...")
        return

    print_success(f"文件清单处理完成，有效文件：{len(final_file_list)} 个")
    print()

    # 阶段3：组装 Markdown 内容
    print_info("正在生成 Markdown 合并文件...")
    md_parts = []

    # 3.1 添加一级标题
    if title_content:
        md_parts.append(f"# {title_content}")

    # 3.2 读取并添加头部说明文件
    header_content = ''
    if os.path.isfile(header_file_path):
        try:
            header_content, used_encoding, has_encode_warning = read_file_auto_encoding(header_file_path)
            if has_encode_warning:
                print_warning(f"头部说明文件编码异常，已使用兼容模式读取（{used_encoding}）")
                warning_count += 1
        except Exception as e:
            print_warning(f"读取头部说明文件失败（{e}），已跳过")
            warning_count += 1

    # 头部内容非空则添加内容 + 分隔线
    if header_content.strip():
        if md_parts:
            md_parts.append('')  # 与标题空行分隔
        md_parts.append(header_content.rstrip())
        md_parts.append('\n---')

    # 3.3 按顺序添加文件内容
    for file_rel_path in final_file_list:
        file_abs_path = os.path.join(base_dir, file_rel_path)

        if not os.path.isfile(file_abs_path):
            print_warning(f"文件 {file_rel_path} 不存在，已跳过")
            warning_count += 1
            continue

        try:
            file_content, used_encoding, has_encode_warning = read_file_auto_encoding(file_abs_path)
            if has_encode_warning:
                print_warning(f"文件 {file_rel_path} 编码异常，已使用兼容模式读取（{used_encoding}）")
                warning_count += 1
        except Exception as e:
            print_warning(f"读取文件 {file_rel_path} 失败（{e}），已跳过")
            warning_count += 1
            continue

        # 空文件处理
        if not file_content.strip():
            file_content = EMPTY_FILE_PLACEHOLDER

        lang = get_lang_by_filename(file_rel_path, custom_lang_map)
        md_parts.append(f"\n## {file_rel_path}")
        md_parts.append(build_code_block(file_content, lang))
        process_success += 1

    final_content = '\n'.join(md_parts) + '\n'
    output_md_path = generate_output_path(base_dir, output_folder, file_prefix)

    try:
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        print_success("Markdown 文件生成完成")
        print(f"  路径：{output_md_path}")
        print(f"  包含：{process_success} 个文件")
    except Exception as e:
        print_error(f"写入 Markdown 文件失败：{e}")
        error_count += 1
        print()
        print_separator()
        print(f"{COLOR_ERROR}  运行失败{COLOR_RESET}")
        print(f"  错误：{error_count} 条")
        print_separator()
        input("\n按回车键退出...")
        return

    print()

    # 阶段4：生成备份压缩包
    if enable_backup_zip:
        print_info("正在生成备份压缩包...")
        output_zip_path = os.path.splitext(output_md_path)[0] + '.zip'
        try:
            file_count = create_backup_zip(output_zip_path, base_dir, final_file_list)
            if file_count > 0:
                print_success("备份压缩包生成完成")
                print(f"  路径：{output_zip_path}")
                print(f"  包含：{file_count} 个文件")
            else:
                print_warning("没有可打包的有效文件，未生成压缩包")
                warning_count += 1
        except Exception as e:
            print_warning(f"生成压缩包失败：{e}")
            warning_count += 1

        print()

    # 底部汇总栏
    print_separator()
    if error_count > 0:
        print(f"{COLOR_ERROR}  运行完成（存在错误）{COLOR_RESET}")
    elif warning_count > 0:
        print(f"{COLOR_WARNING}  运行完成（存在警告）{COLOR_RESET}")
    else:
        print(f"{COLOR_SUCCESS}  运行完成{COLOR_RESET}")
    print(f"  成功处理：{process_success} 个文件")
    print(f"  警告：{warning_count} 条")
    print(f"  错误：{error_count} 条")
    print_separator()

    input("\n按回车键退出...")


if __name__ == '__main__':
    main()
