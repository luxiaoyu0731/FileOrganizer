# Changelog

所有重要变更均记录在此文件中，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [0.1.0] - 2026-03-17

### 新增

#### 应用框架
- Electron 28 + React 19 + TypeScript + Vite 5 跨平台桌面应用骨架
- Python FastAPI sidecar（绑定 127.0.0.1:18923），随 Electron 启动/退出
- contextBridge IPC 通信层，渲染进程隔离访问后端 API
- 首次启动引导向导（5 步：欢迎 → AI 配置 → 扫描路径 → 归档路径 → 完成）
- 亮色/深色主题切换，持久化到 localStorage

#### 文件扫描
- 递归扫描多个目录，过滤隐藏文件、系统文件、临时文件、符号链接、空文件
- SHA256 哈希计算，文件大小限制（可配置，默认 500 MB）
- Windows 长路径（>260 字符）检测并跳过
- `POST /api/scan` 端点

#### AI 分类
- OpenAI SDK 兼容任意接口（OpenAI / Claude / Ollama / 本地模型）
- 并发分类（信号量控制，最多 5 并发）
- 3 次指数退避重试，30 秒超时
- AI 失败时自动回退到扩展名规则分类
- 扩展名规则分类器（覆盖 30+ 种文件类型）
- `POST /api/classify` 端点

#### 内容提取
- PDF：pymupdf → pdfplumber 双重提取，前 2000 字符 + 元数据
- 图片：Pillow + piexif EXIF 提取，HEIC/HEIF 支持（pillow-heif）
- Office：Word / Excel / PowerPoint 摘要提取
- 音视频：mutagen 元数据（标题、艺术家、时长）

#### 重命名策略
- `semantic_date`：`日期_AI语义名.ext`
- `date_prefix`：`日期_原名.ext`
- `preserve_original`：保留原文件名
- 日期优先级链：内容日期 > EXIF > 文件修改时间

#### 安全归档
- copy2 → SHA256 校验 → 删除源文件，确保数据完整性
- 同名冲突自动追加 `_001`、`_002` 后缀
- 归档前磁盘剩余空间检查（文件大小 + 10 MB 余量）
- `POST /api/execute` 端点

#### 操作回滚
- JSON 格式操作日志，存储在 `~/.fileorganizer/logs/`
- SHA256 校验，文件已修改则跳过并告警
- 源路径冲突时恢复为 `{原名}_recovered.ext`
- `GET /api/history`、`POST /api/rollback` 端点

#### 后台监听
- watchdog 跨平台文件监听（macOS FSEvents / Windows ReadDirectoryChangesW / Linux inotify）
- 5 秒 debounce，过滤下载中文件（.crdownload / .part 等）
- 可配置自动归档（`auto_execute`）或仅记录
- `POST /api/watch/start|stop`、`GET /api/watch/status` 端点

#### 系统托盘
- 监听模式下关闭窗口最小化到托盘，不退出
- 托盘右键菜单：打开主窗口 / 停止监听 / 退出
- `app.on('will-quit')` 优雅关闭：停止监听 → kill Python 进程

#### 前端 UI
- 控制台：扫描 → AI 分类 → 预览 → 执行 → 完成 多步流程
- 文件预览表格：勾选框、置信度徽章、展开 AI 理由、内联编辑分类/文件名
- 操作历史：展开详情、回滚确认
- WatchStatus 组件：监听状态指示、最近处理文件列表（3 秒轮询）
- 文件类型 emoji 图标（15 种分类）
- 归档进度条（模拟进度 + 完成跳转）
- Toast 通知（success / error / info / warning，3.5 秒自动消失）

#### 安全
- API Key 通过 Electron safeStorage 加密存储（系统钥匙串）
- Linux safeStorage 不可用时自动降级为明文存储（并标记 `keyFallback`）
- API Key 不写入操作日志，不传输到外部服务

#### 打包与分发
- `electron-builder.yml`：macOS（DMG + zip，x64 + arm64）、Windows（NSIS + portable）、Linux（AppImage + deb）
- `scripts/build-backend.sh`：macOS/Linux PyInstaller 打包脚本
- `scripts/build-backend.bat`：Windows PyInstaller 打包脚本
- `scripts/notarize.js`：macOS 公证脚本（需 APPLE_ID 等环境变量）

#### 测试
- 单元测试：扫描器（10 个测试，含符号链接、空文件、大小限制）
- 集成测试：安全归档（6 个测试）、回滚引擎（6 个测试）
- 总计 22 个测试，全部通过

---

## 下一版本计划

- macOS 和 Windows 打包验证（实际安装包测试）
- 冷启动时间优化（PyInstaller `--onedir` 对比）
- 国际化支持（英文 UI）
- 自定义分类体系（用户可编辑分类树）
- 云存储路径支持（iCloud Drive / OneDrive 本地映射路径）
