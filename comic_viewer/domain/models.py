"""领域实体：与 UI、存储格式解耦的不可变风格数据。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ComicEntry:
    """单本漫画：根目录、元数据与已排序的话数路径。"""

    root: Path
    comic_id: str
    title: str
    description: str
    tags: list[str]
    cover_path: Path | None
    meta_json_path: Path | None
    chapters: list[Path] = field(default_factory=list)

    def progress_key(self) -> str:
        return str(self.root.resolve())


@dataclass
class ReadingProgress:
    """某本漫画的上次阅读位置（持久化载荷）。"""

    comic_key: str
    chapter_index: int = 0
    scroll_y: int = 0
    image_index_1based: int = 1


@dataclass
class ShelfGroup:
    """书架分组：排序、显隐；系统分组不可删除。"""

    id: str
    name: str
    order: int
    visible: bool = True
    system: bool = False
