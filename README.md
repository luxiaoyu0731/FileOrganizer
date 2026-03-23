<h1 align="center">FileOrganizer</h1>

<p align="center">
  <b>AI-Powered Intelligent File Organizer</b><br/>
  Automatically classify, rename, and archive scattered files into a well-structured folder hierarchy using LLM semantic analysis and embedding-based clustering.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-blue" alt="Platform" />
  <img src="https://img.shields.io/badge/electron-28-47848F?logo=electron" alt="Electron" />
  <img src="https://img.shields.io/badge/react-19-61DAFB?logo=react" alt="React" />
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
</p>

---

**智能文件整理助手** — 基于 AI 语义分析的自动化文件分类与归档工具。

FileOrganizer 使用大语言模型和语义向量聚类，将散乱的文件智能归类到层级化的文件夹结构中，支持一键归档、完整回滚和实时监听。

---

## 功能特性

- **AI 智能分类** — 结合 LLM 语义分析 + Embedding 向量聚类，自动生成多级文件夹结构
- **多模型支持** — 兼容所有 OpenAI API 格式的模型服务（OpenAI、Claude、Ollama、本地模型等）
- **两阶段分类引擎** — Stage-1 识别项目分组 → Stage-2 生成子分类，兼顾准确性与细粒度
- **开发依赖智能处理** — 自动识别 venv/node_modules 等开发产物，归入所属项目而非独立分组
- **安全归档** — 复制 → SHA256 校验 → 删除原文件，确保零数据丢失
- **完整回滚** — 所有归档操作均可一键撤销，文件恢复到原始位置
- **实时监听** — 后台监控指定目录，新文件自动分类归档
- **空文件夹清理** — 归档后自动清理空目录（包括 `.DS_Store` 等系统文件）
- **内容提取** — 支持 PDF、Word、Excel、PPT、图片 EXIF、音频元数据等 30+ 种文件格式
- **暗色模式** — 支持明暗主题切换
- **系统托盘** — 监听模式下最小化到托盘，后台静默运行
- **首次向导** — 引导式配置 AI 接口、扫描路径和归档目录

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Tailwind CSS + Vite |
| 桌面端 | Electron 28 |
| 后端 | Python 3.10+ + FastAPI + Uvicorn |
| AI 引擎 | OpenAI SDK（兼容 OpenAI API 范式的任意服务） |
| 向量模型 | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) |
| 聚类算法 | HDBSCAN + KMeans (scikit-learn) |
| 打包 | electron-builder + PyInstaller |

---

## 分类引擎原理

```
              ┌─────────────────────────────────┐
              │  Stage 0: 内容提取 + 语义向量生成  │
              └────────────────┬────────────────┘
                               ▼
              ┌─────────────────────────────────┐
              │  Stage 1: AI 项目分组识别         │
              │  • 发送所有文件名+目录路径给 LLM   │
              │  • LLM 返回项目名 + 关键词列表     │
              │  • 多信号评分匹配每个文件到项目     │
              │  • 时间聚类 + 向量相似度兜底       │
              └────────────────┬────────────────┘
                               ▼
              ┌─────────────────────────────────┐
              │  Stage 2: 项目内子分类            │
              │  • 大组(200+)用 Embedding 聚类     │
              │  • 小组用内容摘要 + LLM 细分       │
              │  • 碎片组(<10文件)自动合并到近邻    │
              └────────────────┬────────────────┘
                               ▼
              ┌─────────────────────────────────┐
              │  后处理: 开发依赖回填 + 递归细分   │
              │  • venv/node_modules 归入所属项目  │
              │  • 超大子文件夹递归拆分            │
              └─────────────────────────────────┘
```

### 关键词匹配评分机制

每个文件与每个项目组的匹配分数由以下信号加权计算：

| 信号 | 权重 | 说明 |
|------|------|------|
| 文件名关键词 | ×1.0 | 子串匹配 +2，Token 交集 +1 |
| 父目录名 | ×3.0 | 最强信号 |
| 祖父目录名 | ×2.0 | 辅助信号 |
| 完整相对路径 | ×2.0 | 确保深层嵌套文件也能匹配到顶层项目 |

分数按 `sqrt(关键词数)` 归一化，防止关键词多的项目过度吸引文件。

---

## 工作流程

```
扫描文件  →  AI 智能分组  →  预览文件夹树  →  确认归档  →  自动清理空文件夹
    ↑                                                        ↓
后台监听  ←←←←←←←←←←←←←←←←←←←←←←←←←←←  操作历史 / 一键回滚
```

---

## 快速开始

### 环境要求

- **Node.js** >= 18
- **Python** >= 3.10
- **npm** >= 9（随 Node.js 附带）

### 安装

```bash
# 1. 克隆项目
git clone https://github.com/luxiaoyu0731/FileOrganizer.git
cd FileOrganizer

# 2. 安装前端依赖
npm install

# 3. 安装后端依赖
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

### 启动（开发模式）

需要同时启动前端和后端两个服务。

**终端 1 — 启动后端：**
```bash
cd backend
source venv/bin/activate        # Windows: .\venv\Scripts\activate
uvicorn server:app --host 127.0.0.1 --port 18923 --reload
```

**终端 2 — 启动前端：**
```bash
npm run dev:vite
```

浏览器打开 `http://localhost:5173` 即可使用。

**以 Electron 桌面应用启动（可选）：**
```bash
# 确保后端已在终端 1 启动
npm run dev
```

### 首次配置

1. 点击左侧菜单进入 **设置** 页面
2. 在「AI 模型」区域选择 API 提供商
3. 填入 **API Key**（你的模型服务密钥，如 `your_api_key_here`）
4. 点击 **测试连接** 确认 API 可用（出现绿色提示即可）
5. 在「扫描路径」区域添加要整理的文件夹
6. 设置「归档路径」为整理后的目标文件夹
7. 返回 **控制台**，开始使用

---

## macOS 安装详细教程

### 环境准备

```bash
# 推荐通过 Homebrew 安装
brew install node python@3.11
```

> **Apple Silicon (M1/M2/M3/M4) 用户提示：**
>
> sentence-transformers 会自动使用 MPS 加速。如遇 PyTorch 安装问题，可先手动安装：
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
> ```

> 如果网络问题导致 Electron 下载失败，可跳过：
> ```bash
> ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm install
> ```

### 构建发布版 (macOS)

```bash
# 1. 构建后端二进制
cd backend && source venv/bin/activate
pip install pyinstaller
cd ..
bash scripts/build-backend.sh

# 2. 构建 macOS 应用
npm run build:mac
```

生成的 `.dmg` 安装包在 `dist/` 目录下。支持 Intel 和 Apple Silicon 双架构。

---

## Windows 安装详细教程

### 环境准备

- **Node.js** >= 18（从 [nodejs.org](https://nodejs.org/) 下载安装包）
- **Python** >= 3.10（从 [python.org](https://www.python.org/downloads/) 下载，**安装时勾选 "Add Python to PATH"**）
- **Git**（从 [git-scm.com](https://git-scm.com/download/win) 下载）

### 安装

```powershell
git clone https://github.com/luxiaoyu0731/FileOrganizer.git
cd FileOrganizer

npm install

cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

**常见问题处理：**

如果 PowerShell 提示「无法运行脚本」，需要解除执行策略限制：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

如果 `sentence-transformers` 安装失败，先单独安装 PyTorch：
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

如果使用 NVIDIA 显卡并希望 GPU 加速：
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

> 如果网络问题导致 Electron 下载失败：
> ```powershell
> $env:ELECTRON_SKIP_BINARY_DOWNLOAD=1
> npm install
> ```

### 启动

```powershell
# 终端 1 — 后端
cd backend
.\venv\Scripts\activate
uvicorn server:app --host 127.0.0.1 --port 18923 --reload

# 终端 2 — 前端
npm run dev:vite
```

### 构建发布版 (Windows)

```powershell
# 1. 构建后端二进制
cd backend
.\venv\Scripts\activate
pip install pyinstaller

pyinstaller --onefile --name file-organizer-backend `
  --add-data "config;config" `
  --add-data "scanner;scanner" `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols `
  --hidden-import uvicorn.protocols.http `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan `
  --hidden-import uvicorn.lifespan.on `
  server.py

New-Item -ItemType Directory -Force -Path ..\build\backend
Copy-Item dist\file-organizer-backend.exe ..\build\backend\
cd ..

# 2. 构建 Windows 应用
npm run build:win
```

生成的 `.exe` 安装包和免安装版（Portable）在 `dist/` 目录下。

---

## 使用说明

### 分类与归档

1. 点击 **扫描文件** — 扫描指定目录中的所有文件
2. 点击 **智能分组** — AI 自动分析文件内容并生成文件夹结构
3. 等待分类完成（进度条会实时显示阶段和进度）
4. 预览分类结果 — 查看 AI 生成的层级目录树，可点击重命名文件夹
5. 点击 **确认归档** — 将文件安全移动到目标目录结构中
6. 归档完成后自动清理源目录中的空文件夹

### 撤销归档

- 在归档完成页面点击 **撤销归档**
- 或进入 **操作历史** 页面，点击对应记录的 **回滚** 按钮
- 所有文件会恢复到归档前的原始位置
- 已回滚的操作显示「已回滚」标记，防止重复操作

### 实时监听模式

1. 在控制台页面点击 **开启监听**
2. 勾选 **自动归档** 可实现全自动流程：检测新文件 → 自动分类 → 自动归档
3. 监听运行时可将应用最小化到系统托盘
4. 在托盘图标右键菜单可选择「停止监听」或「退出」

---

## 支持的文件格式

| 类别 | 格式 |
|------|------|
| 文档 | PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, RTF |
| 代码 | PY, JS, TS, JAVA, C, CPP, GO, RS, HTML, CSS, JSON, YAML, XML |
| 图片 | JPG, PNG, GIF, BMP, WEBP, HEIC, SVG, TIFF |
| 音视频 | MP3, WAV, FLAC, AAC, MP4, AVI, MOV, MKV |
| 压缩包 | ZIP, RAR, 7Z, TAR, GZ |
| 学术 | LaTeX (.tex), Jupyter (.ipynb), MATLAB (.m), CAJ |

---

## 配置说明

| 设置项 | 说明 |
|--------|------|
| API Base URL | OpenAI 兼容接口地址（如 `https://api.openai.com/v1`） |
| API Key | 模型提供商的 API 密钥 |
| 模型名称 | 对应提供商的模型 ID（如 `gpt-4`、`deepseek-chat`） |
| 扫描路径 | 待整理的目录列表（可添加多个） |
| 归档目标路径 | 整理后文件存放的根目录 |
| 重命名策略 | `语义+日期`、`仅日期`、`保留原名` |
| 文件大小上限 | 跳过超出此大小的文件（默认 500 MB） |

> **安全说明：** API Key 在开发模式下存储于浏览器 `localStorage`，打包后通过 Electron `safeStorage` 加密存储（使用系统钥匙串）。API Key 不会出现在日志文件中。

---

## 项目结构

```
FileOrganizer/
├── src/                    # React 前端源码
│   ├── components/         # UI 组件（Dashboard, Settings, History...）
│   └── hooks/              # 自定义 Hooks（useBackend, useSettings...）
├── electron/               # Electron 主进程
│   ├── main.ts             # 窗口管理、系统托盘、IPC
│   ├── sidecar.ts          # Python 后端进程管理
│   └── preload.ts          # 安全隔离预加载脚本
├── backend/                # Python FastAPI 后端
│   ├── server.py           # API 路由入口
│   ├── classifier/         # AI 分类引擎
│   │   ├── tree_classifier.py  # 核心：两阶段层级分类
│   │   ├── embedder.py         # 语义向量 + 聚类
│   │   ├── ai_classifier.py    # OpenAI SDK 封装
│   │   └── rule_classifier.py  # 扩展名兜底分类
│   ├── scanner/            # 文件扫描与实时监听（watchdog）
│   ├── analyzer/           # 内容提取（PDF, Office, 图片, 音频）
│   ├── archiver/           # 安全归档（复制 → 校验 → 删除）
│   ├── rollback/           # 回滚与操作日志
│   ├── renamer/            # 路径构建与重命名策略
│   ├── config/             # Pydantic 数据模型
│   └── requirements.txt    # Python 依赖
├── resources/              # 应用图标（icns/ico/png）
├── scripts/                # 构建脚本
├── electron-builder.yml    # 跨平台打包配置
└── package.json            # 项目配置与脚本
```

---

## 后端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/scan` | 扫描目录 |
| POST | `/api/classify/tree` | AI 智能分组（层级树） |
| GET | `/api/classify/tree/progress/{id}` | 分类进度查询 |
| POST | `/api/classify/tree/cancel/{id}` | 取消分类任务 |
| POST | `/api/execute` | 执行归档 |
| POST | `/api/test-connection` | 测试 AI 连接 |
| GET | `/api/history` | 操作历史 |
| POST | `/api/rollback` | 回滚操作 |
| POST | `/api/cleanup-empty-dirs` | 清理空文件夹 |
| POST | `/api/watch/start` | 开启监听 |
| POST | `/api/watch/stop` | 停止监听 |
| GET | `/api/watch/status` | 监听状态 |

---

## 数据存储

| 内容 | 路径 |
|------|------|
| 操作日志（用于回滚） | `~/.fileorganizer/logs/*.json` |
| 应用设置（开发模式） | 浏览器 `localStorage` |
| 应用设置（打包后） | `electron-store`（加密存储 API Key） |

---

## 常见问题

### 后端启动报错 `ModuleNotFoundError`

确认已激活 Python 虚拟环境：
- **macOS / Linux：** `source backend/venv/bin/activate`
- **Windows：** `.\backend\venv\Scripts\activate`

### Embedding 模型首次加载很慢

首次运行会从 HuggingFace 下载 embedding 模型（约 500MB），后续使用本地缓存。如下载困难，可设置国内镜像：

```bash
# macOS / Linux
export HF_ENDPOINT=https://hf-mirror.com

# Windows PowerShell
$env:HF_ENDPOINT="https://hf-mirror.com"
```

### AI 调用超时

应用内置 180 秒硬超时 + 3 次重试机制。如果文件量大（>1000），建议使用响应速度较快的模型。

### macOS 提示「无法打开，因为无法验证开发者」

右键点击应用图标 → 选择「打开」→ 确认。或在终端运行：

```bash
xattr -cr /Applications/FileOrganizer.app
```

### Windows 安装包被 SmartScreen 拦截

点击「更多信息」→「仍要运行」即可。这是因为应用未经 Microsoft 代码签名。

### 如何撤销归档操作？

在「操作历史」页选择对应操作，点击「回滚」即可恢复文件到原位置。已回滚的操作会标记为灰色，防止重复回滚。

---

## 开发

```bash
# 运行前端测试
npm test

# 运行后端测试
cd backend && source venv/bin/activate   # Windows: .\venv\Scripts\activate
pytest

# TypeScript 类型检查
npm run typecheck

# Python 代码检查
cd backend && ruff check .
cd backend && mypy .
```

### npm 脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动 Electron + Vite + 后端 |
| `npm run dev:vite` | 仅启动前端开发服务器 |
| `npm run build` | 完整生产构建 |
| `npm run build:mac` | 构建 macOS 应用 |
| `npm run build:win` | 构建 Windows 应用 |
| `npm test` | 运行前端测试 |
| `npm run typecheck` | TypeScript 类型检查 |

---

## Contributing

欢迎贡献代码！请遵循以下流程：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -m 'Add some feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

---

## License

[MIT](LICENSE)
