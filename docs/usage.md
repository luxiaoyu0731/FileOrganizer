# FileOrganizer 使用与打包

## 源码启动

Node.js 22.12+ 或 24 LTS，Python 3.11+。仓库根目录运行：

```sh
npm ci
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
```

浏览器体验需要两个终端：

```sh
cd backend
venv/bin/uvicorn server:app --host 127.0.0.1 --port 18923
```

```sh
npm run dev:vite
```

桌面开发：`npm run dev`，自动使用 `backend/venv` 中的 Python；也可以通过 `FILEORGANIZER_PYTHON` 指定其他已安装项目依赖的解释器。

## 免费离线样例

```sh
backend/venv/bin/python examples/try_archive.py --destination ../fileorganizer-sample
```

只在新目录创建三个合成文件，运行实际归档与回滚，验证 SHA-256。分类为人工指定，不调用模型。重复目标会拒绝运行。

## 日常操作

1. 设置模型接口、扫描目录、归档目标。
2. 扫描文件，生成智能分组，检查并调整目录树。
3. 确认后执行复制、校验与移除源文件。
4. 在操作历史查看记录；仅对未修改且可找到的归档文件执行回滚。

实际模型调用可能发送文件路径和摘要并收费。不要用没有备份的重要文件试用；回滚不是无条件恢复保证。自动监听会自动执行文件操作，首次体验不要启用。

## Mac Apple Silicon 体验版

打包需在 Mac 上运行，Python 环境需要已有 PyInstaller 构建工具：

```sh
FILEORGANIZER_PYTHON=backend/venv/bin/python npm run build:backend
CSC_IDENTITY_AUTO_DISCOVERY=false npm run build:mac
```

后端先构建到 `build/backend`，Electron 包输出到 `release/`。当前目标为 Apple Silicon；不把它当作 Intel、Windows 或 Linux 的验证。图标来自仓库自制矢量 `resources/icon.svg`。

体验包未签名、未公证，macOS 可能阻止启动。保持系统安全设置，不运行关闭 Gatekeeper、删除 quarantine 或禁用 SmartScreen 的命令。不要用于敏感文件；稳定公开发行还需开发者签名和相应平台验收。

## 验证与排障

```sh
npm run typecheck
npm run build:frontend
npm run build:electron
python -m pytest backend/tests -q
```

后端不可达时检查端口 18923 和日志；模型第一次使用可能下载向量权重，未配置模型不会完成 AI 分类。桌面密钥尝试使用 `safeStorage`，不可用时存在明文回退；浏览器设置位于本地存储。不要共享配置、日志或凭据。

[代码审查](code-review.md) · [安全反馈](../SECURITY.md)

## 签名准备

已有 Developer ID Application 证书并安全配置 `notarytool` Keychain profile 后，设置 `APPLE_KEYCHAIN_PROFILE`，运行 `npm run build:mac:signed`。预检查在没有证书、没有公证凭据或主动关闭签名发现时拒绝构建；不打印凭据，不自动创建或购买账号。完整签名版仍需验证 `codesign --verify --deep --strict`、`xcrun stapler validate` 和 `spctl --assess`，通过后才能标为签名发行。当前下载入口仍为未签名体验版。
