#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smartfile.py —— 智能文件归类 + 语义检索助手

根据文件【内容】自动归类，建立索引，支持关联检索。

两大能力：
  1. organize  按内容归类：用户自定义规则 + AI 兜底，把文件归档到对应文件夹
  2. search    检索：列出与查询相关的文件（关键词 + AI 语义检索）

可插拔 AI：本地 Ollama（免费离线）或 OpenAI/DeepSeek 兼容 API（填 key）。

用法：
  # 归类（先 dry-run 预览）
  python3 smartfile.py organize --dir ~/Documents --config config.json --dry-run
  python3 smartfile.py organize --dir ~/Documents --config config.json

  # 检索
  python3 smartfile.py search --dir ~/Documents --query "上个月的报销发票"

  # 重建索引
  python3 smartfile.py index --dir ~/Documents --config config.json

零第三方硬依赖（AI 接口用标准库 urllib 调用，无需 pip 安装）。
文本提取：.txt/.md 直接读；.pdf 尝试 pypdf；.docx 尝试 zip+xml 解析（失败了当无文本处理）。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

# --- 文本提取 -----------------------------------------------------------

TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".log", ".json", ".py", ".rst", ".html", ".xml", ".yaml", ".yml"}


def extract_text_docx(path):
    """从 docx 提取文本（docx 是 zip 包，word/document.xml 含正文）"""
    import zipfile
    import xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(path) as z:
            with z.open("word/document.xml") as f:
                tree = ET.parse(f)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        parts = []
        for t in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
            if t.text:
                parts.append(t.text)
        return "\n".join(parts)
    except Exception:
        return ""


def extract_text_pdf(path):
    """从 pdf 提取文本，尝试 pypdf / pdfminer"""
    try:
        from pypdf import PdfReader
        r = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in r.pages)
    except Exception:
        pass
    try:
        from pdfminer.high_level import extract_text as _et
        return _et(str(path))
    except Exception:
        return ""


def extract_text(path):
    """提取文件文本，失败返回空串"""
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_EXTS:
        try:
            return Path(path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    if suffix == ".docx":
        return extract_text_docx(path)
    if suffix == ".pdf":
        return extract_text_pdf(path)
    return ""


# --- AI 接口 ------------------------------------------------------------

class AI:
    def __init__(self, ai_cfg):
        self.provider = (ai_cfg or {}).get("provider", "ollama")
        self.ollama = (ai_cfg or {}).get("ollama", {})
        self.openai = (ai_cfg or {}).get("openai", {})

    def _post(self, url, payload, headers=None):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers or {})
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def chat(self, prompt):
        if self.provider == "ollama":
            base = self.ollama.get("base_url", "http://localhost:11434")
            model = self.ollama.get("model", "qwen2.5:7b")
            r = self._post(f"{base}/api/chat", {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            })
            if r and "message" in r:
                return r["message"].get("content", "")
            return None
        else:  # openai 兼容
            base = self.openai.get("base_url", "https://api.deepseek.com")
            key = self.openai.get("api_key", "")
            model = self.openai.get("model", "deepseek-chat")
            r = self._post(f"{base}/v1/chat/completions", {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            }, headers={"Authorization": f"Bearer {key}"})
            if r and "choices" in r:
                return r["choices"][0]["message"].get("content", "")
            return None

    def classify(self, text, category_names):
        """让 AI 从给定类别里选一个，返回类别名或 None"""
        if not text.strip():
            return None
        names = "、".join(category_names)
        prompt = f"""请根据以下文件内容，从这些类别里选择最合适的一个类别：{names}。
只回答类别名本身，不要解释。如果都不合适，回答「未分类」。

文件内容（截取）：
{text[:2000]}
"""
        ans = self.chat(prompt)
        if not ans:
            return None
        ans = ans.strip().strip("。.,，\"'“”")
        for n in category_names:
            if n in ans:
                return n
        return None

    def summarize(self, text):
        if not text.strip():
            return ""
        prompt = f"用一句话（不超过30字）概括以下文件内容的核心主题：\n\n{text[:2000]}"
        ans = self.chat(prompt)
        return ans.strip() if ans else ""


# --- 分类规则 -----------------------------------------------------------

def load_config(path):
    if not os.path.exists(path):
        print(f"[错误] 配置文件不存在：{path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rule_match(text, categories):
    """基于关键词规则匹配，返回命中的类别 dict 或 None"""
    for cat in categories:
        for kw in cat.get("keywords", []):
            if kw and kw in text:
                return cat
    return None


# --- 索引 ---------------------------------------------------------------

def build_index(directory, recursive):
    idx = []
    root = Path(directory)
    if not root.is_dir():
        print(f"[错误] 目录不存在：{directory}", file=sys.stderr)
        sys.exit(1)
    it = root.rglob("*") if recursive else root.glob("*")
    for p in sorted(it):
        if not p.is_file():
            continue
        if p.name.startswith(".") or "__pycache__" in p.parts:
            continue
        # 排除工具自身的配置文件与索引文件
        if p.name.endswith(".json") and (p.name in ("config.json", "config.example.json") or p.name.startswith(".smartfile_index")):
            continue
        text = extract_text(p)
        idx.append({
            "path": str(p),
            "name": p.name,
            "ext": p.suffix.lower(),
            "size": p.stat().st_size,
            "text": text,
        })
    return idx


def save_index(idx, directory):
    idx_path = Path(directory) / ".smartfile_index.json"
    # 索引里不存完整正文，只存提取的摘要文本（受限长度）
    slim = [{"path": i["path"], "name": i["name"], "ext": i["ext"],
             "size": i["size"], "text": i["text"][:3000]} for i in idx]
    idx_path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    return idx_path


# --- 子命令 -------------------------------------------------------------

def cmd_index(args):
    cfg = load_config(args.config) if args.config else {"categories": [], "project_hints": []}
    idx = build_index(args.dir, True)
    save_index(idx, args.dir)
    print(f"[完成] 已索引 {len(idx)} 个文件 → {Path(args.dir)/'.smartfile_index.json'}")


def cmd_organize(args):
    cfg = load_config(args.config)
    ai = AI(cfg.get("ai"))
    all_cats = cfg.get("categories", []) + cfg.get("project_hints", [])
    cat_names = [c["name"] for c in all_cats]
    default_folder = cfg.get("default_folder", "未分类")
    action = cfg.get("action", "copy")
    recursive = cfg.get("recursive", True)

    idx = build_index(args.dir, recursive)
    print(f"\n待处理 {len(idx)} 个文件：\n")

    moved = 0
    ai_used = 0
    for f in idx:
        text = f["text"]
        # 1. 规则优先
        cat = rule_match(text, all_cats)
        method = "规则"
        # 2. AI 兜底
        if cat is None and text.strip():
            name = ai.classify(text, cat_names)
            if name:
                cat = next((c for c in all_cats if c["name"] == name), None)
                method = "AI"
                ai_used += 1
        # 3. 默认
        if cat is None:
            folder = default_folder
            method = "默认"
        else:
            folder = cat.get("folder", cat["name"])

        dest_dir = Path(args.dir) / folder
        dest = dest_dir / f["name"]
        print(f"  [{method}] {f['name']}  ->  {folder}/")

        if not args.dry_run:
            if dest == Path(f["path"]):
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                print(f"      [跳过] 目标已存在")
                continue
            if action == "move":
                Path(f["path"]).rename(dest)
            else:
                import shutil
                shutil.copy2(f["path"], dest)
        moved += 1

    print(f"\n{'[预览]' if args.dry_run else '[完成]'} 处理 {moved} 个文件（AI 兜底 {ai_used} 个）")
    if args.dry_run:
        print("提示：确认无误后去掉 --dry-run 重新运行即可真正执行。")


def cmd_search(args):
    ai = AI({})
    cfg = {"ai": {}}
    if args.config and os.path.exists(args.config):
        cfg = load_config(args.config)
        ai = AI(cfg.get("ai"))

    idx = build_index(args.dir, True)
    query = args.query
    print(f"\n检索「{query}」：\n")

    # 1. 关键词命中
    kw_matches = []
    ql = query.lower()
    for f in idx:
        if ql in f["name"].lower() or ql in f["text"].lower():
            kw_matches.append(f)

    # 2. AI 语义检索（把候选文本交给 AI 判断相关度）
    results = []
    if kw_matches:
        results = kw_matches
    else:
        # 无关键词命中时，用 AI 对前 N 个文件做语义判断
        candidates = idx[:20]
        for f in candidates:
            if not f["text"].strip():
                continue
            prompt = f"文件内容是否与查询「{query}」相关？回答 是 或 否：\n\n{f['text'][:800]}"
            ans = ai.chat(prompt)
            if ans and "是" in ans:
                results.append(f)

    if not results:
        print("未找到相关文件。")
        return

    for f in results[:20]:
        size = f["size"]
        print(f"  - {f['name']}  ({f['ext']}，{format_size(size)})")
        print(f"      {f['path']}")

    print(f"\n共 {len(results)} 个相关文件。")


def format_size(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


# --- 主入口 -------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="智能文件归类 + 语义检索助手")
    sub = p.add_subparsers(dest="cmd", required=True)

    po = sub.add_parser("organize", help="按内容归类")
    po.add_argument("--dir", default=".", help="目标目录")
    po.add_argument("--config", required=True, help="配置文件（分类规则 + AI）")
    po.add_argument("--dry-run", action="store_true", help="只预览")
    po.set_defaults(func=cmd_organize)

    ps = sub.add_parser("search", help="检索相关文件")
    ps.add_argument("--dir", default=".", help="目标目录")
    ps.add_argument("--query", required=True, help="查询词")
    ps.add_argument("--config", default="", help="配置文件（可选，用于 AI）")
    ps.set_defaults(func=cmd_search)

    pi = sub.add_parser("index", help="重建索引")
    pi.add_argument("--dir", default=".", help="目标目录")
    pi.add_argument("--config", default="", help="配置文件（可选）")
    pi.set_defaults(func=cmd_index)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
