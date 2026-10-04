# dedup.py — 重复文件查找器

纯标准库、零依赖的重复文件查找/清理工具。按内容哈希或文件名找出重复文件，默认只报告，`--delete` 才真正删除（每组保留第一个）。

## 特性

- ✅ 按内容（sha256）找「完全一样」的重复文件
- ✅ 按文件名找同名文件（跨目录）
- ✅ 递归子目录、可设最小文件大小过滤
- ✅ 默认只报告不删除；删除前需二次输入 `yes` 确认
- ✅ 显示可释放的磁盘空间
- ✅ 零第三方依赖（只用标准库）

## 快速开始

```bash
# 查找内容重复的文件（只报告）
python3 dedup.py --dir ~/Downloads --by-content --recursive

# 确认后真正删除（每组保留第一个）
python3 dedup.py --dir ~/Downloads --by-content --recursive --delete
```

## 常见用法

| 需求 | 命令 |
|---|---|
| 按内容找重复 | `--by-content --recursive` |
| 按文件名找重复 | `--by-name --recursive` |
| 只处理大文件 | `--min-size 1M` |
| 真正删除副本 | `--delete` |

## 示例

### 1. 找相册里的重复照片

```bash
python3 dedup.py --dir ~/Pictures --by-content --min-size 500K --recursive
```

### 2. 找下载目录的重复安装包

```bash
python3 dedup.py --dir ~/Downloads --by-name --recursive
```

### 3. 确认无误后清理

```bash
python3 dedup.py --dir ~/Pictures --by-content --recursive --delete
# 程序会提示输入 yes 才真正删除
```

## 完整参数

```
--dir DIR          目标目录（默认当前目录）
--recursive        递归子目录
--by-content       按内容哈希查找重复
--by-name          按文件名查找重复
--min-size 1M      只处理不小于该大小的文件
--delete           真正删除每组除第一个外的副本
```

## 工作原理

- **按内容**：先按文件大小分组（加速），同大小的再算 sha256，哈希相同即判定重复。
- **按文件名**：按文件名小写分组，跨目录同名即判定重复。

## 安全说明

- 默认只报告，绝不删除。
- `--delete` 会要求你输入 `yes` 二次确认。
- 每组**总是保留第一个**，只删后面的副本。
- 每次删除都有日志打印，可回溯。

## License

MIT
