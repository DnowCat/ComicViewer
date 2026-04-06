"""阅读器外壳：条带加载器 + 左侧热区 + 滑出话数侧栏。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comic_viewer.strip_loader import StripLoaderWidget

LEFT_HOT_PX = 42
SIDEBAR_W = 260
SIDEBAR_HIDE_MS = 480


class _LeftHotZone(QWidget):
    def __init__(self, shell: ReaderShell) -> None:
        super().__init__(shell)
        self._shell = shell
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._shell.show_chapter_sidebar()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._shell.schedule_hide_sidebar()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        QApplication.sendEvent(self._shell.loader().scroll_area.viewport(), event)


class ReaderShell(QWidget):
    """全屏加载器 + 左侧热区 + 滑出话数栏。"""

    chapterActivated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loader = StripLoaderWidget(self)
        self._sidebar = QFrame(self)
        self._sidebar.setObjectName("ChapterSidebar")
        self._sidebar.setStyleSheet(
            """
            #ChapterSidebar {
                background-color: rgba(24, 24, 26, 0.96);
                border-right: 1px solid rgba(255, 255, 255, 0.08);
            }
            QListWidget {
                background: transparent;
                color: #e8e8e8;
                border: none;
                outline: none;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 10px 14px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: #2d5a87;
            }
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 0.06);
            }
            """
        )
        self._list = QListWidget(self._sidebar)
        title = QLabel("话数", self._sidebar)
        title.setStyleSheet("color: #888; font-size: 12px; padding: 10px 14px 4px;")
        sl = QVBoxLayout(self._sidebar)
        sl.setContentsMargins(0, 0, 0, 8)
        sl.setSpacing(0)
        sl.addWidget(title)
        sl.addWidget(self._list, 1)

        self._hot = _LeftHotZone(self)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(SIDEBAR_HIDE_MS)
        self._hide_timer.timeout.connect(self._hide_sidebar_impl)

        self._list.currentRowChanged.connect(self._on_row)

        self._sb_hover = _SidebarHoverFilter(self)
        self._sidebar.installEventFilter(self._sb_hover)

        self._sidebar.hide()
        self._loader.lower()
        self._hot.raise_()
        self._sidebar.raise_()

    def loader(self) -> StripLoaderWidget:
        return self._loader

    def set_chapters(self, paths: list[Path]) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for p in paths:
            self._list.addItem(QListWidgetItem(p.name))
        self._list.blockSignals(False)

    def set_current_chapter_row(self, row: int) -> None:
        self._list.blockSignals(True)
        if 0 <= row < self._list.count():
            self._list.setCurrentRow(row)
        self._list.blockSignals(False)

    def show_chapter_sidebar(self) -> None:
        self._cancel_hide_sidebar()
        self._sidebar.show()
        self._sidebar.raise_()
        self._layout_children()

    def schedule_hide_sidebar(self) -> None:
        self._hide_timer.start()

    def _cancel_hide_sidebar(self) -> None:
        self._hide_timer.stop()

    def _hide_sidebar_impl(self) -> None:
        self._sidebar.hide()
        self._layout_children()

    def _on_row(self, row: int) -> None:
        if row >= 0:
            self.chapterActivated.emit(row)

    def enter_sidebar_area(self) -> None:
        self._cancel_hide_sidebar()

    def leave_sidebar_area(self) -> None:
        self.schedule_hide_sidebar()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._layout_children()

    def _layout_children(self) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        self._loader.setGeometry(0, 0, w, h)
        edge_w = min(LEFT_HOT_PX, w)
        self._hot.setGeometry(0, 0, edge_w, h)
        bar_w = min(SIDEBAR_W, w) if self._sidebar.isVisible() else 0
        self._sidebar.setGeometry(0, 0, bar_w, h)
        self._hot.raise_()
        if self._sidebar.isVisible():
            self._sidebar.raise_()


class _SidebarHoverFilter(QObject):
    def __init__(self, shell: ReaderShell) -> None:
        super().__init__(shell)
        self._shell = shell

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.Enter:
            self._shell.enter_sidebar_area()
        elif event.type() == QEvent.Type.Leave:
            self._shell.leave_sidebar_area()
        return False
