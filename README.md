# Merge Files to Markdown

一款轻量、配置驱动的文件内容合并工具，可将指定目录下的多个源码/文本文件按顺序合并为单个 Markdown 文档，同时支持同源文件备份打包。纯 Python 原生实现，无第三方依赖，开箱即用。

## ✨ 功能特性

- **配置驱动**：通过 INI 文件管理所有规则，无需修改代码即可适配不同项目
- **目录通配符**：支持 `目录\*` 语法批量引入目录下的所有直接文件，自动按文件名排序
- **灵活忽略规则**：支持精确路径与 glob 通配符双重忽略模式，路径层级严格匹配
- **自动备份打包**：可选生成同名 ZIP 压缩包，完整保留原始目录结构
- **多编码兼容**：自动适配 UTF-8（含 BOM）、GBK 编码，Latin-1 兜底保证文件不丢失
- **智能代码块**：根据文件后缀自动匹配语言高亮，自动检测并转义反引号冲突
- **空文件处理**：空文件自动添加占位标识，保证文档结构完整
- **结构化输出**：彩色分阶段控制台输出，自带运行统计与异常提示
- **跨平台兼容**：支持 Windows / macOS / Linux，纯 Python 标准库实现

## 📦 环境要求

- Python 3.6 及以上版本
- 无需安装任何第三方依赖

## 🚀 快速开始

### 1. 获取项目
```bash
git clone https://github.com/你的用户名/merge_files_to_md.git
cd merge_files_to_md
```

### 2. 编辑配置
复制并重命名示例配置文件 `merge_files_to_md.ini`，根据需求填写输出目录、文件清单、忽略规则等。

### 3. （可选）编写头部说明
新建 `merge_files_to_md.header` 文件，写入需要放在文档开头的说明内容，支持完整 Markdown 语法。

### 4. 运行脚本
- Windows：直接双击 `merge_files_to_md.py`
- 命令行：
  ```bash
  python merge_files_to_md.py
  ```

运行完成后，生成的 Markdown 文档与备份压缩包将输出到指定目录。

## ⚙️ 配置说明

配置文件与脚本同名，后缀为 `.ini`，支持 `#` 和 `;` 开头的整行注释。

### [OutputFolder]
输出文件所在目录，支持相对路径（相对于脚本所在目录）与绝对路径，目录不存在时自动创建。

### [OutputFileName]
输出文件的名称前缀，最终文件名格式：`前缀-YYYYMMDDHHmm.md`，同一分钟内重复运行自动追加秒数避免覆盖。

### [Title]
合并后 Markdown 文档的一级置顶标题，取第一行非空内容。

### [Options]
全局功能开关：
- `EnableBackupZip`：是否生成源文件备份压缩包，可选 `true/false`，默认开启

### [IgnoreList]
文件忽略规则，优先级最高，匹配后无论手动列出还是通配符展开的文件都会被过滤。
- 支持精确路径匹配与 glob 通配符
- 路径层级严格对应：`*.log` 仅匹配根目录，`utils\*.log` 仅匹配对应目录
- 示例：
  ```ini
  *.log
  temp\*.tmp
  *\*.bak
  secret.env
  ```

### [FileList]
待合并的文件清单，严格按从上到下的顺序输出。
- 支持单个文件路径：`main.py`、`utils\helper.ps1`
- 支持目录通配符：`scripts\*`（仅匹配目录下的直接文件，不递归子目录）
- 支持绝对路径

### [LangMap]
特殊文件名自定义语言标识，优先级高于后缀自动匹配，用于无后缀或自定义命名的文件。
- 格式：`完整文件名 = 代码块语言标识`
- 示例：
  ```ini
  .env = ini
  Dockerfile = dockerfile
  ```

### 外部头部文件
- 文件名：`脚本同名.header`
- 内容会原样输出到标题下方、文件清单上方，不包裹代码块
- 支持完整 Markdown 语法，内容非空时自动在下方添加分隔线
- 文件不存在或内容为空时自动跳过

## 📁 项目结构
```
merge_files_to_md/
├── merge_files_to_md.py      # 主脚本
├── merge_files_to_md.ini     # 配置文件
├── merge_files_to_md.header  # （可选）头部说明文件
├── README.md                 # 项目说明
├── CHANGELOG.md              # 更新记录
└── LICENSE                   # MIT 许可证
```

## 📝 输出格式示例
```markdown
# 项目标题

这里是头部说明内容，支持 Markdown 语法

---

## main.py
```python
# 文件内容
```

## utils\helper.ps1
```powershell
# 文件内容
```
```

## 📄 许可证

MIT License
