# File Tools — 实用小工具合集

纯标准库、零依赖的命令行小工具，macOS / Linux / Windows 自带 `python3` 即可运行。每个工具独立、专注解决一个日常痛点。

## 工具列表

| 工具 | 目录 | 作用 |
|---|---|---|
| 文件批量改名/整理器 | [`renamer/`](renamer/) | 批量重命名、按扩展名归档、正则替换、序号命名 |
| 重复文件查找器 | [`dedup/`](dedup/) | 按内容/文件名找重复文件，安全清理释放空间 |

## 快速开始

每个工具都是单个 Python 文件，无需安装任何依赖：

```bash
# 批量改名（加前缀）
python3 renamer/batchrenamer.py --dir ~/Pictures --ext .jpg --prefix 旅行_ --dry-run

# 找重复文件
python3 dedup/dedup.py --dir ~/Downloads --by-content --recursive
```

详细用法见各工具目录下的 README。

## 设计原则

- **零依赖**：只用 Python 标准库，开箱即用。
- **安全第一**：默认 `--dry-run` 只预览，删除需二次确认，目标已存在自动跳过。
- **单一职责**：一个工具解决一个问题。
- **跨平台**：不依赖任何平台特有命令。

## License

MIT
