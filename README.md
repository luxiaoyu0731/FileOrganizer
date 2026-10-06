# FileOrganizer

### 把散落的文件，整理成可理解的项目结构。

![文件从散乱到有序的概念插画](docs/media/project-hero.png)

Electron · React · Python / FastAPI · 语义分类 · Apache-2.0

[快速开始](#快速开始) · [分类流程](#分类流程) · [代码审查](docs/code-review.md) · [详细使用指南](docs/usage.md)

面向本地文件整理的桌面工具：扫描目录，结合文件摘要、语义向量和大模型生成分类方案；先预览，再执行归档，并保存操作记录供回滚。

## 为什么做这个工具

扩展名能区分 PDF 和图片，却很难识别同一个项目的合同、表格、照片与代码。FileOrganizer 先识别项目，再在项目内部细分，保留人工确认这一步。

| 能力 | 实现 |
|---|---|
| 项目优先分类 | 两阶段分类、目录关键词、向量聚类 |
| 内容理解 | PDF、Office、文本与媒体元数据提取 |
| 归档前预览 | 可展开的层级目录树 |
| 文件完整性 | 复制后 SHA-256 核对，匹配后删除源文件 |
| 操作回滚 | 校验归档文件，恢复副本再次校验，冲突时换名 |
| 持续整理 | watchdog 目录监听与可选自动归档 |

## 分类流程

```mermaid
flowchart LR
  A[扫描本地目录] --> B[提取摘要与向量]
  B --> C[识别项目分组]
  C --> D[项目内细分]
  D --> E[人工预览确认]
  E --> F[复制与哈希校验]
  F --> G[归档与操作记录]
  G --> H[按记录回滚]
```

## 快速开始

Node.js 22.12+（22 / 24 LTS）或 26+、Python 3.11+。先用测试目录试运行，保留重要文件的独立备份。

```sh
git clone https://github.com/luxiaoyu0731/FileOrganizer.git
cd FileOrganizer
npm ci
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
```

终端一：

```sh
cd backend
venv/bin/uvicorn server:app --host 127.0.0.1 --port 18923
```

终端二：

```sh
npm run dev:vite
```

打开本地 Vite 页面，在设置中填入 OpenAI 兼容接口、扫描路径和归档路径。桌面开发与安装包构建见[使用指南](docs/usage.md)。

## 结构与验证

| 目录 | 职责 |
|---|---|
| src/ | 预览、配置、历史记录与监听界面 |
| electron/ | 窗口、IPC、后端 sidecar、密钥存储 |
| backend/classifier/ | 项目识别与语义细分 |
| backend/archiver/、rollback/ | 校验移动与操作恢复 |
| backend/tests/ | 扫描、归档和回滚测试 |

```sh
npm run typecheck
npm run build:frontend
cd backend && python -m pytest tests -q
```

扫描字段 `sha256` 为兼容旧接口保留，实际存储路径、大小和修改时间生成的快速身份标识；内容完整性由归档阶段真实 SHA-256 校验负责。

## 数据与安全

文件处理在本地进行；调用分类服务时，文件名、路径及提取摘要可能发送给配置的模型服务。开发模式设置保存在 localStorage；Electron 使用 safeStorage，系统加密不可用时存在明文回退，详见代码审查。不要把服务绑定到公网。

自动归档与回滚不是备份系统；并发写入、符号链接竞态和部分回滚仍需更完整验证。本仓库不承诺“零数据丢失”。

原创代码采用 [Apache-2.0](LICENSE)，依赖保留各自许可。[素材说明](docs/media/README.md)。
