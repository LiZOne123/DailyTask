from __future__ import annotations

from typing import Callable, List, Optional
from datetime import date
import json

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QInputDialog,
    QApplication,
    QLineEdit,
)

from display_ui import Task
from model import load_api_key, save_api_key, summarize_tasks
from storage import get_archive_dir


class EditorWindow(QWidget):
    def __init__(
        self,
        publish_callback: Callable[[List[Task]], None],
        on_closed: Optional[Callable[[], None]] = None,
        initial_tasks: Optional[List[Task]] = None,
    ):
        super().__init__()
        self.publish_callback = publish_callback
        self._on_closed = on_closed
        self._initial_tasks = initial_tasks or []

        self._dragging = False
        self._drag_pos: Optional[QPoint] = None

        self._init_window()
        self._build_ui()
        self._apply_style()
        if self._initial_tasks:
            self._load_tasks(self._initial_tasks)

    def _init_window(self) -> None:
        self.setWindowTitle("今日任务 · 编辑")
        self.resize(980, 640)

        # 让编辑页也与展示页一致：无边框 + 半透明 + 圆角容器
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

    def closeEvent(self, event) -> None:
        event.accept()
        self.hide()
        if self._on_closed:
            self._on_closed()

    def _build_ui(self) -> None:
        # 外层容器（同展示页风格）
        self.container = QWidget(self)
        self.container.setObjectName("container")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.addWidget(self.container)

        # 顶部标题栏（同展示页）
        outer = QVBoxLayout(self.container)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.lbl_title = QLabel("今日任务 · 编辑")
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        self.lbl_title.setFont(f)
        self.lbl_title.setObjectName("title")

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("btnClose")
        self.btn_close.setFixedWidth(34)
        self.btn_close.clicked.connect(self.close)

        header.addWidget(self.lbl_title, 1)
        header.addWidget(self.btn_close, 0)

        outer.addLayout(header)

        # 主体左右两栏
        body = QHBoxLayout()
        body.setSpacing(12)

        # LEFT
        left = QVBoxLayout()
        left.setSpacing(10)

        lbl_left = QLabel("原始想法")
        lbl_left.setObjectName("subtitle")
        left.addWidget(lbl_left)

        self.txt_raw = QPlainTextEdit()
        self.txt_raw.setObjectName("editor")
        self.txt_raw.setPlaceholderText("把你脑子里的“模糊目标/想法”随便写下来…")
        left.addWidget(self.txt_raw, 1)

        self.btn_ai = QPushButton("AI 总结")
        self.btn_ai.setObjectName("btnPrimary")
        self.btn_ai.clicked.connect(self._on_ai_summarize)
        left.addWidget(self.btn_ai, 0)

        self.btn_api_key = QPushButton("设置 API Key")
        self.btn_api_key.setObjectName("btn")
        self.btn_api_key.clicked.connect(self._on_set_api_key)
        left.addWidget(self.btn_api_key, 0)

        # RIGHT with Tabs
        right = QVBoxLayout()
        right.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabs")

        # Tab1 tasks
        tab_tasks = QWidget()
        tab_tasks_layout = QVBoxLayout(tab_tasks)
        tab_tasks_layout.setContentsMargins(10, 10, 10, 10)
        tab_tasks_layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_add = QPushButton("新增任务")
        self.btn_add.setObjectName("btn")
        self.btn_add.clicked.connect(self._add_task)

        self.btn_del = QPushButton("删除选中")
        self.btn_del.setObjectName("btn")
        self.btn_del.clicked.connect(self._delete_selected)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("btn")
        self.btn_clear.clicked.connect(self._clear_all)

        self.btn_publish = QPushButton("确认发布")
        self.btn_publish.setObjectName("btnPrimary")
        self.btn_publish.clicked.connect(self._publish)

        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_del)
        toolbar.addWidget(self.btn_clear)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_publish)

        self.list_tasks = QListWidget()
        self.list_tasks.setObjectName("taskList")
        self.list_tasks.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_tasks.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_tasks.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        self.list_tasks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_tasks.customContextMenuRequested.connect(self._open_task_context_menu)
        self.list_tasks.model().rowsMoved.connect(lambda *_: self._refresh_task_list_text())

        tab_tasks_layout.addLayout(toolbar)
        tab_tasks_layout.addWidget(self.list_tasks, 1)

        # Tab2 debug
        tab_debug = QWidget()
        tab_debug_layout = QVBoxLayout(tab_debug)
        tab_debug_layout.setContentsMargins(10, 10, 10, 10)

        self.txt_debug = QPlainTextEdit()
        self.txt_debug.setObjectName("debug")
        self.txt_debug.setReadOnly(True)
        tab_debug_layout.addWidget(self.txt_debug)

        self.tabs.addTab(tab_tasks, "任务列表")
        self.tabs.addTab(tab_debug, "AI 调试")

        right.addWidget(self.tabs, 1)

        body.addLayout(left, 1)
        body.addLayout(right, 2)

        outer.addLayout(body, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#container {
                background: rgb(20, 20, 20);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
            QLabel#title { color: rgba(255,255,255,235); }
            QLabel#subtitle { color: rgba(255,255,255,215); font-weight: 700; font-size: 13px; }

            QPlainTextEdit#editor, QPlainTextEdit#debug {
                background: rgba(255,255,255,10);
                border: 1px solid rgba(255,255,255,25);
                border-radius: 10px;
                padding: 10px;
                color: rgba(255,255,255,230);
                selection-background-color: rgba(80, 170, 255, 90);
            }

            QTabWidget#tabs {
                background: transparent;
            }
            QTabWidget#tabs::pane {
                border: 1px solid rgba(255,255,255,25);
                border-radius: 10px;
                background: rgba(255,255,255,6);
                top: -1px;
            }
            QTabBar {
                background: transparent;
            }
            QTabBar::tab {
                color: rgba(255,255,255,220);
                background: rgba(255,255,255,10);
                border: 1px solid rgba(255,255,255,18);
                padding: 8px 12px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                margin-right: 6px;
            }
            QTabBar::tab:selected {
                background: rgba(255,255,255,18);
                border: 1px solid rgba(255,255,255,30);
            }

            QListWidget#taskList {
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,22);
                border-radius: 10px;
                padding: 6px;
                color: rgba(255,255,255,220);
            }
            QListWidget#taskList::item {
                padding: 6px 6px;
            }

            QPushButton#btn {
                color: rgba(255,255,255,225);
                background: rgba(255,255,255,18);
                border: 1px solid rgba(255,255,255,35);
                border-radius: 10px;
                padding: 8px 12px;
            }
            QPushButton#btn:hover { background: rgba(255,255,255,32); }

            QPushButton#btnPrimary {
                color: rgba(255,255,255,235);
                background: rgba(80, 170, 255, 95);
                border: 1px solid rgba(255,255,255,45);
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 900;
            }
            QPushButton#btnPrimary:hover { background: rgba(80, 170, 255, 135); }

            QPushButton#btnClose {
                color: rgba(255,255,255,235);
                background: rgba(255,60,60,80);
                border: 1px solid rgba(255,255,255,35);
                border-radius: 10px;
                padding: 4px 0px;
                font-weight: 900;
            }
            QPushButton#btnClose:hover { background: rgba(255,60,60,120); }
            """
        )

    def _dialog_stylesheet(self) -> str:
        return (
            """
            QDialog {
                background: white;
                color: black;
            }
            QLabel {
                color: black;
            }
            QLineEdit, QPlainTextEdit, QTextEdit {
                background: #f2f2f2;
                color: black;
                border: 1px solid #1a1a1a;
                border-radius: 8px;
                padding: 6px;
            }
            QPushButton {
                background: #f7f7f7;
                color: black;
                border: 1px solid #1a1a1a;
                border-radius: 8px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: #e6e6e6;
            }
            """
        )

    def _show_message(self, title: str, text: str, icon: QMessageBox.Icon) -> None:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStyleSheet(self._dialog_stylesheet())
        box.exec()

    def _show_info(self, title: str, text: str) -> None:
        self._show_message(title, text, QMessageBox.Icon.Information)

    def _show_warning(self, title: str, text: str) -> None:
        self._show_message(title, text, QMessageBox.Icon.Warning)

    def _prompt_api_key(self, current: str) -> Optional[str]:
        dialog = QInputDialog(self)
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
        dialog.setWindowTitle("设置 API Key")
        dialog.setLabelText("请输入 SiliconFlow API Key：")
        dialog.setTextValue(current)
        dialog.setStyleSheet(self._dialog_stylesheet())
        if dialog.exec():
            return dialog.textValue()
        return None

    # -------------------------
    # (下面保留你原来的逻辑：假 AI、任务增删、右键菜单、发布弹窗等)
    # -------------------------
    def _on_ai_summarize(self) -> None:
        raw = self.txt_raw.toPlainText().strip()
        if not raw:
            self._show_info("提示", "请先在左侧输入一些想法，再进行 AI 总结。")
            return

        api_key = load_api_key()
        if not api_key:
            self._show_warning("需要 API Key", "请先点击“设置 API Key”输入并保存你的密钥。")
            return

        self.btn_ai.setEnabled(False)
        progress = QProgressDialog("AI 总结中，请稍候…", None, 0, 0, self)
        progress.setWindowTitle("AI 总结")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setStyleSheet(self._dialog_stylesheet())
        progress.show()
        QApplication.processEvents()

        try:
            payloads, raw_json = summarize_tasks(raw, api_key)
            tasks = [Task(text=p.text, done=p.done, pinned=p.pinned) for p in payloads]
            self._load_tasks(tasks)
            self.txt_debug.setPlainText(
                "【AI 调试】\n"
                "输入（raw_input）：\n"
                f"{raw}\n\n"
                "输出（raw_json）：\n"
                f"{raw_json}"
            )
            self.tabs.setCurrentIndex(0)
        except Exception as exc:
            self._show_warning("AI 总结失败", f"模型返回或解析失败：{exc}")
        finally:
            progress.close()
            self.btn_ai.setEnabled(True)

    def _on_set_api_key(self) -> None:
        current = load_api_key() or ""
        api_key = self._prompt_api_key(current)
        if api_key is None:
            return
        key = api_key.strip()
        if not key:
            self._show_warning("无效 API Key", "API Key 不能为空。")
            return
        save_api_key(key)
        self._show_info("已保存", "API Key 已保存到本地。")

    def _load_tasks(self, tasks: List[Task]) -> None:
        self.list_tasks.clear()
        for t in tasks:
            self._add_task_item(t.text, t.done, t.pinned)
        self._refresh_task_list_text()

    def _add_task_item(self, text: str, done: bool = False, pinned: bool = False) -> None:
        item = QListWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(Qt.ItemDataRole.UserRole, {"done": done, "pinned": pinned})
        f = item.font()
        f.setPointSize(13)
        f.setBold(not done)
        item.setFont(f)
        self.list_tasks.addItem(item)

    def _collect_tasks(self) -> List[Task]:
        out: List[Task] = []
        for r in range(self.list_tasks.count()):
            it = self.list_tasks.item(r)
            meta = it.data(Qt.ItemDataRole.UserRole) or {}
            out.append(Task(text=(it.text() or "").strip(),
                            done=bool(meta.get("done", False)),
                            pinned=bool(meta.get("pinned", False))))
        return out

    def _refresh_task_list_text(self) -> None:
        for r in range(self.list_tasks.count()):
            it = self.list_tasks.item(r)
            meta = it.data(Qt.ItemDataRole.UserRole) or {}
            done = bool(meta.get("done", False))
            f = it.font()
            f.setPointSize(13)
            f.setBold(not done)
            it.setFont(f)

    def _add_task(self) -> None:
        self._add_task_item("新任务", done=False, pinned=False)
        self.list_tasks.setCurrentRow(self.list_tasks.count() - 1)
        self.list_tasks.editItem(self.list_tasks.currentItem())

    def _delete_selected(self) -> None:
        row = self.list_tasks.currentRow()
        if row >= 0:
            self.list_tasks.takeItem(row)

    def _clear_all(self) -> None:
        self.list_tasks.clear()

    def _open_task_context_menu(self, pos) -> None:
        item = self.list_tasks.itemAt(pos)
        if item is None:
            return
        meta = item.data(Qt.ItemDataRole.UserRole) or {}
        done = bool(meta.get("done", False))
        pinned = bool(meta.get("pinned", False))

        menu = QMenu(self)
        act_done = QAction("取消完成" if done else "确认完成", self)
        act_pin = QAction("取消置顶" if pinned else "置顶", self)
        act_done.triggered.connect(lambda: self._toggle_done(item))
        act_pin.triggered.connect(lambda: self._toggle_pin(item))
        menu.addAction(act_done)
        menu.addAction(act_pin)
        menu.exec(self.list_tasks.mapToGlobal(pos))

    def _toggle_done(self, item: QListWidgetItem) -> None:
        meta = item.data(Qt.ItemDataRole.UserRole) or {}
        meta["done"] = not bool(meta.get("done", False))
        item.setData(Qt.ItemDataRole.UserRole, meta)
        self._refresh_task_list_text()

    def _toggle_pin(self, item: QListWidgetItem) -> None:
        meta = item.data(Qt.ItemDataRole.UserRole) or {}
        meta["pinned"] = not bool(meta.get("pinned", False))
        item.setData(Qt.ItemDataRole.UserRole, meta)

    def _publish(self) -> None:
        tasks = self._collect_tasks()
        if not tasks:
            QMessageBox.information(self, "提示", "任务列表为空，无法发布。")
            return
        self.publish_callback(tasks)
        self._archive_tasks(tasks)
        QMessageBox.information(self, "已发布", "任务已发布到悬浮窗，并已刷新显示。")

    def _archive_tasks(self, tasks: List[Task]) -> None:
        filename = f"{date.today().isoformat()}.json"
        payload = [{"text": t.text, "done": t.done, "pinned": t.pinned} for t in tasks]
        (get_archive_dir() / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # 可选：编辑页也支持拖动窗口（和展示窗一致）
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_pos = None
            event.accept()
