"""从文件系统扫描漫画元数据与话数（单一职责：目录 → ComicEntry 列表）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from comic_viewer.domain.models import ComicEntry
from comic_viewer.persistence.progress_json import PROGRESS_FILENAME
from comic_viewer.strip_loader import IMAGE_SUFFIXES, is_image_file, list_chapter_dirs

META_JSON_NAMES = ("info.json", "meta.json", "book.json", "comic.json")


def _normalize_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        parts = re.split(r"[,，、\s]+", raw.strip())
        return [p for p in parts if p]
    return [str(raw)]


def _pick_meta_json(folder: Path) -> Path | None:
    for name in META_JSON_NAMES:
        p = folder / name
        if p.is_file():
            return p
    candidates = sorted(
        p for p in folder.iterdir() if p.suffix.lower() == ".json" and p.is_file()
    )
    for p in candidates:
        if p.name.startswith("."):
            continue
        if p.name == PROGRESS_FILENAME:
            continue
        return p
    return None


def _pick_cover(folder: Path) -> Path | None:
    for stem in ("cover", "poster", "thumb", "thumbnail"):
        for ext in sorted(IMAGE_SUFFIXES, key=str.lower):
            p = folder / f"{stem}{ext}"
            if p.is_file():
                return p
    images = sorted(
        (p for p in folder.iterdir() if is_image_file(p)),
        key=lambda x: x.name.lower(),
    )
    return images[0] if images else None


def load_meta_dict(meta_path: Path) -> dict[str, Any]:
    with meta_path.open(encoding="utf-8") as f:
        return json.load(f)


def meta_to_fields(data: dict[str, Any]) -> tuple[str, str, str, list[str]]:
    title = (
        data.get("title")
        or data.get("name")
        or data.get("书名")
        or data.get("book_title")
        or ""
    )
    title = str(title).strip() or "未命名"
    cid = data.get("id") or data.get("comic_id") or data.get("book_id") or ""
    cid = str(cid).strip() or title
    desc = (
        data.get("description")
        or data.get("desc")
        or data.get("summary")
        or data.get("描述")
        or data.get("intro")
        or ""
    )
    desc = str(desc).strip()
    tags = _normalize_tags(data.get("tags") or data.get("tag") or data.get("标签"))
    return cid, title, desc, tags


class FilesystemComicCatalog:
    """默认实现：扫描单层子目录，需含 JSON 元数据。"""

    def discover(self, shelf_root: Path) -> list[ComicEntry]:
        return discover_comics(shelf_root)


def discover_comics(shelf_root: Path) -> list[ComicEntry]:
    root = shelf_root.expanduser().resolve()
    if not root.is_dir():
        return []
    entries: list[ComicEntry] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        meta_path = _pick_meta_json(child)
        if meta_path is None:
            continue
        try:
            raw = load_meta_dict(meta_path)
        except (OSError, json.JSONDecodeError):
            continue
        cid, title, desc, tags = meta_to_fields(raw)
        cover = _pick_cover(child)
        chapters = list_chapter_dirs(child)
        entries.append(
            ComicEntry(
                root=child,
                comic_id=cid,
                title=title,
                description=desc,
                tags=tags,
                cover_path=cover,
                meta_json_path=meta_path,
                chapters=chapters,
            )
        )
    return entries
