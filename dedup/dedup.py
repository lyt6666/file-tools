#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dedup.py —— 重复文件查找器（纯标准库，零依赖）

功能：
  1. 按内容（sha256 哈希）找出完全相同的重复文件
  2. 按文件名（忽略内容）找出同名文件
  3. 递归扫描子目录
  4. 列出每组重复项 + 可安全删除的副本（保留每组第一个）
  5. --delete 才真正删除副本；默认仅报告

用法示例：
  # 查找目录下内容重复的文件（仅报告，不删除）
  python3 dedup.py --dir ~/Downloads --by-content --recursive

  # 按文件名找重复
  python3 dedup.py --dir ~/Downloads --by-name --recursive

  # 跳过小于 1MB 的文件，避免误判
  python3 dedup.py --dir ~/Pictures --by-content --min-size 1M --recursive

  # 确认后真正删除副本（保留每组第一个）
  python3 dedup.py --dir ~/Downloads --by-content --recursive --delete

安全：默认只报告不删除；--delete 只删「每组除第一个外的副本」，且每个删除都有日志。
零依赖，macOS / Linux / Windows 自带 python3 即可运行。
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path


def parse_size(s):
    """解析 1K / 1M / 1G 之类的大小字符串为字节数"""
    s = s.strip().upper()
    units = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
    for suffix in ("G", "M", "K", ""):
        if s.endswith(suffix):
            num = s[: len(s) - len(suffix)] if suffix else s
            try:
                return int(float(num) * units[suffix])
            except ValueError:
                break
    print(f"[错误] 无法解析大小：{s}（示例：1M、500K、2G）", file=sys.stderr)
    sys.exit(1)


def file_hash(path, chunk=8192):
    """计算文件 sha256，大文件分块读取"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def collect_files(directory, recursive, min_size):
    root = Path(directory)
    if not root.is_dir():
        print(f"[错误] 目录不存在：{directory}", file=sys.stderr)
        sys.exit(1)
    it = root.rglob("*") if recursive else root.glob("*")
    files = [p for p in it if p.is_file()]
    if min_size:
        files = [p for p in files if p.stat().st_size >= min_size]
    return files


def find_by_content(files):
    """按大小预分组，再按内容 hash 精判"""
    by_size = {}
    for f in files:
        sz = f.stat().st_size
        by_size.setdefault(sz, []).append(f)

    groups = []
    for sz, fs in by_size.items():
        if len(fs) < 2:
            continue
        by_hash = {}
        for f in fs:
            h = file_hash(f)
            by_hash.setdefault(h, []).append(f)
        for h, dupes in by_hash.items():
            if len(dupes) > 1:
                groups.append(dupes)
    return groups


def find_by_name(files):
    by_name = {}
    for f in files:
        by_name.setdefault(f.name.lower(), []).append(f)
    return [fs for fs in by_name.values() if len(fs) > 1]


def main():
    p = argparse.ArgumentParser(
        description="重复文件查找器（纯标准库零依赖）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dir", default=".", help="目标目录（默认当前目录）")
    p.add_argument("--recursive", action="store_true", help="递归子目录")
    p.add_argument("--by-content", action="store_true", help="按内容哈希查找重复")
    p.add_argument("--by-name", action="store_true", help="按文件名查找重复")
    p.add_argument("--min-size", default="", help="只处理不小于该大小的文件，如 1M")
    p.add_argument("--delete", action="store_true", help="真正删除每组除第一个外的副本")
    args = p.parse_args()

    if args.by_content == args.by_name:  # 都真或都假
        print("[错误] 必须且只能指定一项：--by-content 或 --by-name", file=sys.stderr)
        sys.exit(1)

    min_size = parse_size(args.min_size) if args.min_size else 0
    files = collect_files(args.dir, args.recursive, min_size)
    print(f"\n扫描到 {len(files)} 个文件（min-size={args.min_size or '不限'}）...\n")

    groups = find_by_content(files) if args.by_content else find_by_name(files)

    if not groups:
        print("未发现重复文件。")
        return

    total_reclaim = 0
    total_dupes = 0
    for i, g in enumerate(groups, 1):
        print(f"[组 {i}] 共 {len(g)} 个重复文件：")
        for j, f in enumerate(g):
            mark = "【保留】" if j == 0 else "【副本】"
            sz = f.stat().st_size
            print(f"    {mark} {f}  ({human_size(sz)})")
            if j > 0:
                total_dupes += 1
                total_reclaim += sz
        print()

    print(f"共 {len(groups)} 组重复，{total_dupes} 个可删副本，可释放约 {human_size(total_reclaim)}")

    if args.delete:
        confirm = input(f"\n确认删除以上 {total_dupes} 个副本（每组保留第一个）？输入 yes 继续：")
        if confirm.strip().lower() != "yes":
            print("已取消。")
            return
        deleted = 0
        for g in groups:
            for f in g[1:]:
                try:
                    f.unlink()
                    print(f"  已删除：{f}")
                    deleted += 1
                except Exception as e:
                    print(f"  删除失败 {f}：{e}", file=sys.stderr)
        print(f"\n完成：删除 {deleted} 个副本，释放约 {human_size(sum(g[1].stat().st_size for g in groups)) if False else total_reclaim}")
    else:
        print("提示：确认无误后加 --delete 再运行才会真正删除（每组保留第一个）。")


if __name__ == "__main__":
    main()
