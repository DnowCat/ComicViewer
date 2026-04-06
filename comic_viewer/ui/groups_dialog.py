"""分组管理：添加、删除、显隐、重命名。"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QCheckBox,
    QVBoxLayout,
    QWidget,
)

from comic_viewer.domain.models import ShelfGroup
from comic_viewer.persistence.protocols import ShelfGroupStore


class GroupManagerDialog(QDialog):
    def __init__(
        self,
        store: ShelfGroupStore,
        parent: QWidget | None = None,
        *,
        on_applied: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("管理书架分组")
        self.setMinimumWidth(420)
        self._store = store
        self._on_applied = on_applied

        root = QVBoxLayout(self)
        hint = QLabel(
            "勾选「显示」的分组会出现在书架上；取消勾选可隐藏整组漫画。\n"
            "删除分组时，其中漫画会移回「未分组」。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa; font-size: 12px;")
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(220)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        scroll.setWidget(self._rows_host)
        root.addWidget(scroll, 1)

        add_row = QHBoxLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("新分组名称")
        add_btn = QPushButton("添加分组")
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(self._name_edit, 1)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        close_btn = box.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText("关闭")
        root.addWidget(box)

        self._rebuild_rows()

    def _notify(self) -> None:
        if self._on_applied is not None:
            self._on_applied()

    def _rebuild_rows(self) -> None:
        self._store.load()
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for g in self._store.groups_ordered():
            self._rows_layout.addWidget(self._make_row(g))
        self._rows_layout.addStretch(1)

    def _make_row(self, g: ShelfGroup) -> QWidget:
        row = QWidget()
        row.setStyleSheet(
            "QWidget { background: #2a2a2e; border-radius: 8px; padding: 4px; }"
        )
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 6, 10, 6)

        vis = QCheckBox("显示")
        vis.setChecked(g.visible)
        vis.setEnabled(not g.system)
        vis.setToolTip("取消勾选后，该分组不会出现在书架上（漫画仍保留在分组中）")
        gid = g.id

        def on_vis(checked: bool, _gid: str = gid) -> None:
            self._store.set_visible(_gid, checked)
            self._notify()

        vis.toggled.connect(on_vis)
        h.addWidget(vis)

        name_lbl = QLabel(g.name)
        name_lbl.setStyleSheet("color: #e8e8e8; font-size: 14px;")
        name_lbl.setMinimumWidth(140)
        h.addWidget(name_lbl, 1)

        if not g.system:
            ren = QPushButton("重命名")
            ren.setStyleSheet("font-size: 12px; padding: 4px 10px;")

            def on_ren(_checked: bool = False, _gid: str = gid, _old: str = g.name) -> None:
                text, ok = QInputDialog.getText(
                    self, "重命名分组", "名称：", QLineEdit.EchoMode.Normal, _old
                )
                if ok and text.strip():
                    self._store.rename_group(_gid, text.strip())
                    self._rebuild_rows()
                    self._notify()

            ren.clicked.connect(on_ren)
            h.addWidget(ren)

            del_btn = QPushButton("删除")
            del_btn.setStyleSheet("font-size: 12px; padding: 4px 10px; color: #f88;")

            def on_del(_checked: bool = False, _gid: str = gid) -> None:
                r = QMessageBox.question(
                    self,
                    "删除分组",
                    "确定删除该分组？其中漫画将移回「未分组」。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if r != QMessageBox.StandardButton.Yes:
                    return
                self._store.remove_group(_gid)
                self._rebuild_rows()
                self._notify()

            del_btn.clicked.connect(on_del)
            h.addWidget(del_btn)
        else:
            sys_tag = QLabel("系统")
            sys_tag.setStyleSheet("color: #888; font-size: 11px;")
            h.addWidget(sys_tag)

        return row

    def _on_add(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            name = "新分组"
        self._store.add_group(name)
        self._name_edit.clear()
        self._rebuild_rows()
        self._notify()
