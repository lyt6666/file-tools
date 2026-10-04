# batchrenamer.py — 文件批量改名 / 整理器

纯标准库、零依赖的 macOS/Linux/Windows 通用命令行小工具。批量重命名、分类归档，全程 `--dry-run` 预览，确认无误才真正执行。

## 特性

- ✅ 加前缀 / 后缀、文本替换、正则替换、补零序号
- ✅ 按扩展名一键分类归档
- ✅ 递归子目录
- ✅ 默认或 `--dry-run` 只预览，绝不误改
- ✅ 零第三方依赖（只用标准库）

## 快速开始

```bash
# 预览：给所有 jpg 加前缀（不真正改名）
python3 batchrenamer.py --dir ~/Pictures --ext .jpg --prefix 旅行_ --dry-run

# 确认后真正执行（去掉 --dry-run）
python3 batchrenamer.py --dir ~/Pictures --ext .jpg --prefix 旅行_
```

## 常见用法

| 需求 | 命令 |
|---|---|
| 加前缀 | `--prefix 前缀` |
| 加后缀 | `--suffix 后缀` |
| 替换文本 | `--replace "旧->新"` |
| 正则替换 | `--regex "s/旧/新/g"` |
| 补零序号 | `--seq --seq-dir 3 --name img ` |
| 按扩展名归档 | `--organize-by-ext` |
| 递归子目录 | `--recursive` |
| 只预览 | `--dry-run` |

## 示例

### 1. 给照片批量加日期前缀

```bash
python3 batchrenamer.py --dir ~/Pictures/2026-10 --ext .jpg --prefix 20261004_ --dry-run
```

### 2. 把文件名里的空格换成下划线

```bash
python3 batchrenamer.py --dir ./ --regex 's/ +/_/g' --dry-run
```

### 3. 下载目录按类型归档

```bash
python3 batchrenamer.py --dir ~/Downloads --organize-by-ext --dry-run
```

### 4. 序号重命名

```bash
python3 batchrenamer.py --dir ./ --ext .png --seq --seq-dir 3 --name 截图 --dry-run
# 结果：截图_001.png, 截图_002.png ...
```

## 完整参数

```
--dir DIR            目标目录（默认当前目录）
--ext .jpg           只处理某扩展名（含点）
--recursive          递归子目录
--prefix 前缀        文件名加前缀
--suffix 后缀        文件名主体加后缀
--replace "旧->新"    文本替换
--regex "s/旧/新/标志"  正则替换（标志 g/i/m）
--seq                按序号重命名
--seq-dir N          序号补零位数（默认 3）
--name 基础名        序号模式下的基础名
--organize-by-ext    按扩展名分类归档
--dry-run            只预览不执行
```

## 安全说明

- 默认不改任何东西；去掉 `--dry-run` 才会真正重命名/移动。
- 目标文件名已存在时会自动跳过，绝不覆盖。
- 归档模式遇到目标已存在也会跳过。

## License

MIT
