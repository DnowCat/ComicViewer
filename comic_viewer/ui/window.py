"""主窗口：组合导航栈与阅读壳，依赖注入仓库与目录服务（开闭原则）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from comic_viewer.domain.models import ComicEntry
from comic_viewer.persistence.progress_json import JsonFileProgressRepository
from comic_viewer.persistence.shelf_groups_json import JsonShelfGroupRepository
from comic_viewer.persistence.protocols import ComicCatalog, ProgressRepository, ShelfGroupStore
from comic_viewer.services.catalog import FilesystemComicCatalog
from comic_viewer.ui.detail import ComicDetailWidget
from comic_viewer.ui.reader import ReaderShell
from comic_viewer.ui.shelf import ShelfGridWidget

PAGE_SHELF = 0
PAGE_DETAIL = 1
PAGE_READER = 2


class MainWindow(QMainWindow):
    def __init__(
        self,
        shelf_root: Path,
        *,
        progress: ProgressRepository | None = None,
        catalog: ComicCatalog | None = None,
        shelf_groups: ShelfGroupStore | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("条漫阅读器 · 书架")
        self.resize(900, 640)

        self._shelf_root = shelf_root.expanduser().resolve()
        self._progress: ProgressRepository = progress or JsonFileProgressRepository(
            self._shelf_root
        )
        self._catalog: ComicCatalog = catalog or FilesystemComicCatalog()
        self._shelf_groups: ShelfGroupStore = shelf_groups or JsonShelfGroupRepository(
            self._shelf_root
        )
        self._progress.load()
        self._shelf_groups.load()

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._shelf_page = ShelfGridWidget(
            self._shelf_root,
            self._progress,
            self._catalog,
            self._shelf_groups,
        )
        self._shelf_page.comicClicked.connect(self._open_comic_detail)
        self._stack.addWidget(self._shelf_page)

        self._detail_page = ComicDetailWidget(self._progress)
        self._detail_page.backRequested.connect(self._show_shelf)
        self._detail_page.chapterRequested.connect(self._on_detail_chapter)
        self._detail_page.continueRequested.connect(self._on_detail_continue)
        self._stack.addWidget(self._detail_page)

        self._reader_wrap = QWidget()
        rl = QVBoxLayout(self._reader_wrap)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        bar = QHBoxLayout()
        self._back_btn = QPushButton("← 返回详情")
        self._back_btn.clicked.connect(self._back_from_reader)
        bar.addWidget(self._back_btn)
        bar.addStretch(1)
        rl.addLayout(bar)
        self._shell = ReaderShell()
        rl.addWidget(self._shell, 1)
        self._stack.addWidget(self._reader_wrap)

        self._current_entry: ComicEntry | None = None
        self._root = self._shelf_root
        self._chapters: list[Path] = []
        self._chapter_index = 0
        self._pending_restore_scroll: int | None = None
        self._pending_restore_image: int = 1

        self._shell.chapterActivated.connect(self._on_pick_chapter)
        self._shell.loader().chapterEndReached.connect(self._on_chapter_end)
        self._shell.loader().chapterStartReached.connect(self._on_chapter_start)
        self._shell.loader().readingPositionChanged.connect(self._sync_status)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self._flush_progress)

        self.setStyleSheet("QMainWindow { background-color: #1a1a1a; color: #e8e8e8; }")

        ctx = Qt.ShortcutContext.ApplicationShortcut
        ld = self._shell.loader()
        for key, fn in (
            (Qt.Key.Key_Up, lambda: ld.scroll_by_step(-1)),
            (Qt.Key.Key_Down, lambda: ld.scroll_by_step(1)),
            (Qt.Key.Key_PageUp, lambda: ld.scroll_by_page(-1)),
            (Qt.Key.Key_PageDown, lambda: ld.scroll_by_page(1)),
            (Qt.Key.Key_Space, lambda: ld.scroll_by_page(1)),
            (Qt.Key.Key_Home, ld.scroll_to_top),
            (Qt.Key.Key_End, ld.scroll_to_bottom),
        ):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(ctx)
            s.activated.connect(fn)

        self._stack.setCurrentIndex(PAGE_SHELF)
        self.statusBar().showMessage(f"书架：{self._shelf_root}")

    def _show_shelf(self) -> None:
        self._flush_progress()
        self._stack.setCurrentIndex(PAGE_SHELF)
        self._shelf_page.refresh()
        self.setWindowTitle("条漫阅读器 · 书架")
        self.statusBar().showMessage(f"书架：{self._shelf_root}")

    def _open_comic_detail(self, entry: ComicEntry) -> None:
        self._flush_progress()
        self._detail_page.set_comic(entry)
        self.setWindowTitle(f"漫画 · {entry.title}")
        self._stack.setCurrentIndex(PAGE_DETAIL)
        self.statusBar().showMessage(f"{entry.title} · 共 {len(entry.chapters)} 话")

    def _on_detail_chapter(self, chapter_index: int) -> None:
        e = self._detail_page.current_entry()
        if e is None or not e.chapters:
            return
        self._enter_reader(
            e,
            restore=False,
            start_chapter_index=chapter_index,
        )

    def _on_detail_continue(self) -> None:
        e = self._detail_page.current_entry()
        if e is None or not e.chapters:
            return
        if self._progress.get(e.progress_key()) is None:
            return
        self._enter_reader(e, restore=True)

    def _back_from_reader(self) -> None:
        self._flush_progress()
        if self._current_entry is not None:
            self._detail_page.set_comic(self._current_entry)
            self.setWindowTitle(f"漫画 · {self._current_entry.title}")
            self._stack.setCurrentIndex(PAGE_DETAIL)
            self.statusBar().showMessage(
                f"{self._current_entry.title} · 共 {len(self._chapters)} 话"
            )
        else:
            self._show_shelf()

    def _enter_reader(
        self,
        entry: ComicEntry,
        *,
        restore: bool = False,
        start_chapter_index: int | None = None,
    ) -> None:
        self._current_entry = entry
        self._root = entry.root
        self._chapters = list(entry.chapters)
        self._shell.set_chapters(self._chapters)
        self.setWindowTitle(f"阅读 · {entry.title}")
        self._stack.setCurrentIndex(PAGE_READER)
        self._pending_restore_scroll = None
        self._pending_restore_image = 1
        if restore:
            p = self._progress.get(entry.progress_key())
            if p is not None and self._chapters:
                ch = max(0, min(p.chapter_index, len(self._chapters) - 1))
                self._pending_restore_scroll = p.scroll_y
                self._pending_restore_image = p.image_index_1based
                self._apply_chapter(ch, force=True, do_restore=True)
                return
        if start_chapter_index is not None and self._chapters:
            ch = max(0, min(int(start_chapter_index), len(self._chapters) - 1))
            self._apply_chapter(ch, force=True, do_restore=False)
            return
        self._apply_chapter(0, force=True, do_restore=False)

    def _schedule_save(self) -> None:
        if self._current_entry is None:
            return
        self._save_timer.start()

    def _flush_progress(self) -> None:
        self._save_timer.stop()
        if self._current_entry is None or not self._chapters:
            return
        if self._stack.currentIndex() != PAGE_READER:
            return
        key = self._current_entry.progress_key()
        ld = self._shell.loader()
        cur, _tot = ld.reading_position()
        self._progress.put(
            key,
            chapter_index=self._chapter_index,
            scroll_y=ld.viewport_scroll_y(),
            image_index_1based=cur,
        )
        self._progress.save()

    def _apply_chapter(
        self,
        index: int,
        *,
        force: bool = False,
        do_restore: bool = False,
    ) -> None:
        if not self._chapters:
            self._shell.loader().clear()
            self.statusBar().showMessage(f"未找到话数文件夹：{self._root}")
            return
        index = max(0, min(index, len(self._chapters) - 1))
        if not force and index == self._chapter_index:
            return
        self._chapter_index = index
        self._shell.set_current_chapter_row(index)
        self._shell.loader().load_folder(self._chapters[index])
        self._sync_status()
        if do_restore:
            sy = self._pending_restore_scroll
            img = self._pending_restore_image
            self._pending_restore_scroll = None
            self._pending_restore_image = 1

            def restore() -> None:
                ld = self._shell.loader()
                ld.refit()
                mx = ld.scroll_area.verticalScrollBar().maximum()
                if mx > 0:
                    if sy is not None and sy > 0:
                        ld.set_viewport_scroll_y(min(sy, mx))
                    elif img > 1:
                        ld.scroll_to_image_top(img)
                self._sync_status()
                self._flush_progress()

            QTimer.singleShot(0, restore)
            QTimer.singleShot(150, restore)
        else:
            self._flush_progress()

    def _on_pick_chapter(self, row: int) -> None:
        self._apply_chapter(row, force=True)
        self._flush_progress()

    def _on_chapter_end(self) -> None:
        if self._chapter_index + 1 < len(self._chapters):
            self._apply_chapter(self._chapter_index + 1, force=True)

    def _on_chapter_start(self) -> None:
        if self._chapter_index <= 0:
            return
        self._apply_chapter(self._chapter_index - 1, force=True)
        self._shell.loader().suppress_chapter_end_until_leave_bottom()
        QTimer.singleShot(0, self._scroll_loaded_chapter_to_bottom)
        QTimer.singleShot(120, self._scroll_loaded_chapter_to_bottom)

    def _scroll_loaded_chapter_to_bottom(self) -> None:
        ld = self._shell.loader()
        ld.refit()
        ld.scroll_to_bottom()
        ld.suppress_chapter_end_until_leave_bottom()

    def _sync_status(self, *_args) -> None:
        self._schedule_save()
        if not self._chapters:
            return
        n = len(self._chapters)
        ch_name = self._chapters[self._chapter_index].name
        cur_page, total_pages = self._shell.loader().reading_position()
        if total_pages <= 0:
            page_txt = "0 张"
        else:
            page_txt = f"第 {cur_page}/{total_pages} 张"
        title_bit = ""
        if self._current_entry:
            title_bit = f"{self._current_entry.title} · "
        self.statusBar().showMessage(
            f"{title_bit}{self._chapter_index + 1}/{n} 话 · {ch_name} · {page_txt}"
            "　靠左选话　到底下一话　回顶上一话"
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._flush_progress()
        super().closeEvent(event)
