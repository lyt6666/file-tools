#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smartfile_gui.py —— 智能文件归类助手（图形界面版）

双击 `.app` 或 `python3 smartfile_gui.py` 启动窗口。

功能：
  - 选一个文件夹 → 自动扫描其中的文件
  - 一眼预览「每个文件会被归到哪个文件夹」（规则 / AI / 默认）
  - 一键「生成示例配置」自定义分类规则，或加载你自己的 config.json
  - 一键「开始归类」（默认 copy 保留原件，可切换为 move）
  - 搜索框：倒排索引 + BM25 相关度排序，海量文件毫秒级

复用 smartfile.py 的核心逻辑。GUI 用 macOS 自带 tkinter，零第三方依赖。
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import json
import os
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smartfile import (
    build_index, rule_match, load_config, AI, format_size,
    load_index_file,
)

EXAMPLE_CONFIG = {
    "categories": [
        {"name": "财务", "folder": "财务", "keywords": ["报销", "发票", "打车费", "餐饮费", "办公用品", "工资", "账单"]},
        {"name": "合同", "folder": "合同", "keywords": ["合同", "甲方", "乙方", "租金", "租期", "协议"]},
        {"name": "会议", "folder": "会议", "keywords": ["会议", "纪要", "讨论", "汇报", "周会"]},
        {"name": "人事", "folder": "人事", "keywords": ["简历", "入职", "离职", "面试", "考勤"]},
    ],
    "default_folder": "未分类",
    "action": "copy",
    # "ai": {"provider": "ollama", "base_url": "http://localhost:11434", "model": "qwen2.5:7b"},
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("智能文件归类助手")
        self.geometry("960x680")
        self.minsize(800, 560)

        self.dir_var = tk.StringVar(value=str(Path.home()))
        self.config_var = tk.StringVar(value="")
        self.search_var = tk.StringVar()
        self.action_var = tk.StringVar(value="copy")
        self.cfg = None
        self.ai = None
        self.idx = []

        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        # 顶部标题栏
        head = ttk.Frame(self, padding=(12, 10, 12, 4))
        head.pack(fill="x")
        ttk.Label(head, text="📁 智能文件归类助手", font=("", 16, "bold")).pack(side="left")
        ttk.Label(head, text="按内容自动整理 · 规则 + AI 兜底 · 倒排索引秒搜", foreground="#888").pack(side="right")

        # 目录行
        dir_row = ttk.Frame(self, padding=(12, 8))
        dir_row.pack(fill="x")
        ttk.Label(dir_row, text="文件夹：").pack(side="left")
        ttk.Entry(dir_row, textvariable=self.dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(dir_row, text="浏览…", command=self.pick_dir).pack(side="left")
        ttk.Button(dir_row, text="扫描", command=self.load_files).pack(side="left", padx=(6, 0))

        # 配置行
        cfg_row = ttk.Frame(self, padding=(12, 4))
        cfg_row.pack(fill="x")
        ttk.Label(cfg_row, text="规则配置：").pack(side="left")
        ttk.Entry(cfg_row, textvariable=self.config_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(cfg_row, text="选择…", command=self.pick_config).pack(side="left")
        ttk.Button(cfg_row, text="生成示例", command=self.gen_config).pack(side="left", padx=(6, 0))
        ttk.Label(cfg_row, text="（可选：无配置则全部归入「未分类」）", foreground="#999").pack(side="right")

        # 选项行：copy/move
        opt_row = ttk.Frame(self, padding=(12, 4))
        opt_row.pack(fill="x")
        ttk.Label(opt_row, text="处理方式：").pack(side="left")
        ttk.Radiobutton(opt_row, text="复制（保留原件，安全）", variable=self.action_var, value="copy").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(opt_row, text="移动（剪切到分类夹）", variable=self.action_var, value="move").pack(side="left")

        # 表格
        table = ttk.Frame(self, padding=(12, 8))
        table.pack(fill="both", expand=True)
        cols = ("file", "dest", "method")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", height=16)
        self.tree.heading("file", text="文件")
        self.tree.heading("dest", text="归类到")
        self.tree.heading("method", text="方式")
        self.tree.column("file", width=420, anchor="w")
        self.tree.column("dest", width=220, anchor="w")
        self.tree.column("method", width=80, anchor="center")
        self.tree.tag_configure("ok", foreground="#1a7f37")
        self.tree.tag_configure("def", foreground="#999")
        self.tree.tag_configure("ai", foreground="#8250df")
        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._open_file)

        # 操作行
        act_row = ttk.Frame(self, padding=(12, 6))
        act_row.pack(fill="x")
        ttk.Button(act_row, text="预览归类", command=self.preview).pack(side="left")
        self.go_btn = ttk.Button(act_row, text="开始归类", command=self.organize)
        self.go_btn.pack(side="left", padx=(8, 0))
        ttk.Label(act_row, text="搜索：").pack(side="left", padx=(24, 0))
        ttk.Entry(act_row, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(act_row, text="检索", command=self.search).pack(side="left")

        # 状态栏
        self.status = ttk.Label(self, text="就绪 — 选一个文件夹后点「扫描」", foreground="#666", padding=(12, 6))
        self.status.pack(fill="x", side="bottom")

    # ---------- 交互 ----------
    def pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_var.set(d)

    def pick_config(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
        if f:
            self.config_var.set(f)
            self.load_files()

    def gen_config(self):
        d = self.dir_var.get() or str(Path.home())
        target = str(Path(d) / "config.json")
        if os.path.exists(target):
            if not messagebox.askyesno("覆盖?", f"{target}\n已存在，覆盖为示例配置？"):
                return
        with open(target, "w", encoding="utf-8") as f:
            json.dump(EXAMPLE_CONFIG, f, ensure_ascii=False, indent=2)
        self.config_var.set(target)
        self.load_files()
        self.set_status(f"已生成示例配置：{target}", "#2a6")

    def set_status(self, text, color="#666"):
        self.status.config(text=text, foreground=color)

    def load_files(self):
        d = self.dir_var.get().strip()
        if not os.path.isdir(d):
            messagebox.showerror("错误", f"文件夹不存在：\n{d}")
            return
        cfg_path = self.config_var.get().strip()
        self.cfg = load_config(cfg_path) if cfg_path else {"categories": [], "project_hints": []}
        self.ai = AI(self.cfg.get("ai"))
        self.idx = build_index(d, True)
        self._fill_table(self.idx)
        self.set_status(f"已扫描 {len(self.idx)} 个文件（规则 {len(self.cfg.get('categories', []))} 类）", "#2a6")

    def _fill_table(self, idx):
        self.tree.delete(*self.tree.get_children())
        for f in idx:
            self.tree.insert("", "end", values=(f["name"], "—", "—"))

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

    def _tag_for(self, method):
        return {"规则": "ok", "AI": "ai", "默认": "def"}.get(method, ())

    def preview(self):
        if not self.idx:
            self.load_files()
        if not self.idx:
            return
        self.tree.delete(*self.tree.get_children())
        for f in self.idx:
            folder, method = self._classify(f)
            self.tree.insert("", "end", values=(f["name"], folder, method), tags=(self._tag_for(method),))
        self.set_status(f"预览完成：{len(self.idx)} 个文件", "#a60")

    def organize(self):
        if not self.idx:
            self.load_files()
        if not self.idx:
            return
        if not messagebox.askyesno("确认", f"即将按 {self.action_var.get()} 方式归类 {len(self.idx)} 个文件，继续？"):
            return
        d = Path(self.dir_var.get())
        action = self.action_var.get()
        done = 0
        self.tree.delete(*self.tree.get_children())
        for f in self.idx:
            folder, method = self._classify(f)
            if folder in ("未分类", "") and action == "move":
                folder = self.cfg.get("default_folder", "未分类")
            dest_dir = d / folder
            dest = dest_dir / f["name"]
            if dest == Path(f["path"]):
                self.tree.insert("", "end", values=(f["name"], "已在原位", method)); continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                self.tree.insert("", "end", values=(f["name"], "已存在(跳过)", method)); continue
            try:
                if action == "move":
                    Path(f["path"]).rename(dest)
                else:
                    shutil.copy2(f["path"], dest)
                self.tree.insert("", "end", values=(f["name"], folder, method))
                done += 1
            except Exception as e:
                self.tree.insert("", "end", values=(f["name"], f"失败:{e}", method))
        self.set_status(f"完成：已归类 {done} 个文件", "#2a6")
        messagebox.showinfo("完成", f"已按 {action} 方式归类 {done} 个文件。")

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
                self.tree.insert("", "end", values=(d["name"], f"相关度 {score:.2f}", d["path"]))
            self.set_status(f"检索到 {len(scores)} 个相关文件（倒排索引）", "#246" if scores else "#a60")
            return

        seen = set(); results = []
        for f in self.idx:
            blob = f["name"] + "\n" + f["text"]
            if any(t.lower() in blob.lower() for t in terms):
                key = hashlib.md5(f["text"].encode()).hexdigest()[:16]
                if key in seen: continue
                seen.add(key); results.append(f)
        self.tree.delete(*self.tree.get_children())
        for f in results[:50]:
            self.tree.insert("", "end", values=(f["name"], "相关", f["path"]))
        self.set_status(f"检索到 {len(results)} 个相关文件", "#246" if results else "#a60")

    def _open_file(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if len(vals) >= 3 and vals[2] and vals[2] not in ("—", ""):
            import subprocess
            subprocess.Popen(["open", vals[2]])


if __name__ == "__main__":
    app = App()
    # 支持 --demo 参数：自动加载演示目录并预览（用于截图/演示）
    if "--demo" in sys.argv:
        demo_dir = "/tmp/mcp_demo"
        if os.path.isdir(demo_dir):
            app.dir_var.set(demo_dir)
            app.config_var.set(os.path.join(demo_dir, "config.json"))
            app.after(300, app.load_files)
            app.after(600, app.preview)
    app.mainloop()
