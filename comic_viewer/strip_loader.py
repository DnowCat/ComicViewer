"""竖向条漫加载器：按视口宽度缩放，懒加载与滚动边界信号。"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
MAX_PIXMAPS_IN_MEMORY = 30

_DECODE_POOL = QThreadPool()
_DECODE_POOL.setMaxThreadCount(min(6, max(2, (os.cpu_count() or 2))))


class _StripDecodeSignals(QObject):
    imageReady = Signal(int, object, int, int, int)


class _DecodeImageRunnable(QRunnable):
    def __init__(
        self,
        index: int,
        path: Path,
        generation: int,
        target_w: int,
        load_epoch: int,
        sigs: _StripDecodeSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._index = index
        self._path = path
        self._generation = generation
        self._target_w = max(1, target_w)
        self._load_epoch = load_epoch
        self._sigs = sigs

    def run(self) -> None:
        img = QImage(str(self._path))
        if img.isNull():
            self._emit_safe(self._index, None, self._generation, self._target_w, self._load_epoch)
            return
        scaled = img.scaledToWidth(
            self._target_w,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._emit_safe(self._index, scaled, self._generation, self._target_w, self._load_epoch)

    def _emit_safe(
        self,
        index: int,
        image: QImage | None,
        generation: int,
        target_w: int,
        load_epoch: int,
    ) -> None:
        try:
            self._sigs.imageReady.emit(index, image, generation, target_w, load_epoch)
        except RuntimeError:
            pass


def list_image_files(folder: Path) -> list[Path]:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        return []
    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=lambda p: p.name.lower())


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def is_chapter_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(is_image_file(p) for p in path.iterdir())


def _chapter_sort_key(name: str) -> tuple:
    m = re.search(r"第\s*(\d+)\s*话", name)
    if m:
        return (0, int(m.group(1)), name.lower())
    m2 = re.search(r"(\d+)", name)
    if m2:
        return (1, int(m2.group(1)), name.lower())
    return (2, name.lower())


def list_chapter_dirs(comic_root: Path) -> list[Path]:
    root = comic_root.expanduser().resolve()
    if not root.is_dir():
        return []
    dirs = [p for p in root.iterdir() if is_chapter_dir(p)]
    return sorted(dirs, key=lambda p: _chapter_sort_key(p.name))


def _folder_display(p: Path) -> str:
    try:
        return str(p.resolve())
    except OSError:
        return str(p)


class _LazyChapterStrip(QWidget):
    def __init__(
        self,
        folder: Path,
        image_paths: list[Path],
        loader: "StripLoaderWidget",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._loader = loader
        self._folder = folder
        self._paths = image_paths
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)

        self._labels: list[QLabel] = []
        self._natural: list[QSize] = []
        self._heights: list[int] = []
        self._pixmaps: dict[int, QPixmap] = {}
        self._last_viewport_w = -1
        self._gen = 0
        self._inflight: set[int] = set()
        self._scroll_ref: QScrollArea | None = None

        if not image_paths:
            err = QLabel(f"目录中没有图片：\n{_folder_display(folder)}")
            err.setWordWrap(True)
            err.setAlignment(Qt.AlignmentFlag.AlignCenter)
            err.setStyleSheet("color: #aaa; padding: 24px;")
            self._layout.insertWidget(0, err)
            return

        for p in image_paths:
            r = QImageReader(str(p))
            sz = r.size()
            if not sz.isValid() or sz.width() <= 0 or sz.height() <= 0:
                sz = QSize(720, 1280)
            self._natural.append(sz)

        for i, p in enumerate(image_paths):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            lbl.setScaledContents(False)
            lbl.setStyleSheet("background-color: #222;")
            self._labels.append(lbl)
            self._layout.insertWidget(self._layout.count() - 1, lbl)

    def total_paths(self) -> int:
        return len(self._paths)

    def reading_index_at_viewport_center(self, scroll: QScrollArea) -> tuple[int, int]:
        n = len(self._paths)
        if n == 0:
            return 1, 0
        if not self._heights or len(self._heights) != n:
            return 1, n
        vp_top = int(scroll.verticalScrollBar().value())
        vp_h = max(1, scroll.viewport().height())
        mid_y = vp_top + vp_h // 2
        cum = 0
        for i, h in enumerate(self._heights):
            y0, y1 = cum, cum + h
            if y0 <= mid_y < y1:
                return i + 1, n
            cum = y1
        if mid_y >= cum:
            return n, n
        return 1, n

    def shutdown_decodes(self) -> None:
        self._gen += 1
        self._inflight.clear()

    def _rebuild_heights(self, viewport_w: int) -> None:
        if not self._paths:
            return
        self._gen += 1
        self._inflight.clear()
        w = max(1, viewport_w)
        self._heights = []
        for sz in self._natural:
            h = max(1, int(sz.height() * w / max(1, sz.width())))
            self._heights.append(h)
        for lbl, h in zip(self._labels, self._heights):
            lbl.setFixedSize(w, h)
        self.setMinimumWidth(w)
        self._last_viewport_w = w
        self._pixmaps.clear()
        for lbl in self._labels:
            lbl.clear()
            lbl.setStyleSheet("background-color: #222;")

    def apply_worker_image(
        self,
        index: int,
        image_obj: object,
        generation: int,
        target_w: int,
    ) -> None:
        self._inflight.discard(index)
        if generation != self._gen:
            return
        if target_w != self._last_viewport_w:
            return
        if index < 0 or index >= len(self._labels):
            return
        scroll = self._scroll_ref
        if scroll is None:
            return
        lo, hi = self._window_indices(scroll)
        if index < lo or index > hi:
            return
        row_w = self._last_viewport_w
        row_h = self._heights[index] if index < len(self._heights) else 1
        if image_obj is None:
            lbl = self._labels[index]
            lbl.setFixedSize(row_w, row_h)
            lbl.setText(f"无法加载：{self._paths[index].name}")
            lbl.setStyleSheet("color: #c00; padding: 8px;")
            return
        image = image_obj
        if not isinstance(image, QImage) or image.isNull():
            lbl = self._labels[index]
            lbl.setFixedSize(row_w, row_h)
            lbl.setText(f"无法加载：{self._paths[index].name}")
            lbl.setStyleSheet("color: #c00; padding: 8px;")
            return
        pm = QPixmap.fromImage(image)
        self._pixmaps[index] = pm
        lbl = self._labels[index]
        lbl.setFixedSize(row_w, row_h)
        lbl.setPixmap(pm)
        lbl.setStyleSheet("")

    def _visible_range(self, scroll: QScrollArea) -> tuple[int, int]:
        n = len(self._paths)
        if n == 0 or not self._heights:
            return 0, -1
        vp_top = scroll.verticalScrollBar().value()
        vp_bot = vp_top + scroll.viewport().height()
        cum = 0
        lo, hi = n, -1
        for i, h in enumerate(self._heights):
            y0, y1 = cum, cum + h
            if y1 > vp_top and y0 < vp_bot:
                lo = min(lo, i)
                hi = max(hi, i)
            cum = y1
        if hi < 0:
            mid = min(n - 1, max(0, vp_top // max(1, self._heights[0])))
            lo = hi = mid
        return lo, hi

    def _window_indices(self, scroll: QScrollArea) -> tuple[int, int]:
        n = len(self._paths)
        if n == 0:
            return 0, -1
        v_lo, v_hi = self._visible_range(scroll)
        margin = 6
        lo = max(0, v_lo - margin)
        hi = min(n - 1, v_hi + margin)
        if hi - lo + 1 > MAX_PIXMAPS_IN_MEMORY:
            center = (v_lo + v_hi) // 2
            half = MAX_PIXMAPS_IN_MEMORY // 2
            lo = max(0, center - half)
            hi = min(n - 1, lo + MAX_PIXMAPS_IN_MEMORY - 1)
            lo = max(0, hi - (MAX_PIXMAPS_IN_MEMORY - 1))
        return lo, hi

    def sync_pixmap_window(self, scroll: QScrollArea) -> None:
        if not self._paths or not self._labels:
            return
        self._scroll_ref = scroll
        w = max(1, scroll.viewport().width() - 4)
        if w != self._last_viewport_w:
            self._rebuild_heights(w)
        lo, hi = self._window_indices(scroll)
        if hi < lo:
            return
        keep = set(range(lo, hi + 1))
        for idx in list(self._pixmaps.keys()):
            if idx not in keep:
                del self._pixmaps[idx]
                self._labels[idx].clear()
                self._labels[idx].setStyleSheet("background-color: #222;")
        for idx in range(lo, hi + 1):
            if idx in self._pixmaps:
                lbl = self._labels[idx]
                if idx < len(self._heights):
                    lbl.setFixedSize(w, self._heights[idx])
                lbl.setPixmap(self._pixmaps[idx])
                continue
            if idx in self._inflight:
                continue
            self._inflight.add(idx)
            self._loader.enqueue_strip_decode(
                self,
                idx,
                self._paths[idx],
                self._gen,
                w,
            )

    def refit_to_scroll_viewport(self, scroll: QScrollArea) -> None:
        if not self._paths:
            return
        w = max(1, scroll.viewport().width() - 4)
        if w != self._last_viewport_w:
            self._rebuild_heights(w)
        self.sync_pixmap_window(scroll)
        self.updateGeometry()
        self.adjustSize()


class StripLoaderWidget(QWidget):
    """条漫式图像加载器（懒加载 + 每话最多 30 张图在内存）。"""

    folderChanged = Signal(object)
    imagesLoaded = Signal(int)
    loadFailed = Signal(str)
    scrollValueChanged = Signal(int)
    chapterEndReached = Signal()
    chapterStartReached = Signal()
    readingPositionChanged = Signal(int, int)

    _TOP_REARM_SCROLL_PX = 48
    _BOTTOM_LEAVE_PX = 140
    _SUPPRESS_BOTTOM_ARMOR_SEC = 1.35

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._folder: Path | None = None
        self._strip: QWidget | None = None
        self._chapter_end_emitted = False
        self._chapter_start_emitted = False
        self._can_trigger_chapter_start = False
        self._suppress_auto_chapter_end = False
        self._suppress_chapter_end_deadline = 0.0
        self._last_scroll_max = -1

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background-color: #1a1a1a; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._scroll)

        bar = self._scroll.verticalScrollBar()
        bar.valueChanged.connect(self._on_scroll_value_changed)
        bar.rangeChanged.connect(lambda *_: self._emit_reading_position())

        self._load_epoch = 0
        self._decode_bridge = _StripDecodeSignals(self)
        self._decode_bridge.imageReady.connect(
            self._on_decode_image_ready,
            Qt.ConnectionType.QueuedConnection,
        )

        self._placeholder = _LazyChapterStrip(Path(), [], self)
        self._scroll.setWidget(self._placeholder)
        self._strip = self._placeholder

    def enqueue_strip_decode(
        self,
        strip: _LazyChapterStrip,
        index: int,
        path: Path,
        generation: int,
        target_w: int,
    ) -> None:
        if self._strip is not strip:
            strip._inflight.discard(index)
            return
        _DECODE_POOL.start(
            _DecodeImageRunnable(
                index,
                path,
                generation,
                target_w,
                self._load_epoch,
                self._decode_bridge,
            )
        )

    def _on_decode_image_ready(
        self,
        index: int,
        image_obj: object,
        generation: int,
        target_w: int,
        load_epoch: int,
    ) -> None:
        if load_epoch != self._load_epoch:
            return
        s = self._strip
        if not isinstance(s, _LazyChapterStrip):
            return
        s.apply_worker_image(index, image_obj, generation, target_w)

    def suppress_chapter_end_until_leave_bottom(self) -> None:
        self._chapter_end_emitted = True
        self._suppress_auto_chapter_end = True
        self._suppress_chapter_end_deadline = time.monotonic() + self._SUPPRESS_BOTTOM_ARMOR_SEC

    @property
    def scroll_area(self) -> QScrollArea:
        return self._scroll

    @property
    def current_folder(self) -> Path | None:
        return self._folder

    def image_count(self) -> int:
        if isinstance(self._strip, _LazyChapterStrip):
            return self._strip.total_paths()
        return 0

    def reading_position(self) -> tuple[int, int]:
        if isinstance(self._strip, _LazyChapterStrip):
            return self._strip.reading_index_at_viewport_center(self._scroll)
        return 1, 0

    def _emit_reading_position(self) -> None:
        cur, tot = self.reading_position()
        self.readingPositionChanged.emit(cur, tot)

    def _on_scroll_value_changed(self, v: int) -> None:
        self.scrollValueChanged.emit(v)
        if isinstance(self._strip, _LazyChapterStrip):
            self._strip.sync_pixmap_window(self._scroll)
        bar = self._scroll.verticalScrollBar()
        mx = bar.maximum()
        prev_mx = self._last_scroll_max
        self._last_scroll_max = mx
        layout_max_changed = prev_mx >= 0 and mx != prev_mx

        if mx <= 0:
            self._chapter_start_emitted = False
            if not self._suppress_auto_chapter_end:
                self._chapter_end_emitted = False
            self._emit_reading_position()
            return
        if v > self._TOP_REARM_SCROLL_PX:
            self._can_trigger_chapter_start = True

        near_end = v >= mx - 3
        if near_end:
            if not self._chapter_end_emitted and not self._suppress_auto_chapter_end:
                self._chapter_end_emitted = True
                self.chapterEndReached.emit()
        else:
            self._chapter_end_emitted = False
            if self._suppress_auto_chapter_end:
                now = time.monotonic()
                armor_done = now >= self._suppress_chapter_end_deadline
                user_left_bottom = (not layout_max_changed) and (v < mx - self._BOTTOM_LEAVE_PX)
                if armor_done and user_left_bottom:
                    self._suppress_auto_chapter_end = False

        near_start = v <= 3 and (v + 12 < mx)
        if near_start and self._can_trigger_chapter_start:
            if not self._chapter_start_emitted:
                self._chapter_start_emitted = True
                self.chapterStartReached.emit()
        elif not near_start:
            self._chapter_start_emitted = False

        self._emit_reading_position()

    def load_folder(self, folder: Path | str) -> None:
        folder_path = Path(folder).expanduser()
        self._folder = folder_path
        self._chapter_end_emitted = False
        self._chapter_start_emitted = False
        self._can_trigger_chapter_start = False
        self._suppress_auto_chapter_end = False
        self._suppress_chapter_end_deadline = 0.0
        self._last_scroll_max = -1

        if not folder_path.exists():
            self._mount_strip(folder_path, [])
            self.folderChanged.emit(folder_path)
            self.imagesLoaded.emit(0)
            self.refit()
            self.loadFailed.emit("路径不存在")
            return

        if not folder_path.is_dir():
            self._mount_strip(folder_path, [])
            self.folderChanged.emit(folder_path)
            self.imagesLoaded.emit(0)
            self.refit()
            self.loadFailed.emit("不是文件夹")
            return

        paths = list_image_files(folder_path)
        self._mount_strip(folder_path, paths)
        self.folderChanged.emit(folder_path)
        self.imagesLoaded.emit(self.image_count())
        self.refit()

    def clear(self) -> None:
        self._folder = None
        self._chapter_end_emitted = False
        self._chapter_start_emitted = False
        self._can_trigger_chapter_start = False
        self._suppress_auto_chapter_end = False
        self._suppress_chapter_end_deadline = 0.0
        self._last_scroll_max = -1
        self._mount_strip(Path(), [])
        self.folderChanged.emit(None)
        self.imagesLoaded.emit(0)
        self.refit()

    def _mount_strip(self, folder: Path, paths: list[Path]) -> None:
        self._load_epoch += 1
        old = self._scroll.takeWidget()
        if old is not None:
            if isinstance(old, _LazyChapterStrip):
                old.shutdown_decodes()
            old.deleteLater()
        self._strip = _LazyChapterStrip(folder, paths, self)
        self._scroll.setWidget(self._strip)
        self._scroll.verticalScrollBar().setValue(0)

    def refit(self) -> None:
        if isinstance(self._strip, _LazyChapterStrip):
            self._strip.refit_to_scroll_viewport(self._scroll)
        self._emit_reading_position()

    def scroll_by_step(self, direction: int) -> None:
        bar = self._scroll.verticalScrollBar()
        step = max(80, self._scroll.viewport().height() // 8)
        bar.setValue(bar.value() + direction * step)

    def scroll_by_page(self, direction: int) -> None:
        bar = self._scroll.verticalScrollBar()
        h = max(1, self._scroll.viewport().height())
        bar.setValue(bar.value() + direction * int(h * 0.92))

    def scroll_to_top(self) -> None:
        self._scroll.verticalScrollBar().setValue(0)

    def scroll_to_bottom(self) -> None:
        self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        )

    def viewport_scroll_y(self) -> int:
        return int(self._scroll.verticalScrollBar().value())

    def set_viewport_scroll_y(self, y: int) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(max(0, min(int(y), max(0, bar.maximum()))))
        if isinstance(self._strip, _LazyChapterStrip):
            self._strip.sync_pixmap_window(self._scroll)
        self._emit_reading_position()

    def scroll_to_image_top(self, index_1based: int) -> None:
        if not isinstance(self._strip, _LazyChapterStrip):
            return
        s = self._strip
        n = s.total_paths()
        if n == 0:
            return
        self.refit()
        idx = max(1, min(int(index_1based), n)) - 1
        heights = s._heights  # noqa: SLF001
        if not heights or len(heights) != n:
            return
        y = sum(heights[:idx])
        self.set_viewport_scroll_y(y)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.refit()
        QTimer.singleShot(0, self._after_show)

    def _after_show(self) -> None:
        self.refit()
        if isinstance(self._strip, _LazyChapterStrip):
            self._strip.sync_pixmap_window(self._scroll)
        QTimer.singleShot(80, self._emit_if_short_chapter)

    def _emit_if_short_chapter(self) -> None:
        bar = self._scroll.verticalScrollBar()
        if bar.maximum() > 0 or self.image_count() <= 0:
            return
        if self._suppress_auto_chapter_end:
            return
        if self._chapter_end_emitted:
            return
        self._chapter_end_emitted = True
        self.chapterEndReached.emit()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.refit()
