"""书架：按可见分组分节展示卡片网格，支持右键移至分组与分组管理。"""

from __future__ import annotations

from collections import defaultdict
from functools import partial
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from comic_viewer.domain.models import ComicEntry
from comic_viewer.persistence.protocols import ComicCatalog, ProgressRepository, ShelfGroupStore
from comic_viewer.ui.groups_dialog import GroupManagerDialog

SHELF_ICON_W = 140
SHELF_ICON_H = 196

_GRID_STYLE = """
    QListWidget {
        background: transparent;
        border: none;
        outline: none;
    }
    QListWidget::item {
        background: #2a2a2e;
        border-radius: 10px;
        padding: 8px;
        color: #e8e8e8;
    }
    QListWidget::item:hover {
        background: #35353c;
    }
    QListWidget::item:selected {
        background: #2d4a6e;
    }
"""

_GROUPBOX_STYLE = """
    QGroupBox {
        font-size: 15px;
        font-weight: bold;
        color: #80d8ff;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 10px;
        margin-top: 16px;
        padding: 8px 4px 10px 4px;
        background-color: rgba(30, 30, 32, 0.55);
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 8px;
        background-color: transparent;
    }
"""


class ShelfGridWidget(QWidget):
    """分组书架；依赖 `ShelfGroupStore` 决定分节与显隐。"""

    comicClicked = Signal(ComicEntry)

    def __init__(
        self,
        shelf_root: Path,
        progress: ProgressRepository,
        catalog: ComicCatalog,
        shelf_groups: ShelfGroupStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._shelf_root = shelf_root
        self._progress = progress
        self._catalog = catalog
        self._shelf_groups = shelf_groups

        top = QHBoxLayout()
        self._path_label = QLabel()
        self._path_label.setStyleSheet("color: #888; font-size: 12px;")
        self._groups_btn = QPushButton("分组管理")
        self._groups_btn.clicked.connect(self._open_group_manager)
        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.clicked.connect(self.refresh)
        top.addWidget(self._path_label, 1)
        top.addWidget(self._groups_btn)
        top.addWidget(self._refresh_btn)
        top.setContentsMargins(10, 8, 10, 6)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._scroll_inner = QWidget()
        self._scroll_inner.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self._sections_layout = QVBoxLayout(self._scroll_inner)
        self._sections_layout.setContentsMargins(10, 4, 10, 8)
        self._sections_layout.setSpacing(0)
        self._scroll.setWidget(self._scroll_inner)
        self._scroll.viewport().installEventFilter(self)

        self._empty_hint = QLabel(
            "未找到漫画。\n请在子文件夹中放置 JSON（书名、id、描述、标签）与封面图，"
            "话数放在更深一层的子文件夹中。"
        )
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setStyleSheet("color: #888; padding: 48px;")
        self._empty_hint.hide()

        self._hidden_hint = QLabel(
            "当前没有可显示的分组内容。\n"
            "若漫画都在已隐藏的分组中，请点击「分组管理」勾选「显示」。"
        )
        self._hidden_hint.setWordWrap(True)
        self._hidden_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hidden_hint.setStyleSheet("color: #a98; padding: 36px;")
        self._hidden_hint.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(top)
        root.addWidget(self._scroll, 1)
        root.addWidget(self._empty_hint, 1)
        root.addWidget(self._hidden_hint, 1)

        self._path_label.setText(str(self._shelf_root.resolve()))
        self.refresh()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._ensure_shelf_fills_viewport()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._ensure_shelf_fills_viewport()

    def _content_height_hint(self) -> int:
        lay = self._sections_layout
        m = lay.contentsMargins()
        h = m.top() + m.bottom()
        n = lay.count()
        for i in range(n):
            it = lay.itemAt(i)
            if it is None:
                continue
            if it.spacerItem() is not None:
                continue
            w = it.widget()
            if w is not None:
                hint = w.sizeHint().height()
                if hint <= 0 and w.height() > 0:
                    hint = w.height()
                h += hint
                if i < n - 1:
                    h += lay.spacing()
        return max(h, 1)

    def _ensure_shelf_fills_viewport(self) -> None:
        if not self._scroll.isVisible():
            return
        vp = self._scroll.viewport()
        vh = vp.height()
        if vh <= 0:
            return
        ch = self._content_height_hint()
        self._scroll_inner.setMinimumHeight(max(vh, ch))

    def _clear_sections(self) -> None:
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _new_grid_list(self) -> QListWidget:
        grid = QListWidget()
        grid.setViewMode(QListWidget.ViewMode.IconMode)
        grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        grid.setMovement(QListWidget.Movement.Static)
        grid.setSpacing(16)
        grid.setUniformItemSizes(True)
        grid.setIconSize(QSize(SHELF_ICON_W, SHELF_ICON_H))
        grid.setGridSize(QSize(172, 288))
        grid.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        grid.setStyleSheet(_GRID_STYLE)
        grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        grid.customContextMenuRequested.connect(self._on_grid_context_menu)
        grid.itemClicked.connect(self._on_item_clicked)
        return grid

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        e = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(e, ComicEntry):
            self.comicClicked.emit(e)

    def _on_grid_context_menu(self, pos) -> None:
        lw = self.sender()
        if not isinstance(lw, QListWidget):
            return
        item = lw.itemAt(pos)
        if item is None:
            return
        e = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(e, ComicEntry):
            return
        menu = QMenu(self)
        move = menu.addMenu("移至分组")
        self._shelf_groups.load()
        for g in self._shelf_groups.groups_ordered():
            act = move.addAction(g.name)
            act.triggered.connect(
                partial(self._assign_and_refresh, e.progress_key(), g.id)
            )
        menu.exec(lw.mapToGlobal(pos))

    def _assign_and_refresh(self, comic_key: str, group_id: str) -> None:
        self._shelf_groups.assign_comic(comic_key, group_id)
        self.refresh()

    def _open_group_manager(self) -> None:
        dlg = GroupManagerDialog(self._shelf_groups, self, on_applied=self.refresh)
        dlg.exec()

    def _add_items_to_grid(self, grid: QListWidget, entries: list[ComicEntry]) -> None:
        icon_sz = QSize(SHELF_ICON_W, SHELF_ICON_H)
        for e in entries:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, e)
            lines = [e.title]
            p = self._progress.get(e.progress_key())
            if p and e.chapters:
                ch = min(p.chapter_index + 1, len(e.chapters))
                lines.append(f"第 {ch}/{len(e.chapters)} 话")
            it.setText("\n".join(lines))
            desc = e.description or ""
            it.setToolTip(f"{e.title}\n{desc[:200]}{'…' if len(desc) > 200 else ''}")
            pm = QPixmap()
            if e.cover_path and e.cover_path.is_file():
                pm = QPixmap(str(e.cover_path))
            if pm.isNull():
                pm = QPixmap(icon_sz)
                pm.fill(Qt.GlobalColor.darkGray)
            it.setIcon(
                QIcon(
                    pm.scaled(
                        icon_sz,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            )
            grid.addItem(it)

    def refresh(self) -> None:
        self._progress.load()
        self._shelf_groups.load()
        entries = self._catalog.discover(self._shelf_root)
        self._clear_sections()
        self._hidden_hint.hide()
        self._empty_hint.hide()

        if not entries:
            self._scroll.hide()
            self._empty_hint.show()
            return

        by_group: dict[str, list[ComicEntry]] = defaultdict(list)
        for e in entries:
            gid = self._shelf_groups.comic_group_id(e.progress_key())
            by_group[gid].append(e)

        any_section = False
        for g in self._shelf_groups.visible_groups_ordered():
            comics = by_group.get(g.id, [])
            if not comics:
                continue
            any_section = True
            box = QGroupBox(g.name)
            box.setStyleSheet(_GROUPBOX_STYLE)
            box.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
            inner = QVBoxLayout(box)
            inner.setContentsMargins(10, 12, 10, 6)
            inner.setSpacing(0)
            grid = self._new_grid_list()
            self._add_items_to_grid(grid, comics)
            inner.addWidget(grid)
            self._sections_layout.addWidget(box)

        if any_section:
            self._scroll.show()
            self._ensure_shelf_fills_viewport()
            QTimer.singleShot(0, self._ensure_shelf_fills_viewport)
        else:
            self._scroll.hide()
            self._hidden_hint.show()
