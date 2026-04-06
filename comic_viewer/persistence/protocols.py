"""持久化与目录查询的抽象（依赖倒置 / 接口隔离）。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from comic_viewer.domain.models import ComicEntry, ReadingProgress, ShelfGroup


class ProgressRepository(Protocol):
    """阅读进度的读写字段，与具体存储介质无关。"""

    def load(self) -> None: ...

    def get(self, comic_key: str) -> ReadingProgress | None: ...

    def put(
        self,
        comic_key: str,
        *,
        chapter_index: int,
        scroll_y: int,
        image_index_1based: int,
    ) -> None: ...

    def save(self) -> None: ...


class ComicCatalog(Protocol):
    """枚举书架下可读漫画条目。"""

    def discover(self, shelf_root: Path) -> list[ComicEntry]: ...


class ShelfGroupStore(Protocol):
    """书架分组：增删、显隐、漫画归属。"""

    def load(self) -> None: ...

    def save(self) -> None: ...

    def groups_ordered(self) -> list[ShelfGroup]: ...

    def visible_groups_ordered(self) -> list[ShelfGroup]: ...

    def add_group(self, name: str) -> str: ...

    def remove_group(self, group_id: str) -> None: ...

    def set_visible(self, group_id: str, visible: bool) -> None: ...

    def rename_group(self, group_id: str, name: str) -> None: ...

    def assign_comic(self, comic_key: str, group_id: str) -> None: ...

    def comic_group_id(self, comic_key: str) -> str: ...
