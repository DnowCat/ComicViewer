"""书架分组与漫画归属：JSON 持久化。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from comic_viewer.domain.models import ShelfGroup

SHELF_GROUPS_FILENAME = ".comic_viewer_shelf_groups.json"
DEFAULT_GROUP_ID = "__ungrouped__"
DEFAULT_GROUP_NAME = "未分组"


class JsonShelfGroupRepository:
    """`shelf_root / SHELF_GROUPS_FILENAME` 存储分组定义与 comic_key → group_id。"""

    def __init__(self, shelf_root: Path) -> None:
        self._shelf_root = shelf_root.expanduser().resolve()
        self._path = self._shelf_root / SHELF_GROUPS_FILENAME
        self._groups: list[ShelfGroup] = []
        self._comic_to_group: dict[str, str] = {}

    def file_path(self) -> Path:
        return self._path

    def load(self) -> None:
        if not self._path.is_file():
            self._groups = [
                ShelfGroup(
                    id=DEFAULT_GROUP_ID,
                    name=DEFAULT_GROUP_NAME,
                    order=0,
                    visible=True,
                    system=True,
                )
            ]
            self._comic_to_group = {}
            return
        try:
            with self._path.open(encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        self._groups = []
        seen_ids: set[str] = set()
        for row in raw.get("groups") or []:
            if not isinstance(row, dict):
                continue
            gid = str(row.get("id", "")).strip()
            if not gid or gid in seen_ids:
                continue
            seen_ids.add(gid)
            name = str(row.get("name", "")).strip() or "分组"
            try:
                order = int(row.get("order", len(self._groups)))
            except (TypeError, ValueError):
                order = len(self._groups)
            visible = bool(row.get("visible", True))
            system = bool(row.get("system", False))
            self._groups.append(
                ShelfGroup(
                    id=gid,
                    name=name,
                    order=order,
                    visible=visible,
                    system=system,
                )
            )
        if not any(g.id == DEFAULT_GROUP_ID for g in self._groups):
            self._groups.insert(
                0,
                ShelfGroup(
                    id=DEFAULT_GROUP_ID,
                    name=DEFAULT_GROUP_NAME,
                    order=-1,
                    visible=True,
                    system=True,
                ),
            )
        self._groups.sort(key=lambda g: (g.order, g.name.lower()))
        ctg = raw.get("comic_to_group") or {}
        self._comic_to_group = {
            str(k): str(v) for k, v in ctg.items() if isinstance(k, str) and isinstance(v, str)
        }
        self._normalize_assignments_on_load()

    def _normalize_assignments_on_load(self) -> None:
        valid = {g.id for g in self._groups}
        changed = False
        for key, gid in list(self._comic_to_group.items()):
            if gid not in valid:
                self._comic_to_group[key] = DEFAULT_GROUP_ID
                changed = True
        if changed:
            self.save()

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": 1,
            "groups": [
                {
                    "id": g.id,
                    "name": g.name,
                    "order": g.order,
                    "visible": g.visible,
                    "system": g.system,
                }
                for g in sorted(self._groups, key=lambda x: (x.order, x.name.lower()))
            ],
            "comic_to_group": dict(self._comic_to_group),
        }
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(self._path)

    def groups_ordered(self) -> list[ShelfGroup]:
        return sorted(self._groups, key=lambda g: (g.order, g.name.lower()))

    def visible_groups_ordered(self) -> list[ShelfGroup]:
        return [g for g in self.groups_ordered() if g.visible]

    def valid_group_ids(self) -> set[str]:
        return {g.id for g in self._groups}

    def add_group(self, name: str) -> str:
        name = name.strip() or "新分组"
        gid = uuid.uuid4().hex[:12]
        orders = [g.order for g in self._groups]
        n_order = max(orders, default=0) + 1
        self._groups.append(
            ShelfGroup(id=gid, name=name, order=n_order, visible=True, system=False)
        )
        self.save()
        return gid

    def remove_group(self, group_id: str) -> None:
        if group_id == DEFAULT_GROUP_ID:
            return
        self._groups = [g for g in self._groups if g.id != group_id]
        for k, v in list(self._comic_to_group.items()):
            if v == group_id:
                self._comic_to_group[k] = DEFAULT_GROUP_ID
        self.save()

    def set_visible(self, group_id: str, visible: bool) -> None:
        for i, g in enumerate(self._groups):
            if g.id == group_id:
                if g.system:
                    return
                self._groups[i] = ShelfGroup(
                    id=g.id,
                    name=g.name,
                    order=g.order,
                    visible=visible,
                    system=g.system,
                )
                self.save()
                return

    def rename_group(self, group_id: str, name: str) -> None:
        name = name.strip()
        if not name:
            return
        for i, g in enumerate(self._groups):
            if g.id == group_id:
                if g.system:
                    return
                self._groups[i] = ShelfGroup(
                    id=g.id,
                    name=name,
                    order=g.order,
                    visible=g.visible,
                    system=g.system,
                )
                self.save()
                return

    def assign_comic(self, comic_key: str, group_id: str) -> None:
        valid = self.valid_group_ids()
        if group_id not in valid:
            group_id = DEFAULT_GROUP_ID
        self._comic_to_group[comic_key] = group_id
        self.save()

    def comic_group_id(self, comic_key: str) -> str:
        gid = self._comic_to_group.get(comic_key, DEFAULT_GROUP_ID)
        if gid not in self.valid_group_ids():
            return DEFAULT_GROUP_ID
        return gid
