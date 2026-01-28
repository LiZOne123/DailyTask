from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import List, Optional, Callable

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
)


@dataclass
class Task:
    text: str
    done: bool = False
    pinned: bool = False


class DisplayWindow(QWidget):
    def __init__(self, tasks: Optional[List[Task]] = None, on_closed: Optional[Callable[[], None]] = None):
        super().__init__()
        self.tasks: List[Task] = tasks[:] if tasks else []
        self._on_closed = on_closed

        self._dragging = False
        self._drag_pos: Optional[QPoint] = None

        self._collapsed = True
        self._topmost = True
        self._open_editor_callback: Optional[Callable[[], None]] = None

        self._init_window()
        self._build_ui()
        self._apply_collapsed(self._collapsed)
        self._refresh_all()

    def closeEvent(self, event) -> None:
        # 关闭=隐藏（不销毁对象，便于再次 show）
        event.accept()
        self.hide()
        if self._on_closed:
            self._on_closed()

    # -------------------------
    # public API
    # -------------------------
    def apply_tasks(self, tasks: List[Task]) -> None:
        # 覆盖并立刻刷新
        self.tasks = [Task(t.text, t.done, t.pinned) for t in tasks]
        self._refresh_all()
        # 如果置顶打开，顺手把窗口抬上来（让你感知到“已发布生效”）
        self.raise_()

    def set_open_editor_callback(self, cb: Callable[[], None]) -> None:
        self._open_editor_callback = cb

    # -------------------------
    # Window
    # -------------------------
    def _init_window(self) -> None:
        self.setWindowTitle("今日任务 · 展示")

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self.setWindowOpacity(0.90)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.resize(560, 150)
        self.move(40, 40)

    def _apply_topmost(self, enabled: bool) -> None:
        self._topmost = enabled
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()
        self.raise_()
        self.activateWindow()

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self) -> None:
        self.container = QWidget(self)
        self.container.setObjectName("container")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # header row
        header = QHBoxLayout()
        header.setSpacing(8)

        self.lbl_title = QLabel("今日任务")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.lbl_title.setFont(title_font)
        self.lbl_title.setObjectName("title")

        self.btn_edit = QPushButton("去编辑")
        self.btn_edit.setObjectName("btn")
        self.btn_edit.clicked.connect(self._open_editor)

        self.btn_topmost = QPushButton("置顶：开")
        self.btn_topmost.setObjectName("btn")
        self.btn_topmost.clicked.connect(self._toggle_topmost)

        self.btn_expand = QPushButton("展开")
        self.btn_expand.setObjectName("btn")
        self.btn_expand.clicked.connect(self._toggle_collapsed)

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("btnClose")
        self.btn_close.setFixedWidth(34)
        self.btn_close.clicked.connect(self.close)

        header.addWidget(self.lbl_title, 1)
        header.addWidget(self.btn_edit, 0)
        header.addWidget(self.btn_topmost, 0)
        header.addWidget(self.btn_expand, 0)
        header.addWidget(self.btn_close, 0)

        # collapsed row: current task + complete button
        self.row_collapsed = QWidget()
        row = QHBoxLayout(self.row_collapsed)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.lbl_current = QLabel("")
        current_font = QFont()
        current_font.setPointSize(13)
        current_font.setBold(True)
        self.lbl_current.setFont(current_font)
        self.lbl_current.setObjectName("current")
        self.lbl_current.setWordWrap(False)

        self.btn_complete_current = QPushButton("完成")
        self.btn_complete_current.setObjectName("btnPrimary")
        self.btn_complete_current.clicked.connect(self._complete_current_task)

        row.addWidget(self.lbl_current, 1)
        row.addWidget(self.btn_complete_current, 0)

        # expanded list
        self.list_tasks = QListWidget()
        self.list_tasks.setObjectName("taskList")
        self.list_tasks.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_tasks.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.list_tasks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_tasks.customContextMenuRequested.connect(self._open_task_context_menu)

        # sync order after drag
        self.list_tasks.model().rowsMoved.connect(lambda *_: self._sync_order_from_list())

        layout.addLayout(header)
        layout.addWidget(self.row_collapsed)
        layout.addWidget(self.list_tasks)

        self.setStyleSheet(
            """
            QWidget#container {
                background: rgba(20, 20, 20, 195);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
            QLabel#title { color: rgba(255,255,255,235); }
            QLabel#current { color: rgba(255,255,255,225); }

            QListWidget#taskList {
                background: rgba(255,255,255,10);
                border: 1px solid rgba(255,255,255,25);
                border-radius: 10px;
                color: rgba(255,255,255,220);
                padding: 6px;
                font-size: 13px;
            }

            QPushButton#btn {
                color: rgba(255,255,255,225);
                background: rgba(255,255,255,22);
                border: 1px solid rgba(255,255,255,40);
                border-radius: 10px;
                padding: 6px 10px;
            }
            QPushButton#btn:hover { background: rgba(255,255,255,38); }

            QPushButton#btnPrimary {
                color: rgba(255,255,255,235);
                background: rgba(80, 170, 255, 90);
                border: 1px solid rgba(255,255,255,45);
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 800;
            }
            QPushButton#btnPrimary:hover { background: rgba(80, 170, 255, 130); }

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

        self.row_collapsed.setFixedHeight(self.row_collapsed.sizeHint().height())

    # -------------------------
    # interactions
    # -------------------------
    def _open_editor(self) -> None:
        if self._open_editor_callback:
            self._open_editor_callback()

    def _toggle_topmost(self) -> None:
        self._apply_topmost(not self._topmost)
        self.btn_topmost.setText("置顶：开" if self._topmost else "置顶：关")

    def _toggle_collapsed(self) -> None:
        self._apply_collapsed(not self._collapsed)

    def _apply_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.row_collapsed.setVisible(collapsed)
        self.list_tasks.setVisible(not collapsed)
        self.btn_expand.setText("展开" if collapsed else "收起")

        self.resize(self.width(), 150 if collapsed else 340)

    # -------------------------
    # task logic
    # -------------------------
    def _current_task_index(self) -> Optional[int]:
        for i, t in enumerate(self.tasks):
            if t.pinned and not t.done:
                return i
        for i, t in enumerate(self.tasks):
            if not t.done:
                return i
        return None

    def _sorted_indices_for_display(self) -> List[int]:
        pinned = [i for i, t in enumerate(self.tasks) if t.pinned]
        others = [i for i, t in enumerate(self.tasks) if not t.pinned]
        return pinned + others

    def _refresh_all(self) -> None:
        self._refresh_collapsed_row()
        self._refresh_task_list()

    def _refresh_collapsed_row(self) -> None:
        idx = self._current_task_index()
        if idx is None:
            self.lbl_current.setText("今日已完成✅")
            self.btn_complete_current.setEnabled(False)
            return
        t = self.tasks[idx]
        prefix = "📌 " if t.pinned else ""
        self.lbl_current.setText(f"{prefix}{t.text}")
        self.btn_complete_current.setEnabled(True)

    def _complete_current_task(self) -> None:
        idx = self._current_task_index()
        if idx is None:
            return
        self.tasks[idx].done = True
        self._archive_tasks()
        self._refresh_all()

    def _refresh_task_list(self) -> None:
        self.list_tasks.blockSignals(True)
        self.list_tasks.clear()

        for i in self._sorted_indices_for_display():
            t = self.tasks[i]
            status = "✅" if t.done else "⬜"
            pin = "📌" if t.pinned else ""
            text = f"{status} {pin} {t.text}".strip()

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, i)

            f = item.font()
            f.setPointSize(13)
            f.setBold(not t.done)
            item.setFont(f)

            self.list_tasks.addItem(item)

        self.list_tasks.blockSignals(False)

    # context menu
    def _open_task_context_menu(self, pos) -> None:
        item = self.list_tasks.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return

        t = self.tasks[idx]
        menu = QMenu(self)

        act_done = QAction("取消完成" if t.done else "确认完成", self)
        act_pin = QAction("取消置顶" if t.pinned else "置顶", self)

        act_done.triggered.connect(lambda: self._toggle_done(idx))
        act_pin.triggered.connect(lambda: self._toggle_pin(idx))

        menu.addAction(act_done)
        menu.addAction(act_pin)
        menu.exec(self.list_tasks.mapToGlobal(pos))

    def _toggle_done(self, idx: int) -> None:
        self.tasks[idx].done = not self.tasks[idx].done
        self._archive_tasks()
        self._refresh_all()

    def _toggle_pin(self, idx: int) -> None:
        self.tasks[idx].pinned = not self.tasks[idx].pinned
        self._archive_tasks()
        self._refresh_all()

    # drag sync
    def _sync_order_from_list(self) -> None:
        new_order: List[int] = []
        for r in range(self.list_tasks.count()):
            it = self.list_tasks.item(r)
            idx = it.data(Qt.ItemDataRole.UserRole)
            if idx is not None:
                new_order.append(idx)

        self.tasks = [self.tasks[i] for i in new_order]
        self._archive_tasks()
        self._refresh_all()

    def _archive_tasks(self) -> None:
        archive_dir = Path(__file__).resolve().parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{date.today().isoformat()}.json"
        payload = [{"text": t.text, "done": t.done, "pinned": t.pinned} for t in self.tasks]
        (archive_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # -------------------------
    # drag window
    # -------------------------
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
