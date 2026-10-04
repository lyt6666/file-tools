#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batchrenamer.py —— 文件批量改名 / 整理器（纯标准库，零依赖）

功能：
  1. 批量重命名：加前缀/后缀、替换文本、正则替换、补零序号、按日期
  2. 按扩展名分类归档到子文件夹
  3. 全程 dry-run 预览，确认无误才真正执行

用法示例：
  # 预览：给所有 jpg 加前缀 "旅行_"（不会真正改名）
  python3 batchrenamer.py --dir ~/Pictures --ext .jpg --prefix 旅行_ --dry-run

  # 真正执行（去掉 --dry-run）
  python3 batchrenamer.py --dir ~/Pictures --ext .jpg --prefix 旅行_

  # 按扩展名分类归档（把目录里散落的文件按 .jpg/.png/.pdf 分到对应子文件夹）
  python3 batchrenamer.py --dir ~/Downloads --organize-by-ext --dry-run

  # 正则替换文件名里的空格为下划线
  python3 batchrenamer.py --dir ./ --regex 's/ +/_/g' --dry-run

  # 补零序号重命名：img_001.jpg, img_002.jpg ...
  python3 batchrenamer.py --dir ./ --ext .jpg --seq --seq-dir 3 --name img_

无任何第三方依赖，macOS / Linux / Windows 自带 python3 即可运行。
"""

import argparse
import os
import re
import sys
from pathlib import Path


def collect_files(directory, ext, recursive):
    """收集目录下待处理的文件，返回 [Path, ...]"""
    root = Path(directory)
    if not root.is_dir():
        print(f"[错误] 目录不存在：{directory}", file=sys.stderr)
        sys.exit(1)

    pattern = f"*{ext}" if ext else "*"
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    files = sorted([p for p in iterator if p.is_file()])
    return files


def apply_regex(name_root, regex):
    """对文件名主体（不含扩展名）执行正则替换。regex 形如 's/旧/新/标志'"""
    m = re.match(r"^s/(.+?)/(.*?)/([gim]*)$", regex)
    if not m:
        print(f"[错误] 正则格式应为 s/旧/新/标志，例如 's/ +/_/g'，收到：{regex}", file=sys.stderr)
        sys.exit(1)
    old, new, flags = m.groups()
    reflags = 0
    if "i" in flags:
        reflags |= re.IGNORECASE
    if "m" in flags:
        reflags |= re.MULTILINE
    count = 0 if "g" in flags else 1
    return re.sub(old, new, name_root, count=count, flags=reflags)


def build_new_name(path, args, seq_counter):
    """根据参数构造新文件名，返回新 Path 或 None（不改变）"""
    name = path.name
    stem, suffix = path.stem, path.suffix

    new_stem = stem

    if args.seq:
        # 补零序号：name + 序号
        width = args.seq_dir
        base = args.names or stem
        new_stem = f"{base}_{str(seq_counter).zfill(width)}"
    else:
        if args.prefix:
            new_stem = args.prefix + new_stem
        if args.suffix_:
            new_stem = new_stem + args.suffix_
        if args.replace:
            if args.replace.count("->") == 1:
                old, new = args.replace.split("->")
                new_stem = new_stem.replace(old, new)
            else:
                print(f"[错误] --replace 格式应为 旧->新，收到：{args.replace}", file=sys.stderr)
                sys.exit(1)
        if args.regex:
            new_stem = apply_regex(new_stem, args.regex)

    if new_stem == stem:
        return None

    new_name = new_stem + suffix
    return path.with_name(new_name)


def organize_by_ext(files, dry_run):
    """按扩展名把文件归档到子文件夹"""
    moved = 0
    for f in files:
        ext = f.suffix.lstrip(".").lower() or "noext"
        target_dir = f.parent / ext
        target = target_dir / f.name
        if target == f:
            continue
        if dry_run:
            print(f"  [归档] {f.name}  ->  {ext}/")
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            if target.exists():
                print(f"  [跳过] 目标已存在：{target.name}")
                continue
            f.rename(target)
        moved += 1
    return moved


def main():
    p = argparse.ArgumentParser(
        description="文件批量改名 / 整理器（纯标准库零依赖）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dir", default=".", help="目标目录（默认当前目录）")
    p.add_argument("--ext", default="", help="只处理某扩展名，如 .jpg（含点）")
    p.add_argument("--recursive", action="store_true", help="递归子目录")
    p.add_argument("--prefix", default="", help="文件名加前缀")
    p.add_argument("--suffix", dest="suffix_", default="", help="文件名主体加后缀")
    p.add_argument("--replace", default="", help="文本替换，格式 旧->新")
    p.add_argument("--regex", default="", help="正则替换，格式 s/旧/新/标志")
    p.add_argument("--seq", action="store_true", help="按序号重命名")
    p.add_argument("--seq-dir", type=int, default=3, help="序号补零位数（默认 3）")
    p.add_argument("--name", dest="names", default="", help="序号模式下的基础名")
    p.add_argument("--organize-by-ext", action="store_true", help="按扩展名分类归档")
    p.add_argument("--dry-run", action="store_true", help="只预览，不真正改动")
    args = p.parse_args()

    files = collect_files(args.dir, args.ext, args.recursive)
    if not files:
        print(f"[提示] 目录 {args.dir} 下没有匹配的文件（ext={args.ext or '全部'}）")
        return

    print(f"\n共找到 {len(files)} 个文件{'(dry-run 预览)' if args.dry_run else ''}：\n")

    if args.organize_by_ext:
        moved = organize_by_ext(files, args.dry_run)
        print(f"\n{'[预览]' if args.dry_run else '[完成]'} 归档 {moved} 个文件")
        return

    seq_counter = 0
    changed = 0
    for f in files:
        seq_counter += 1
        new = build_new_name(f, args, seq_counter)
        if new is None:
            print(f"  [不变] {f.name}")
            continue
        if new.exists() and new != f:
            print(f"  [跳过] 目标已存在：{new.name}")
            continue
        print(f"  {f.name}  ->  {new.name}")
        if not args.dry_run:
            f.rename(new)
        changed += 1

    print(f"\n{'[预览]' if args.dry_run else '[完成]'} 将改名/已改名 {changed} 个文件（共 {len(files)} 个）")
    if args.dry_run:
        print("提示：确认无误后，去掉 --dry-run 重新运行即可真正执行。")


if __name__ == "__main__":
    main()
