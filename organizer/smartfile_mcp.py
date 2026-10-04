#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smartfile_mcp.py —— 智能文件归类助手的 MCP Server（stdio + JSON-RPC）

把 smartfile.py 的核心能力（organize / search / index）暴露成 MCP 工具，
供 OpenClaw、Claude Desktop、Cursor 等任何支持 MCP 的客户端调用。

零第三方依赖：纯标准库实现 MCP 协议（JSON-RPC 2.0 over stdio）。

启动方式（由 MCP 客户端拉起）：
  python3 /path/to/smartfile_mcp.py

暴露的工具：
  - smartfile_organize  按内容归类（规则 + AI 兜底）
  - smartfile_search    检索相关文件（倒排索引 + BM25）
  - smartfile_index     重建索引

实现覆盖 MCP 的：
  - initialize （协商协议版本 + 能力）
  - tools/list （列出工具 + JSON Schema）
  - tools/call （执行工具）
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smartfile import (
    build_index, save_index, load_index_file, rule_match, load_config, AI,
    bm25_score, tokenize, format_size,
)


# --- MCP 工具定义（JSON Schema）-----------------------------------------

TOOLS = [
    {
        "name": "smartfile_organize",
        "description": (
            "按文件内容自动归类：先按用户自定义规则匹配，匹配不到用 AI 兜底，"
            "最终归档到对应子文件夹。返回每个文件的归类结果。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dir": {"type": "string", "description": "要整理的目标目录（绝对路径）"},
                "config": {"type": "string", "description": "配置文件路径（分类规则 + AI 配置），可选"},
                "dry_run": {"type": "boolean", "description": "只预览不实际执行，默认 true", "default": True},
                "action": {"type": "string", "enum": ["copy", "move"], "description": "copy 保留原件，move 移动，默认 copy"},
            },
            "required": ["dir"],
        },
    },
    {
        "name": "smartfile_search",
        "description": (
            "检索与查询相关的文件。优先用预建倒排索引 + BM25 相关度排序，"
            "海量文件也能毫秒级返回。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dir": {"type": "string", "description": "目标目录（绝对路径）"},
                "query": {"type": "string", "description": "查询词，可多个词用空格分隔"},
                "config": {"type": "string", "description": "配置文件路径，可选"},
                "limit": {"type": "integer", "description": "最多返回条数，默认 20"},
            },
            "required": ["dir", "query"],
        },
    },
    {
        "name": "smartfile_index",
        "description": (
            "重建目录的文件索引（含倒排索引 + BM25 统计量），"
            "之后 search 会立即变快。返回索引的文件数量。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dir": {"type": "string", "description": "目标目录（绝对路径）"},
                "config": {"type": "string", "description": "配置文件路径，可选"},
            },
            "required": ["dir"],
        },
    },
]


# --- 工具实现 -----------------------------------------------------------

def _tool_organize(args):
    dir_ = args.get("dir", ".")
    cfg = load_config(args.get("config")) if args.get("config") else {"categories": [], "project_hints": []}
    ai = AI(cfg.get("ai"))
    all_cats = cfg.get("categories", []) + cfg.get("project_hints", [])
    cat_names = [c["name"] for c in all_cats]
    default_folder = cfg.get("default_folder", "未分类")
    action = args.get("action", "copy")
    dry_run = args.get("dry_run", True)

    idx = build_index(dir_, True)
    results = []
    ai_used = 0
    import shutil
    for f in idx:
        text = f["text"]
        cat = rule_match(text, all_cats)
        method = "规则"
        if cat is None and text.strip():
            name = ai.classify(text, cat_names)
            if name:
                cat = next((c for c in all_cats if c["name"] == name), None)
                method = "AI"
                ai_used += 1
        folder = default_folder if cat is None else cat.get("folder", cat["name"])

        entry = {"file": f["name"], "folder": folder, "method": method, "to": str(Path(dir_) / folder / f["name"])}
        if not dry_run:
            dest_dir = Path(dir_) / folder
            dest = dest_dir / f["name"]
            if dest == Path(f["path"]):
                entry["status"] = "已在原位"
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    entry["status"] = "目标已存在(跳过)"
                else:
                    try:
                        if action == "move":
                            Path(f["path"]).rename(dest)
                        else:
                            shutil.copy2(f["path"], dest)
                        entry["status"] = "完成"
                    except Exception as e:
                        entry["status"] = f"失败:{e}"
        results.append(entry)

    return {
        "total": len(results),
        "ai_used": ai_used,
        "dry_run": dry_run,
        "results": results,
    }


def _tool_search(args):
    dir_ = args.get("dir", ".")
    query = args.get("query", "")
    limit = int(args.get("limit", 20))
    cfg = load_config(args.get("config")) if args.get("config") else {"ai": {}}
    ai = AI(cfg.get("ai"))

    import re
    terms = [t for t in re.split(r"[\s,，、。|]+", query) if t]

    data = load_index_file(dir_)
    results = []
    if data and data.get("inverted"):
        docs = data["docs"]
        q_terms = []
        for t in terms:
            q_terms.extend(tokenize(t))
        scores = bm25_score(q_terms, data["inverted"], data["doc_stats"], len(docs))
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        for did, score in ranked:
            d = docs[int(did)]
            results.append({
                "name": d["name"], "ext": d["ext"], "size": d["size"],
                "path": d["path"], "score": round(score, 4),
            })
        return {"query": query, "matched": len(scores), "results": results}
    else:
        # 无索引：线性扫描 + 去重
        import hashlib
        idx = build_index(dir_, True)
        seen = set()
        for f in idx:
            blob = f["name"] + "\n" + f["text"]
            if any(t.lower() in blob.lower() for t in terms):
                key = hashlib.md5(f["text"].encode("utf-8")).hexdigest()[:16]
                if key in seen:
                    continue
                seen.add(key)
                results.append({"name": f["name"], "ext": f["ext"], "size": f["size"], "path": f["path"], "score": None})
        return {"query": query, "matched": len(results), "results": results[:limit]}


def _tool_index(args):
    dir_ = args.get("dir", ".")
    idx = build_index(dir_, True)
    save_index(idx, dir_)
    return {"indexed": len(idx), "index_file": str(Path(dir_) / ".smartfile_index.json")}


TOOL_HANDLERS = {
    "smartfile_organize": _tool_organize,
    "smartfile_search": _tool_search,
    "smartfile_index": _tool_index,
}


# --- MCP stdio JSON-RPC 循环 --------------------------------------------

def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(session_id, msg):
    method = msg.get("method")
    req_id = msg.get("id")
    m_id = msg.get("id")  # 兼容

    if method == "initialize":
        return send({
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "smartfile-mcp", "version": "1.0.0"},
            },
        })

    if method == "notifications/initialized":
        return  # 无需回复

    if method == "ping":
        return send({"jsonrpc": "2.0", "id": req_id, "result": {}})

    if method == "tools/list":
        return send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})

    if method == "tools/call":
        name = msg["params"]["name"]
        cargs = msg["params"].get("arguments", {})
        try:
            if name not in TOOL_HANDLERS:
                raise ValueError(f"未知工具: {name}")
            result = TOOL_HANDLERS[name](cargs)
            content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            return send({"jsonrpc": "2.0", "id": req_id, "result": {"content": content}})
        except Exception as e:
            return send({
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": f"错误: {e}"}], "isError": True},
            })

    # 未知方法
    return send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"未知方法: {method}"}})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(None, msg)


if __name__ == "__main__":
    main()
