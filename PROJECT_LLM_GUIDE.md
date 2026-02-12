# XHS-Downloader 项目速查手册（面向 LLM）

更新时间：2026-02-11  
适用对象：需要快速接手本项目进行理解、部署、功能改造的 LLM / 开发者

## 1. 项目目标与能力边界

### 1.1 核心目标
- 提取小红书作品链接（含短链解析）
- 采集作品详情数据（图文/图集/视频）
- 下载无水印作品文件（支持断点续传、格式识别、下载记录去重）
- 以多入口提供能力：TUI、CLI、API、MCP、浏览器脚本联动

### 1.2 非目标（当前代码未完整覆盖）
- 完整测试体系（仓库当前无测试目录）
- 完整进度 UI（`source/TUI/progress.py` 为占位）
- DataRecorder/MapRecorder 的全量查询删除能力（存在 `pass` 占位实现）

## 2. 快速部署与运行

### 2.1 环境要求
- Python：`>=3.12,<3.13`（见 `pyproject.toml`）
- 推荐包管理：`uv`（也支持 `pip`）

### 2.2 本地部署（推荐 uv）
```bash
uv sync --no-dev
uv run main.py
```

### 2.3 本地部署（pip）
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 2.4 运行模式
- TUI（默认）：`python main.py`
- API 服务：`python main.py api`
- MCP 服务：`python main.py mcp`
- CLI 参数模式：`python main.py --help`

入口分发见 `main.py`（根据 `argv` 判断模式）。

### 2.5 Docker
- 镜像构建：参考 `Dockerfile`
- 容器默认执行：`python main.py`
- 挂载卷：`/app/Volume`（配置与下载数据持久化目录）

## 3. 高层架构（执行链路）

请求/输入 -> 链接提取 -> 页面请求 -> HTML 转结构化数据 -> 作品字段抽取 -> 下载地址生成 -> 文件下载 -> 记录落库

主核心类：`source/application/app.py` 中 `XHS`

关键方法链：
1. `extract()`：批量处理入口  
2. `extract_links()`：识别/规范化可处理链接（含短链）  
3. `_get_html_data()`：拉取页面并生成 `Namespace` 数据对象  
4. `_extract_data()`：抽取作品元信息  
5. `_deal_download_tasks()`：按作品类型生成下载地址并执行下载  
6. `save_data()` + `IDRecorder`：保存作品数据与下载记录

## 4. 目录与模块职责

### 4.1 顶层
- `main.py`：统一入口（TUI/API/MCP/CLI）
- `example.py`：二次开发示例
- `README.md` / `README_EN.md`：功能与使用文档
- `pyproject.toml` / `requirements.txt`：依赖与项目元数据
- `Dockerfile`：容器构建
- `Volume/`：运行时数据（配置、DB、下载文件）

### 4.2 `source/` 模块
- `source/application/`：业务核心
  - `app.py`：`XHS` 主流程、API/MCP 路由与工具定义
  - `request.py`：网络请求封装
  - `explore.py`：作品字段抽取
  - `image.py` / `video.py`：下载地址生成
  - `download.py`：下载器（并发、断点续传、签名识别后缀）
- `source/module/`：基础能力
  - `manager.py`：运行参数校验、HTTP 客户端、路径管理
  - `settings.py`：`settings.json` 读写与兼容补全
  - `recorder.py`：SQLite 记录层（下载记录/采集数据/作者映射）
  - `mapping.py`：作者昵称映射更新与文件重命名
  - `script.py`：WebSocket 脚本任务服务
  - `static.py`：版本号、常量、默认 UA、文件签名表
- `source/TUI/`：Textual 界面
  - `app.py`：TUI App 壳与屏幕切换
  - `index.py`：主操作页面
  - `setting.py`：配置修改页
  - `monitor.py`：剪贴板监听页
  - `record.py`：下载记录删除页
- `source/CLI/`：Click 命令行参数入口
- `source/expansion/`：工具扩展
  - `converter.py`：从 HTML 提取 `window.__INITIAL_STATE__`
  - `namespace.py`：安全链式字段访问
  - `cleaner.py` / `truncate.py`：文件名清洗和长度裁剪
- `source/translation/`：i18n（gettext）

## 5. 配置、数据与持久化

### 5.1 配置文件
- 路径：`Volume/settings.json`
- 由 `Settings.run()` 自动创建/兼容补全
- 关键项：
  - `cookie`、`proxy`、`timeout`
  - `image_format`、`video_preference`
  - `download_record`、`record_data`
  - `author_archive`、`folder_mode`
  - `script_server`

### 5.2 数据库
- `Volume/ExploreID.db`：下载记录（去重依据）
- `Volume/MappingData.db`：作者 ID 映射
- `Volume/Download/ExploreData.db`：作品详情（开启 `record_data` 时）

### 5.3 文件输出
- 默认下载目录：`Volume/Download`
- `author_archive=true`：按作者分目录
- `folder_mode=true`：单作品独立目录

## 6. 外部接口速查

### 6.1 API 模式
- 启动：`python main.py api`
- 文档：`http://127.0.0.1:5556/docs`
- 主要接口：`POST /xhs/detail`
- 请求模型：`ExtractParams`（`source/module/model.py`）

### 6.2 MCP 模式
- 启动：`python main.py mcp`
- 默认地址：`http://127.0.0.1:5556/mcp/`
- 工具：
  - `get_detail_data`：仅取作品信息
  - `download_detail`：下载文件，可选返回信息

### 6.3 浏览器脚本联动
- 脚本：`static/XHS-Downloader.js`
- 服务端：`ScriptServer`（`source/module/script.py`，默认端口 `5558`）
- 条件：配置 `script_server=true`

## 7. 改造入口（按常见需求）

### 7.1 改“支持链接规则”
- 修改：`XHS` 中正则定义与 `extract_links()`
- 文件：`source/application/app.py`

### 7.2 改“作品字段抽取/返回结构”
- 修改：`Explore.__extract_*`
- 文件：`source/application/explore.py`
- 同步检查：`ExtractData` 模型、API/MCP 返回结构

### 7.3 改“下载策略”
- 并发数：`MAX_WORKERS`（`source/module/static.py`）
- 断点续传/文件后缀识别：`Download.__download()` / `__suffix_with_file()`
- 图片/视频链接生成：`source/application/image.py`、`source/application/video.py`

### 7.4 改“命名与目录归档”
- 规则入口：`XHS.__naming_rules()`
- 路径归档：`Manager.archive()`、`Download.__generate_path()`
- 作者改名联动：`source/module/mapping.py`

### 7.5 改“配置项”
- 默认值：`source/module/settings.py` 的 `default`
- 参数校验：`source/module/manager.py`
- TUI 设置页：`source/TUI/setting.py`
- CLI 参数：`source/CLI/main.py`

### 7.6 改“API/MCP 能力”
- API 路由：`XHS.setup_routes()`
- MCP 工具：`XHS.run_mcp_server()`
- 文件：`source/application/app.py`

## 8. 当前技术债与风险

- `source/TUI/progress.py` 未实现。
- `source/module/recorder.py` 中 `DataRecorder` / `MapRecorder` 多个接口为占位 `pass`。
- 代理请求在 `request.py` 中混用异步与同步 `httpx.get`，潜在阻塞风险（可评估统一为 `AsyncClient`）。
- 当前缺少自动化测试与 CI 质量门禁（lint/test/typecheck）闭环。

## 9. 建议的改造工作流（给 LLM）

1. 先确认目标属于哪一层：入口层（TUI/CLI/API/MCP）还是核心层（application/module）。
2. 用最小改动定位单一链路，避免跨层同时重构。
3. 修改后至少做三类验证：
   - 启动验证：`python main.py` / `python main.py api`
   - 功能验证：使用 `example.py` 或 API 请求验证一条真实链接
   - 数据验证：检查 `Volume` 下 DB/下载文件是否符合预期
4. 若涉及返回结构变更，同步更新：
   - Pydantic 模型
   - README 示例
   - MCP 工具描述文本

## 10. 最小操作清单（可直接执行）

```bash
# 1) 安装依赖
uv sync --no-dev

# 2) 启动默认 TUI
uv run main.py

# 3) 启动 API
uv run main.py api

# 4) 启动 MCP
uv run main.py mcp

# 5) 运行代码调用示例
uv run example.py
```

---

如需继续维护本手册，建议每次改动以下任一内容后同步更新：
- 入口参数与模式（`main.py`、`CLI`、`TUI`）
- API/MCP 协议（`source/application/app.py`、`source/module/model.py`）
- 配置字段（`source/module/settings.py`、`source/TUI/setting.py`）
- 下载与落库规则（`source/application/download.py`、`source/module/recorder.py`）
