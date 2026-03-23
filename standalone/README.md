# FileOrganizer — 傻瓜版（Standalone）

无需安装 Python / Node.js / Electron，**双击即用**。

---

## 给最终用户

### macOS / Linux

1. 下载 `file-organizer`
2. 终端赋权（仅首次）：
   ```bash
   chmod +x file-organizer
   ```
3. 双击运行，或终端执行：
   ```bash
   ./file-organizer
   ```
4. 浏览器自动打开 `http://127.0.0.1:18924`

> macOS 提示「无法验证开发者」：右键 → 打开 → 仍要打开

### Windows

1. 下载 `file-organizer.exe`
2. 双击运行
3. 浏览器自动打开 `http://127.0.0.1:18924`

> Windows Defender 可能弹出警告，点击「仍要运行」即可

### 停止应用

- 关闭浏览器标签页不会停止服务
- 在终端按 `Ctrl+C`，或通过任务管理器结束进程

---

## 数据存储

- 设置：浏览器 `localStorage`（清空浏览器数据会丢失设置）
- 操作日志：`~/.fileorganizer/logs/`（macOS/Linux）或 `C:\Users\用户名\.fileorganizer\logs\`（Windows）

---

## 注意事项

| 功能 | Electron 版 | Standalone 版 |
|------|-------------|---------------|
| 文件夹选择对话框 | ✅ 系统对话框 | ❌ 需手动输入路径 |
| API Key 加密存储 | ✅ 系统钥匙串 | ⚠️ localStorage（明文） |
| 系统托盘 | ✅ 有 | ❌ 无 |
| 自动更新 | 可配置 | 手动替换文件 |
| 文件归档/分类/回滚 | ✅ | ✅ |
| 后台监听 | ✅ | ✅ |

---

## 给开发者（构建说明）

### 前置环境（仅开发者机器需要）

- Python 3.11+
- Node.js 18+
- npm

### macOS / Linux 构建

```bash
cd "FileOrganizer Agent"
bash standalone/build.sh
# 产物：standalone/dist/file-organizer
```

### Windows 构建

```cmd
cd "FileOrganizer Agent"
standalone\build.bat
REM 产物：standalone\dist\file-organizer.exe
```

### 构建流程说明

```
build.sh / build.bat
  │
  ├─ [1] pip install -r standalone/requirements.txt
  │       安装 Python 依赖 + PyInstaller
  │
  ├─ [2] npx vite build --config vite.standalone.config.ts
  │       编译 React → standalone/web/
  │       关键：alias 将 useBackend / useSettings 替换为
  │             standalone/src/hooks/ 中的 fetch() 版本
  │
  └─ [3] pyinstaller standalone/main.py
          将以下内容打包进单文件二进制：
            - Python 解释器 + 所有依赖
            - backend/ 目录（FastAPI 路由逻辑）
            - standalone/web/ 目录（React 静态文件）
          启动时自动解压到临时目录并运行
```

### 目录结构

```
standalone/
├── main.py                  # 入口：FastAPI + 静态文件托管 + 自动打开浏览器
├── requirements.txt         # Python 依赖
├── build.sh                 # macOS/Linux 构建脚本
├── build.bat                # Windows 构建脚本
├── src/
│   └── hooks/
│       ├── useBackend.ts    # fetch() 版（替换 Electron IPC 版）
│       └── useSettings.ts   # 纯 localStorage 版（无 safeStorage）
├── web/                     # 构建产物（由 build.sh 生成，不提交 git）
└── dist/                    # 可执行文件（由 build.sh 生成，不提交 git）
```

### .gitignore 建议

```
standalone/web/
standalone/dist/
standalone/build/
```
