#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smartfile_gui.py —— 智能文件归类助手（带图形界面）

双击或 `python3 smartfile_gui.py` 启动窗口：
  - 选文件夹、选配置文件
  - 一眼看到「每个文件会被归到哪个文件夹」
  - 一键预览 / 开始归类
  - 搜索框检索相关文件

复用 smartfile.py 的核心逻辑（文本提取、规则、AI）。
GUI 用 macOS 自带 tkinter，零第三方依赖。

启动方式（任选）：
  python3 smartfile_gui.py
  # 或直接双击（需先 chmod +x）
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import json
import os
from pathlib import Path

# 复用 smartfile 的核心函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smartfile import (
    build_index, extract_text, rule_match, load_config, AI, format_size,
    load_index_file,
)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("智能文件归类助手")
        self.geometry("900x640")
        self.minsize(760, 500)

        self.dir_var = tk.StringVar(value=str(Path.home()))
        self.config_var = tk.StringVar(value="")
        self.search_var = tk.StringVar()
        self.cfg = None
        self.ai = None
        self.idx = []

        self._build_ui()

    def _build_ui(self):
        # —— 顶部：目录 + 配置 ——
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="文件夹：").pack(side="left")
        self.dir_entry = ttk.Entry(top, textvariable=self.dir_var, width=50)
        self.dir_entry.pack(side="left", padx=4)
        ttk.Button(top, text="浏览…", command=self.pick_dir).pack(side="left")

        cfg_row = ttk.Frame(self, padding=(10, 0))
        cfg_row.pack(fill="x")
        ttk.Label(cfg_row, text="配置：").pack(side="left")
        ttk.Entry(cfg_row, textvariable=self.config_var, width=50).pack(side="left", padx=4)
        ttk.Button(cfg_row, text="选择…", command=self.pick_config).pack(side="left")
        ttk.Button(cfg_row, text="加载", command=self.load_files).pack(side="left", padx=6)
        self.hint = ttk.Label(cfg_row, text="（可选：填 config.json 启用自定义规则）", foreground="#888")
        self.hint.pack(side="left")

        # —— 中部：表格 ——
        table = ttk.Frame(self, padding=10)
        table.pack(fill="both", expand=True)

        cols = ("file", "dest", "method")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", height=15)
        self.tree.heading("file", text="文件")
        self.tree.heading("dest", text="归类到")
        self.tree.heading("method", text="方式")
        self.tree.column("file", width=320, anchor="w")
        self.tree.column("dest", width=180, anchor="w")
        self.tree.column("method", width=80, anchor="center")

        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # —— 底部：操作按钮 + 搜索 ——
        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill="x")

        ttk.Button(bottom, text="预览归类", command=self.preview).pack(side="left")
        self.go_btn = ttk.Button(bottom, text="开始归类", command=self.organize)
        self.go_btn.pack(side="left", padx=8)

        ttk.Label(bottom, text="搜索：").pack(side="left", padx=(20, 0))
        ttk.Entry(bottom, textvariable=self.search_var, width=30).pack(side="left", padx=4)
        ttk.Button(bottom, text="检索", command=self.search).pack(side="left")

        self.status = ttk.Label(self, text="就绪", foreground="#666", padding=(10, 0))
        self.status.pack(fill="x", side="bottom")

    # —— 交互 ——
    def pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_var.set(d)

    def pick_config(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
        if f:
            self.config_var.set(f)

    def set_status(self, text, color="#666"):
        self.status.config(text=text, foreground=color)

    def load_files(self):
        d = self.dir_var.get()
        if not os.path.isdir(d):
            messagebox.showerror("错误", f"文件夹不存在：\n{d}")
            return
        cfg_path = self.config_var.get()
        self.cfg = load_config(cfg_path) if cfg_path else {"categories": [], "project_hints": []}
        self.ai = AI(self.cfg.get("ai"))
        self.idx = build_index(d, True)
        self._fill_table(self.idx)
        self.set_status(f"已加载 {len(self.idx)} 个文件", "#2a6")

    def _fill_table(self, idx):
        self.tree.delete(*self.tree.get_children())
        for f in idx:
            self.tree.insert("", "end", values=(f["name"], "", ""))

    def _classify(self, f):
        """返回 (folder, method)"""
        all_cats = self.cfg.get("categories", []) + self.cfg.get("project_hints", [])
        text = f["text"]
        cat = rule_match(text, all_cats)
        method = "规则"
        if cat is None and text.strip():
            name = self.ai.classify(text, [c["name"] for c in all_cats])
            if name:
                cat = next((c for c in all_cats if c["name"] == name), None)
                method = "AI"
        if cat is None:
            return (self.cfg.get("default_folder", "未分类"), "默认")
        return (cat.get("folder", cat["name"]), method)

    def preview(self):
        if not self.idx:
            self.load_files()
        if not self.idx:
            return
        self.tree.delete(*self.tree.get_children())
        for f in self.idx:
            folder, method = self._classify(f)
            self.tree.insert("", "end", values=(f["name"], folder, method))
        self.set_status(f"预览：{len(self.idx)} 个文件的归类结果", "#a60")

    def organize(self):
        if not self.idx:
            self.load_files()
        if not self.idx:
            return
        if not messagebox.askyesno("确认", f"即将归类 {len(self.idx)} 个文件到子文件夹，继续？"):
            return
        d = Path(self.dir_var.get())
        action = self.cfg.get("action", "copy")
        done = 0
        self.tree.delete(*self.tree.get_children())
        import shutil
        for f in self.idx:
            folder, method = self._classify(f)
            dest_dir = d / folder
            dest = dest_dir / f["name"]
            if dest == Path(f["path"]):
                self.tree.insert("", "end", values=(f["name"], "已在原位", method)); continue
            if not folder:
                folder = "未分类"
                dest_dir = d / folder; dest = dest_dir / f["name"]
            dest_dir.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                self.tree.insert("", "end", values=(f["name"], "已存在(跳过)", method)); continue
            try:
                shutil.copy2(f["path"], dest) if action != "move" else Path(f["path"]).rename(dest)
                self.tree.insert("", "end", values=(f["name"], folder, method))
                done += 1
            except Exception as e:
                self.tree.insert("", "end", values=(f["name"], f"失败:{e}", method))
        self.set_status(f"完成：归类 {done} 个文件", "#2a6")
        messagebox.showinfo("完成", f"已归类 {done} 个文件到对应子文件夹。")

    def search(self):
        if not self.idx:
            self.load_files()
        if not self.idx:
            return
        q = self.search_var.get().strip()
        if not q:
            messagebox.showinfo("提示", "请输入搜索词"); return
        import re, hashlib
        terms = [t for t in re.split(r"[\s,，、。|]+", q) if t]

        # 优先走倒排索引 + BM25（快）
        data = load_index_file(self.dir_var.get())
        if data and data.get("inverted"):
            from smartfile import bm25_score, tokenize
            docs = data["docs"]
            q_terms = []
            for t in terms:
                q_terms.extend(tokenize(t))
            scores = bm25_score(q_terms, data["inverted"], data["doc_stats"], len(docs))
            self.tree.delete(*self.tree.get_children())
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:50]
            for did, score in ranked:
                d = docs[int(did)]
                self.tree.insert("", "end", values=(d["name"], f"{score:.2f}", ""))
            self.set_status(f"检索到 {len(scores)} 个相关文件（倒排索引）", "#246" if scores else "#a60")
            return

        # 无索引时退化线性扫描
        seen = set(); results = []
        for f in self.idx:
            blob = f["name"] + "\n" + f["text"]
            if any(t.lower() in blob.lower() for t in terms):
                key = hashlib.md5(f["text"].encode()).hexdigest()[:16]
                if key in seen: continue
                seen.add(key); results.append(f)
        self.tree.delete(*self.tree.get_children())
        for f in results[:50]:
            self.tree.insert("", "end", values=(f["name"], "相关", ""))
        self.set_status(f"检索到 {len(results)} 个相关文件", "#246" if results else "#a60")


if __name__ == "__main__":
    App().mainloop()
