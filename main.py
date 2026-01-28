import json
import sys
from datetime import date
from typing import List

from PyQt6.QtWidgets import QApplication

from display_ui import DisplayWindow, Task
from editor_ui import EditorWindow
from storage import get_archive_dir


class AppController:
    def __init__(self, app: QApplication):
        self.app = app

        # 关键：不要让 Qt “最后一个窗口关闭就退出”自动干预
        self.app.setQuitOnLastWindowClosed(False)

        self.display_open = False
        self.editor_open = False

        initial_tasks = _load_today_tasks() or [
            Task("今日任务待编辑，请点击上方去编辑按钮", done=False, pinned=True),
        ]

        self.display = DisplayWindow(
            tasks=initial_tasks,
            on_closed=self._on_display_closed,
        )

        self.editor = EditorWindow(
            publish_callback=self.publish_to_display,
            on_closed=self._on_editor_closed,
            initial_tasks=initial_tasks,
        )

        self.display.set_open_editor_callback(self.open_editor)

        # 默认启动只显示展示页（收起状态）
        self.display.show()
        self.display_open = True

    def open_editor(self) -> None:
        if not self.editor.isVisible():
            self.editor.show()
            self.editor_open = True
        self.editor.raise_()
        self.editor.activateWindow()

    def open_display(self) -> None:
        if not self.display.isVisible():
            self.display.show()
            self.display_open = True
        self.display.raise_()
        self.display.activateWindow()

    def publish_to_display(self, new_tasks: List[Task]) -> None:
        # 发布时检测：展示页若关闭则重新开启
        self.open_display()
        self.display.apply_tasks(new_tasks)

    def _on_display_closed(self) -> None:
        self.display_open = False
        self._maybe_quit()

    def _on_editor_closed(self) -> None:
        self.editor_open = False
        self._maybe_quit()

    def _maybe_quit(self) -> None:
        # 两个都关闭，才退出应用
        if not self.display_open and not self.editor_open:
            self.app.quit()


def main() -> None:
    app = QApplication(sys.argv)
    _ = AppController(app)
    sys.exit(app.exec())


def _load_today_tasks() -> List[Task]:
    archive_path = get_archive_dir() / f"{date.today().isoformat()}.json"
    if not archive_path.exists():
        return []
    try:
        raw = json.loads(archive_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    tasks: List[Task] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        done = item.get("done", False)
        pinned = item.get("pinned", False)
        if isinstance(text, str):
            tasks.append(Task(text=text, done=bool(done), pinned=bool(pinned)))
    return tasks


if __name__ == "__main__":
    main()
