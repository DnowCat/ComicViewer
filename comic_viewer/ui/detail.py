"""漫画详情页：元信息展示 + 话数卡片网格。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from comic_viewer.domain.models import ComicEntry
from comic_viewer.persistence.protocols import ProgressRepository

DETAIL_BG = "#121212"
DETAIL_CARD = "#2c2c2e"
DETAIL_ACCENT = "#80d8ff"
DETAIL_PRIMARY_BTN = "#2b588b"
DETAIL_CHAPTER_MIN_COLS = 3
DETAIL_CHAPTER_MAX_COLS = 6
DETAIL_CHAPTER_CELL_MIN_W = 132


class ChapterCard(QFrame):
    """话数卡片：大号序号 + 话名。"""

    cardClicked = Signal()

    def __init__(
        self,
        display_number: int,
        chapter_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ChapterCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setMinimumHeight(104)
        self.setStyleSheet(
            f"""
            QFrame#ChapterCard {{
                background-color: {DETAIL_CARD};
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.06);
            }}
            QFrame#ChapterCard:hover {{
                background-color: #353538;
                border: 1px solid rgba(128, 216, 255, 0.28);
            }}
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 14, 10, 12)
        lay.setSpacing(6)
        num = QLabel(str(display_number))
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet(
            "color: #ffffff; font-size: 26px; font-weight: bold; border: none; "
            "background: transparent;"
        )
        name = QLabel(chapter_name)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        name.setStyleSheet(
            "color: #b0b0b0; font-size: 12px; border: none; background: transparent;"
        )
        lay.addWidget(num)
        lay.addWidget(name, 1)
        self.setToolTip(chapter_name)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.cardClicked.emit()
        super().mouseReleaseEvent(event)


class ComicDetailWidget(QWidget):
    """上区元信息，下区全宽话数网格；进度状态只读 `ProgressRepository`。"""

    backRequested = Signal()
    chapterRequested = Signal(int)
    continueRequested = Signal()

    def __init__(
        self,
        progress: ProgressRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ComicDetailRoot")
        self._progress = progress
        self._entry: ComicEntry | None = None
        self._chapter_cards: list[ChapterCard] = []

        self.setStyleSheet(
            f"""
            QWidget#ComicDetailRoot {{
                background-color: {DETAIL_BG};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(0)

        head = QHBoxLayout()
        self._back_btn = QPushButton("← 返回书架")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #1e1e1e;
                color: #e8e8e8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
                border: 1px solid rgba(255, 255, 255, 0.18);
            }
            QPushButton:pressed {
                background-color: #252525;
            }
            """
        )
        self._back_btn.clicked.connect(self.backRequested.emit)
        head.addWidget(self._back_btn)
        head.addStretch(1)
        root.addLayout(head)
        root.addSpacing(18)

        info_row = QHBoxLayout()
        info_row.setSpacing(20)

        self._cover = QLabel()
        self._cover.setFixedSize(220, 308)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setStyleSheet(
            f"background-color: {DETAIL_CARD}; border-radius: 8px; "
            "border: 1px solid rgba(255, 255, 255, 0.06);"
        )
        self._cover.setScaledContents(True)

        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            "color: #ffffff; font-size: 22px; font-weight: bold; background: transparent;"
        )

        self._id_label = QLabel()
        self._id_label.setWordWrap(True)
        self._id_label.setStyleSheet(
            "color: #888888; font-size: 12px; background: transparent;"
        )

        self._tags_label = QLabel()
        self._tags_label.setWordWrap(True)
        self._tags_label.setStyleSheet(
            "color: #a8a8a8; font-size: 13px; background: transparent;"
        )

        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self._desc_label.setStyleSheet(
            "color: #e8e8e8; font-size: 14px; line-height: 1.45; background: transparent;"
        )
        self._desc_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._continue_btn = QPushButton("继续阅读")
        self._continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue_btn.setMinimumHeight(44)
        self._continue_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._continue_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {DETAIL_PRIMARY_BTN};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3366a3;
            }}
            QPushButton:pressed {{
                background-color: #244a78;
            }}
            QPushButton:disabled {{
                background-color: #3a3a3a;
                color: #777777;
            }}
            """
        )
        self._continue_btn.clicked.connect(self.continueRequested.emit)

        right_col.addWidget(self._title)
        right_col.addWidget(self._id_label)
        right_col.addWidget(self._tags_label)
        right_col.addWidget(self._desc_label, 1)
        right_col.addWidget(self._continue_btn)

        info_row.addWidget(self._cover)
        info_row.addLayout(right_col, 1)
        root.addLayout(info_row)
        root.addSpacing(22)

        self._chapter_title = QLabel("选话阅读")
        self._chapter_title.setStyleSheet(
            f"color: {DETAIL_ACCENT}; font-size: 14px; font-weight: bold; "
            "background: transparent; margin-bottom: 4px;"
        )
        root.addWidget(self._chapter_title)
        root.addSpacing(10)

        self._chapter_inner = QWidget()
        self._chapter_inner.setStyleSheet(f"background-color: {DETAIL_BG};")
        self._chapter_grid = QGridLayout(self._chapter_inner)
        self._chapter_grid.setContentsMargins(0, 0, 0, 8)
        self._chapter_grid.setHorizontalSpacing(12)
        self._chapter_grid.setVerticalSpacing(12)

        self._ch_scroll = QScrollArea()
        self._ch_scroll.setWidgetResizable(True)
        self._ch_scroll.setWidget(self._chapter_inner)
        self._ch_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._ch_scroll.setStyleSheet(
            f"""
            QScrollArea {{ background-color: {DETAIL_BG}; border: none; }}
            QScrollArea > QWidget > QWidget {{ background-color: {DETAIL_BG}; }}
            """
        )
        root.addWidget(self._ch_scroll, 1)

    def current_entry(self) -> ComicEntry | None:
        return self._entry

    def _chapter_column_count(self) -> int:
        w = self._ch_scroll.viewport().width()
        if w < 320:
            w = max(320, self.width() - 40)
        spacing = self._chapter_grid.horizontalSpacing() or 12
        cell = DETAIL_CHAPTER_CELL_MIN_W + spacing
        cols = max(DETAIL_CHAPTER_MIN_COLS, (w + spacing) // cell)
        return min(DETAIL_CHAPTER_MAX_COLS, cols)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._entry and self._entry.chapters:
            self._relayout_chapter_grid()

    def _relayout_chapter_grid(self) -> None:
        if not self._chapter_cards:
            return
        while self._chapter_grid.count():
            self._chapter_grid.takeAt(0)
        cols = self._chapter_column_count()
        for i, card in enumerate(self._chapter_cards):
            r, c = divmod(i, cols)
            self._chapter_grid.addWidget(card, r, c)

    def set_comic(self, entry: ComicEntry) -> None:
        self._entry = entry
        self._progress.load()

        self._title.setText(entry.title)
        self._id_label.setText(
            f"id：{entry.comic_id}" if entry.comic_id else ""
        )
        self._id_label.setVisible(bool(entry.comic_id))
        tags_txt = "、".join(entry.tags) if entry.tags else "无"
        self._tags_label.setText(f"标签：{tags_txt}")
        desc = entry.description or "（无描述）"
        self._desc_label.setText(desc)

        cover_frame_ss = (
            f"background-color: {DETAIL_CARD}; border-radius: 8px; "
            "border: 1px solid rgba(255, 255, 255, 0.06);"
        )
        cover_placeholder_ss = (
            f"color: #888888; font-size: 14px; background-color: {DETAIL_CARD}; "
            "border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);"
        )
        if entry.cover_path and entry.cover_path.is_file():
            pm = QPixmap(str(entry.cover_path))
            if not pm.isNull():
                self._cover.setStyleSheet(cover_frame_ss)
                self._cover.setText("")
                self._cover.setPixmap(
                    pm.scaled(
                        self._cover.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                self._cover.clear()
                self._cover.setText("无封面")
                self._cover.setStyleSheet(cover_placeholder_ss)
        else:
            self._cover.clear()
            self._cover.setText("无封面")
            self._cover.setStyleSheet(cover_placeholder_ss)

        prog = self._progress.get(entry.progress_key())
        self._continue_btn.setEnabled(bool(entry.chapters and prog is not None))

        self._clear_chapter_buttons()
        if not entry.chapters:
            hint = QLabel("未扫描到话数文件夹（子文件夹内需有图片）")
            hint.setStyleSheet("color: #888888; font-size: 13px; background: transparent;")
            hint.setWordWrap(True)
            self._chapter_grid.addWidget(hint, 0, 0)
        else:
            cols = self._chapter_column_count()
            for i, p in enumerate(entry.chapters):
                card = ChapterCard(i + 1, p.name, self._chapter_inner)
                card.cardClicked.connect(
                    lambda idx=i: self.chapterRequested.emit(idx)
                )
                self._chapter_cards.append(card)
                r, c = divmod(i, cols)
                self._chapter_grid.addWidget(card, r, c)
            QTimer.singleShot(0, self._relayout_chapter_grid)

    def _clear_chapter_buttons(self) -> None:
        self._chapter_cards.clear()
        while self._chapter_grid.count():
            item = self._chapter_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
