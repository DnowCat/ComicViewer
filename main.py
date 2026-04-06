"""应用入口：解析参数、校验路径并启动主窗口。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from comic_viewer.config import DEFAULT_SHELF_ROOT
from comic_viewer.ui.window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("条漫阅读器")

    shelf = DEFAULT_SHELF_ROOT
    if len(sys.argv) >= 2:
        shelf = Path(sys.argv[1]).expanduser()

    if not shelf.is_dir():
        QMessageBox.warning(
            None,
            "书架路径无效",
            f"目录不存在或不是文件夹：\n{shelf}\n\n"
            "请修改 comic_viewer.config.DEFAULT_SHELF_ROOT 或传入命令行路径。",
        )
        return 1

    w = MainWindow(shelf)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
