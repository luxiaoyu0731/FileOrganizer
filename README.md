# FileOrganizer

把散落的合同、表格、图片和代码整理成项目目录，先看分类方案，再确认归档。

![文件整理概念插画](docs/media/project-hero.png)

Electron · React · Python / FastAPI · Apache-2.0

## 核心功能

- 结合文件摘要、语义向量与大模型，按项目分组并细分目录。
- 在目录树中预览分类方案，确认后执行复制、SHA-256 校验与归档。
- 保存操作记录，支持冲突换名恢复和目录监听。

## 本地运行

需要 Node.js 22.12+（22 / 24 LTS）或 26+、Python 3.11+。先在测试目录试用，并独立备份重要文件。

```sh
git clone https://github.com/luxiaoyu0731/FileOrganizer.git
cd FileOrganizer
npm ci
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
```

分别在两个终端运行：

```sh
# 后端
cd backend
venv/bin/uvicorn server:app --host 127.0.0.1 --port 18923
```

```sh
# 仓库根目录：前端
npm run dev:vite
```

打开终端给出的 URL，配置模型接口、扫描路径与目标目录。[桌面启动与打包指南](docs/usage.md)。

文件名、路径和提取摘要可能发送给你配置的模型服务。自动归档与回滚不能替代备份；不要将本地服务开放到公网。

<details>
<summary>开发与安全说明</summary>

源码入口：`src/` 界面、`electron/` 桌面桥接、`backend/` 分类与归档。

```sh
npm run typecheck
npm run build:frontend
python -m pytest backend/tests -q
```

[代码审查](docs/code-review.md)记录并发文件操作、凭据明文回退及未验收的安装包边界；不承诺零数据丢失。[贡献指南](CONTRIBUTING.md) · [安全反馈](SECURITY.md)。

</details>

[Apache-2.0](LICENSE) · [素材说明](docs/media/README.md)
