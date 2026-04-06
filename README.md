# Comic-Viewer（条漫阅读器）

本地 **竖向条漫** 阅读器：书架分组、漫画详情、按话阅读、记录上次阅读位置与继续阅读。图形界面基于 **PySide6**。

## 与 jmcomic-downloader 配合使用（推荐）

本项目的定位是：**在本地已下载的漫画目录上阅读**。漫画资源请使用 **[jmcomic-downloader](https://github.com/lanyeeee/jmcomic-downloader)** 获取。

| 步骤 | 说明 |
|------|------|
| 1 | 使用 [jmcomic-downloader](https://github.com/lanyeeee/jmcomic-downloader) 搜索/登录收藏、勾选章节并完成下载（图形界面，基于 Tauri；详见其 [README](https://github.com/lanyeeee/jmcomic-downloader/blob/main/README.md)）。 |
| 2 | 将下载输出目录（或你整理后的父目录）作为本阅读器的 **书架根目录**（`DEFAULT_SHELF_ROOT` 或启动参数，见下文）。 |
| 3 | 若下载结果尚未包含元数据 JSON，请在每部漫画文件夹内补充 `info.json`（或 `meta.json` / `book.json` / `comic.json`）及封面图，以便书架展示书名、标签与封面（见 [目录约定](#目录约定)）。 |
| 4 | 启动本程序：`python main.py [书架根目录]` |

**说明：** [jmcomic-downloader](https://github.com/lanyeeee/jmcomic-downloader) 与本项目相互独立；前者负责下载与收藏，后者仅读取本地文件夹，不访问站点 API。请遵守下载器与资源站点的用户协议及当地法律法规。

## 环境要求

- Python 3.10+（建议 3.12+）
- [PySide6](https://pypi.org/project/PySide6/)

```bash
cd /path/to/Comic-Viewer
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install PySide6
```

## 运行

```bash
python main.py
```

或指定书架根目录：

```bash
python main.py /path/to/your/shelf
```

默认书架路径在 `comic_viewer/config.py` 的 `DEFAULT_SHELF_ROOT`，可按本机情况修改。

## 目录约定

书架根目录下 **每一部漫画一个子文件夹**。要出现在书架中，该子文件夹内需包含 **至少一个 JSON 元数据文件**（优先文件名：`info.json`、`meta.json`、`book.json`、`comic.json`，否则取首个非隐藏 `.json`）。

**JSON 常用字段（可选键名见实现）**

- 书名：`title` / `name` / `书名` / `book_title`
- ID：`id` / `comic_id` / `book_id`
- 描述：`description` / `desc` / `summary` / `描述` / `intro`
- 标签：`tags`（数组）或 `tag` / `标签`（字符串）

**封面**：优先 `cover.*`、`poster.*`、`thumb.*`；否则使用漫画根目录下首张图片。

**话数**：漫画根目录下的 **子文件夹**，且文件夹内直接含有图片（`jpg` / `png` / `webp` 等）即视为一话；话序按文件夹名排序（支持「第 N 话」等规则）。

示例：

```text
书架根目录/
  .comic_viewer_progress.json      # 阅读进度（自动生成）
  .comic_viewer_shelf_groups.json  # 分组（自动生成）
  某漫画/
    info.json
    cover.jpg
    第1话/
      001.webp ...
    第2话/
      ...
```

## 功能摘要

- 书架：按 **分组**（`QGroupBox`）展示，可 **分组管理**、显示/隐藏分组、右键将漫画移至分组
- 详情页：元信息、继续阅读、按话进入阅读
- 阅读：左侧热区呼出话数列表、滚底下一话、回顶上一话、状态栏当前张数/话数
- 进度：写入书架根目录下的 `.comic_viewer_progress.json`

## 项目结构（概要）

```text
main.py                 # 唯一入口
comic_viewer/
  config.py             # 默认书架路径等
  strip_loader.py       # 条漫加载与话数扫描辅助
  domain/               # 领域模型
  persistence/          # 进度与分组 JSON
  services/catalog.py   # 扫描书架 → 漫画列表
  ui/                   # 主窗口、书架、详情、阅读壳等
```

## 免责声明

- 本工具仅用于浏览 **用户本机已有** 的漫画文件；请通过合法途径取得内容，并自行承担使用责任。
- 与 [jmcomic-downloader](https://github.com/lanyeeee/jmcomic-downloader) 相关的下载行为、账号与版权事项，以该仓库说明及当地法律为准。

## 许可证

仓库根目录若尚未包含 `LICENSE`，请按你的分发需求自行补充许可文件。
