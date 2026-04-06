"""JSON 文件实现的阅读进度仓库。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from comic_viewer.domain.models import ReadingProgress

PROGRESS_FILENAME = ".comic_viewer_progress.json"


class JsonFileProgressRepository:
    """进度保存在 `shelf_root / PROGRESS_FILENAME`，键为漫画根目录 resolve 路径。"""

    def __init__(self, shelf_root: Path) -> None:
        self._shelf_root = shelf_root.expanduser().resolve()
        self._path = self._shelf_root / PROGRESS_FILENAME
        self._data: dict[str, Any] = {"version": 1, "comics": {}}

    def file_path(self) -> Path:
        return self._path

    def path(self) -> Path:
        """与旧版 `ProgressStore.path()` 兼容。"""
        return self._path

    def load(self) -> None:
        if not self._path.is_file():
            self._data = {"version": 1, "comics": {}}
            return
        try:
            with self._path.open(encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = {"version": 1, "comics": {}}
        if not isinstance(self._data, dict):
            self._data = {"version": 1, "comics": {}}
        self._data.setdefault("version", 1)
        self._data.setdefault("comics", {})
        if not isinstance(self._data["comics"], dict):
            self._data["comics"] = {}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        tmp.replace(self._path)

    def get(self, comic_key: str) -> ReadingProgress | None:
        comics = self._data.get("comics") or {}
        row = comics.get(comic_key)
        if not isinstance(row, dict):
            return None
        try:
            ch = int(row.get("chapter_index", 0))
            sy = int(row.get("scroll_y", 0))
            img = int(row.get("image_index_1based", 1))
        except (TypeError, ValueError):
            return None
        return ReadingProgress(
            comic_key=comic_key,
            chapter_index=max(0, ch),
            scroll_y=max(0, sy),
            image_index_1based=max(1, img),
        )

    def put(
        self,
        comic_key: str,
        *,
        chapter_index: int,
        scroll_y: int,
        image_index_1based: int,
    ) -> None:
        comics = self._data.setdefault("comics", {})
        comics[comic_key] = {
            "chapter_index": int(chapter_index),
            "scroll_y": int(scroll_y),
            "image_index_1based": int(image_index_1based),
        }
