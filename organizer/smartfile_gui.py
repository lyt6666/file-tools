#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smartfile_gui.py —— 智能文件归类助手（PySide6 现代界面版）

依赖：PySide6（pip install PySide6）

启动：python3 smartfile_gui.py  或双击 .app

功能：
  - 选文件夹 → 扫描文件
  - 预览每个文件会归到哪个文件夹（规则/AI/默认，颜色标记）
  - 一键生成示例分类规则 / 加载自定义 config.json
  - 开始归类（复制/移动）
  - 搜索：倒排索引 + BM25 相关度排序
  - 深色/浅色主题切换
"""

import sys
import os
import json
import shutil
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QRadioButton, QButtonGroup,
    QFrame, QSizePolicy, QSpacerItem, QComboBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QBrush

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smartfile import (
    build_index, rule_match, load_config, AI, load_index_file,
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
}

# ---- 主题配色 ---------------------------------------------------------

DARK = {
    "bg": "#121417", "panel": "#1c2026", "panel2": "#242a33", "card": "#1c2026",
    "text": "#e6e8eb", "sub": "#8a93a1", "border": "#2e3540",
    "accent": "#4f8cff", "accent_hover": "#6ba2ff", "green": "#34d399",
    "purple": "#a78bfa", "gray": "#7a8494", "input_bg": "#242a33",
    "table_alt": "#20262e",
}
LIGHT = {
    "bg": "#f5f6f8", "panel": "#ffffff", "panel2": "#f0f2f5", "card": "#ffffff",
    "text": "#1f2430", "sub": "#6b7280", "border": "#e5e7eb",
    "accent": "#2563eb", "accent_hover": "#3b82f6", "green": "#059669",
    "purple": "#7c3aed", "gray": "#9ca3af", "input_bg": "#ffffff",
    "table_alt": "#f8fafc",
}


class SmartFileApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("智能文件归类助手")
        self.resize(1000, 700)
        self.setMinimumSize(820, 560)

        self.cfg = {"categories": [], "project_hints": []}
        self.ai = None
        self.idx = []
        self.dark = True

        self._theme = DARK
        self._build_ui()
        self._apply_theme()

    # ---------- 主题 ----------
    def _apply_theme(self):
        t = self._theme
        self.setStyleSheet(f"""
            QMainWindow, QWidget#central {{ background: {t['bg']}; }}
            QWidget {{ color: {t['text']};
                       font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; }}
            QLabel {{ background: transparent; color: {t['text']}; }}
            QFrame#card {{ background: {t['card']}; border: 1px solid {t['border']};
                     border-radius: 12px; }}
            QLabel#title {{ font-size: 20px; font-weight: 700; color: {t['text']}; }}
            QLabel#subtitle {{ color: {t['sub']}; font-size: 12px; }}
            QLabel[class="fieldlabel"], QLabel#fieldlabel {{ color: {t['sub']}; font-size: 12px; font-weight: 600; }}
            QLineEdit, QComboBox {{ background: {t['input_bg']}; border: 1px solid {t['border']};
                     border-radius: 8px; padding: 8px 10px; font-size: 13px;
                     color: {t['text']}; }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {t['accent']}; }}
            QPushButton {{ background: {t['panel2']}; color: {t['text']};
                     border: 1px solid {t['border']}; border-radius: 8px;
                     padding: 8px 16px; font-size: 13px; font-weight: 500; }}
            QPushButton:hover {{ background: {t['border']}; }}
            QPushButton[class="primary"], QPushButton#primary {{ background: {t['accent']}; color: white; border: none; }}
            QPushButton[class="primary"]:hover, QPushButton#primary:hover {{ background: {t['accent_hover']}; }}
            QRadioButton {{ color: {t['text']}; font-size: 13px; spacing: 6px; background: transparent; }}
            QRadioButton::indicator {{ width: 15px; height: 15px; border-radius: 8px;
                     border: 1px solid {t['border']}; background: {t['input_bg']}; }}
            QRadioButton::indicator:checked {{ background: {t['accent']}; border: 1px solid {t['accent']}; }}
            QTableWidget {{ background: {t['card']}; border: 1px solid {t['border']};
                     border-radius: 8px; gridline-color: {t['border']};
                     font-size: 13px; color: {t['text']}; }}
            QHeaderView::section {{ background: {t['panel2']}; color: {t['sub']};
                     border: none; padding: 8px; font-size: 12px; font-weight: 600; }}
            QTableWidget::item {{ padding: 6px; }}
            QTableWidget::item:selected {{ background: {t['accent']}; color: white; }}
            QTableCornerButton::section {{ background: {t['panel2']}; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """)

    # ---------- 构建 UI ----------
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # 标题栏
        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("📁 智能文件归类助手")
        title.setObjectName("title")
        sub = QLabel("按内容自动整理 · 规则优先 + AI 兜底 · 倒排索引秒搜")
        sub.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        head.addLayout(title_box)
        head.addStretch()
        self.theme_btn = QPushButton("🌙 深色")
        self.theme_btn.setFixedWidth(90)
        self.theme_btn.clicked.connect(self.toggle_theme)
        head.addWidget(self.theme_btn)
        root.addLayout(head)

        # 目录卡片
        dir_card = self._card()
        dir_lay = dir_card.layout()
        lbl = QLabel("文件夹")
        lbl.setObjectName("fieldlabel")
        dir_lay.addWidget(lbl)
        self.dir_input = QLineEdit(str(Path.home()))
        dir_lay.addWidget(self.dir_input, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self.pick_dir)
        dir_lay.addWidget(browse)
        scan = QPushButton("扫描")
        scan.setObjectName("primary")
        scan.clicked.connect(self.load_files)
        dir_lay.addWidget(scan)
        root.addWidget(dir_card)

        # 配置卡片
        cfg_card = self._card()
        cfg_lay = cfg_card.layout()
        lbl2 = QLabel("规则配置")
        lbl2.setObjectName("fieldlabel")
        cfg_lay.addWidget(lbl2)
        self.cfg_input = QLineEdit()
        self.cfg_input.setPlaceholderText("留空则全部归入「未分类」；点右侧“生成示例”一键创建")
        cfg_lay.addWidget(self.cfg_input, 1)
        sel = QPushButton("选择…")
        sel.clicked.connect(self.pick_config)
        cfg_lay.addWidget(sel)
        gen = QPushButton("生成示例")
        gen.clicked.connect(self.gen_config)
        cfg_lay.addWidget(gen)

        # 方式单选
        self.mode_copy = QRadioButton("复制（保留原件）")
        self.mode_move = QRadioButton("移动（剪切）")
        self.mode_copy.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_copy)
        self.mode_group.addButton(self.mode_move)
        mode_box = QHBoxLayout()
        mode_box.addWidget(QLabel("处理方式："))
        mode_box.addWidget(self.mode_copy)
        mode_box.addWidget(self.mode_move)
        mode_box.addStretch()
        cfg_lay.addLayout(mode_box)
        root.addWidget(cfg_card)

        # 表格卡片
        table_card = self._card()
        table_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_lay = table_card.layout()
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["文件", "归类到", "方式"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._open_file)
        table_lay.addWidget(self.table)
        root.addWidget(table_card, 1)

        # 操作 + 搜索行
        act = QHBoxLayout()
        self.preview_btn = QPushButton("预览归类")
        self.preview_btn.clicked.connect(self.preview)
        act.addWidget(self.preview_btn)
        self.go_btn = QPushButton("开始归类")
        self.go_btn.setObjectName("primary")
        self.go_btn.clicked.connect(self.organize)
        act.addWidget(self.go_btn)
        act.addSpacing(20)
        act.addWidget(QLabel("搜索："))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词，支持多词空格分隔")
        self.search_input.returnPressed.connect(self.search)
        act.addWidget(self.search_input, 1)
        self.search_btn = QPushButton("检索")
        self.search_btn.clicked.connect(self.search)
        act.addWidget(self.search_btn)
        root.addLayout(act)

        # 状态栏
        self.status = QLabel("就绪 — 选一个文件夹后点「扫描」")
        self.status.setObjectName("subtitle")
        root.addWidget(self.status)

    def _card(self):
        f = QFrame()
        f.setObjectName("card")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)
        return f

    # ---------- 交互 ----------
    def toggle_theme(self):
        self.dark = not self.dark
        self._theme = DARK if self.dark else LIGHT
        self.theme_btn.setText("🌙 深色" if self.dark else "☀️ 浅色")
        self._apply_theme()

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹", str(Path.home()))
        if d:
            self.dir_input.setText(d)

    def pick_config(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择配置文件", "", "JSON (*.json)")
        if f:
            self.cfg_input.setText(f)
            self.load_files()

    def gen_config(self):
        d = self.dir_input.text().strip() or str(Path.home())
        target = str(Path(d) / "config.json")
        if os.path.exists(target):
            if not self._confirm(f"{target}\n已存在，覆盖为示例配置？"):
                return
        with open(target, "w", encoding="utf-8") as f:
            json.dump(EXAMPLE_CONFIG, f, ensure_ascii=False, indent=2)
        self.cfg_input.setText(target)
        self.load_files()
        self._status(f"已生成示例配置：{target}", "green")

    def load_files(self):
        d = self.dir_input.text().strip()
        if not os.path.isdir(d):
            self._warn(f"文件夹不存在：\n{d}")
            return
        cfg_path = self.cfg_input.text().strip()
        self.cfg = load_config(cfg_path) if cfg_path else {"categories": [], "project_hints": []}
        self.ai = AI(self.cfg.get("ai"))
        self.idx = build_index(d, True)
        self._fill_table(self.idx)
        self._status(f"已扫描 {len(self.idx)} 个文件（{len(self.cfg.get('categories', []))} 类规则）", "green")

    def _fill_table(self, idx):
        self.table.setRowCount(0)
        self.table.setRowCount(len(idx))
        for r, f in enumerate(idx):
            self.table.setItem(r, 0, QTableWidgetItem(f["name"]))

    def _classify(self, f):
        all_cats = self.cfg.get("categories", []) + self.cfg.get("project_hints", [])
        cat = rule_match(f["text"], all_cats)
        method = "规则"
        if cat is None and f["text"].strip():
            name = self.ai.classify(f["text"], [c["name"] for c in all_cats])
            if name:
                cat = next((c for c in all_cats if c["name"] == name), None)
                method = "AI"
        if cat is None:
            return (self.cfg.get("default_folder", "未分类"), "默认")
        return (cat.get("folder", cat["name"]), method)

    def _method_color(self, method):
        return {
            "规则": self._theme["green"],
            "AI": self._theme["purple"],
            "默认": self._theme["gray"],
        }.get(method, self._theme["text"])

    def preview(self):
        if not self.idx:
            self.load_files()
        if not self.idx:
            return
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.idx))
        for r, f in enumerate(self.idx):
            folder, method = self._classify(f)
            self.table.setItem(r, 0, QTableWidgetItem(f["name"]))
            self.table.setItem(r, 1, QTableWidgetItem(folder))
            m_item = QTableWidgetItem(method)
            m_item.setForeground(QBrush(QColor(self._method_color(method))))
            self.table.setItem(r, 2, m_item)
        self._status(f"预览完成：{len(self.idx)} 个文件", "accent")

    def organize(self):
        if not self.idx:
            self.load_files()
        if not self.idx:
            return
        action = "move" if self.mode_move.isChecked() else "copy"
        if not self._confirm(f"即将按「{('移动' if action=='move' else '复制')}」方式归类 {len(self.idx)} 个文件，继续？"):
            return
        d = Path(self.dir_input.text().strip())
        done = 0
        for f in self.idx:
            folder, _ = self._classify(f)
            dest_dir = d / folder
            dest = dest_dir / f["name"]
            if dest == Path(f["path"]):
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                continue
            try:
                if action == "move":
                    Path(f["path"]).rename(dest)
                else:
                    shutil.copy2(f["path"], dest)
                done += 1
            except Exception:
                pass
        self._status(f"完成：已归类 {done} 个文件", "green")
        QMessageBox.information(self, "完成", f"已按「{('移动' if action=='move' else '复制')}」方式归类 {done} 个文件。")

    def search(self):
        if not self.idx:
            self.load_files()
        if not self.idx:
            return
        q = self.search_input.text().strip()
        if not q:
            return
        import re, hashlib
        terms = [t for t in re.split(r"[\s,，、。|]+", q) if t]
        data = load_index_file(self.dir_input.text().strip())
        results = []  # (name, score_or_none, path)
        if data and data.get("inverted"):
            from smartfile import bm25_score, tokenize
            docs = data["docs"]
            q_terms = []
            for t in terms:
                q_terms.extend(tokenize(t))
            scores = bm25_score(q_terms, data["inverted"], data["doc_stats"], len(docs))
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:50]
            for did, score in ranked:
                d = docs[int(did)]
                results.append((d["name"], f"{score:.2f}", d["path"]))
        else:
            seen = set()
            for f in self.idx:
                blob = f["name"] + "\n" + f["text"]
                if any(t.lower() in blob.lower() for t in terms):
                    key = hashlib.md5(f["text"].encode()).hexdigest()[:16]
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append((f["name"], "相关", f["path"]))
        self.table.setRowCount(0)
        self.table.setRowCount(len(results))
        for r, (name, score, path) in enumerate(results):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(f"相关度 {score}" if score != "相关" else "相关"))
            self.table.setItem(r, 2, QTableWidgetItem(path if path else ""))
        self._status(f"检索到 {len(results)} 个相关文件", "green" if results else "accent")

    def _open_file(self, row, col):
        item = self.table.item(row, 2)
        if item and item.text() and os.path.exists(item.text()):
            subprocess.Popen(["open", item.text()])

    # ---------- 提示 ----------
    def _confirm(self, text):
        return QMessageBox.question(self, "确认", text) == QMessageBox.Yes

    def _warn(self, text):
        QMessageBox.warning(self, "提示", text)

    def _status(self, text, kind="gray"):
        self.status.setText(text)
        color = self._theme.get(kind, self._theme["sub"])
        self.status.setStyleSheet(f"color: {color};")


def main():
    app = QApplication(sys.argv)
    w = SmartFileApp()
    if "--demo" in sys.argv:
        demo_dir = "/tmp/mcp_demo"
        if os.path.isdir(demo_dir):
            w.dir_input.setText(demo_dir)
            w.cfg_input.setText(os.path.join(demo_dir, "config.json"))
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, w.load_files)
            QTimer.singleShot(600, w.preview)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
