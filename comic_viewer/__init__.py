"""Comic Viewer 应用包：领域模型、持久化、目录服务与 UI 分层。

SOLID 对应关系（简要）：
- S：各模块单一职责（domain / persistence / services / ui）。
- O：主窗口依赖 `ProgressRepository`、`ComicCatalog` 协议，可替换实现而少改 UI。
- L：协议由具体类满足，不引入脆弱继承层次。
- I：`protocols` 中接口按读写与目录查询拆分。
- D：UI 与入口依赖抽象协议，默认注入 JSON / 文件系统实现。

条漫引擎见 `comic_viewer.strip_loader`（`StripLoaderWidget`）。
"""

from comic_viewer.config import DEFAULT_SHELF_ROOT
from comic_viewer.ui.window import MainWindow

__all__ = ["DEFAULT_SHELF_ROOT", "MainWindow"]
