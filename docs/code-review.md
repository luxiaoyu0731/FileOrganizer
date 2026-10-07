# 代码审查 · 2026-10-06

结论：不是所有代码都混乱，但分类核心过度集中，文件操作的安全边界比界面包装更重要。

范围：53 个受版本管理的源码文件做规模与 Python 语法检查；详细阅读扫描、路径构建、归档、回滚、Electron 桥接与密钥处理。不是逐行形式化审计。

## 本次修复

- 回滚复用归档模块的 SHA-256 与重名处理，去掉重复哈希实现；原恢复名和 `_recovered` 均已被占用时，不覆盖已有文件。
- 恢复副本再次核对哈希，失败时保留归档原件。
- 去掉四处不必要的 Window→Record 强制转换，使用已有桥接声明。
- 扫描用路径、大小、修改时间生成快速 ID，避免逐文件读大视频；旧 `sha256` 字段名称保留兼容，测试验证真实身份语义。不能将该 ID 当作内容校验。

## 剩余问题

| 优先级 | 证据 | 后续建议 |
|---|---|---|
| 已修复 | 部分成功即标整次回滚完成 | 按动作记录恢复状态，允许重试未完成项；新增部分失败后重试测试 |
| 已修复 | 分类段未拒绝 `..` | 拒绝点路径、约束日期格式，构建与归档入口检查最终边界，测试已有符号链接越界 |
| 已修复 | 重名检查与复制分离 | 独占创建目标，只清理本次创建的副本，12 路并发测试验证无覆盖 |
| P2 | `backend/classifier/tree_classifier.py` 2,568 行 | 按分组、评分、回填、细分拆模块，先补特征测试 |
| P2 | `electron/main.ts` 加密不可用明文回退 | 显示回退状态或阻止保存，避免误称始终加密 |

## 本次验证

后端现有测试与新增覆盖：23 passed（1 项环境配置警告）；TypeScript 类型检查、Vite 前端构建已执行；Electron TypeScript 编译通过。未执行真实文件自动归档、各平台安装包和付费分类模型测试。

Git 历史 Gitleaks：0 项。依赖扫描与构建结果见仓库整理清单；扫描未发现不等于软件已通过安全认证。

本批以源码审查与展示整理为范围，不发布新的桌面安装包，不宣称所有安全风险已经解决。

## 依赖与发布判定

2026-10-06 使用 npm 官方 registry 执行 `npm audit --json`，升级前锁文件报告 46 项：低危 2、中危 9、高危 31、严重 4。统计是依赖图告警，不等同于已证实的运行时可利用漏洞；需逐项分析暴露面。

**运行产品发布：NO-GO。** 本次仅提交源码审查、展示文档及隔离测试覆盖的修复，不发布安装包或公网服务。不能通过修改扫描阈值、强制 audit fix 或隐藏风险制造全绿。

### 依赖修复与兼容验证

操作员批准大版本升级后，迁移至 Electron 44、Vite 8.3.3、Tailwind 4 和修复版测试工具，保留 Python 分类模型接口。Tailwind 4 使用明确的 PostCSS 插件并加载原主题配置，补齐旧版默认边框色。

原有 npm 依赖图 46 项告警（31 高危、4 严重）降为 8 项中危，高危与严重为 0；余下告警位于 electron-builder 的下载/日志依赖链，仍需追踪上游修复，不标成完全通过。尝试另一打包版本反而引入高危依赖，因此最终选择经过实测的 26.15.3 系列。未强制忽略 peer 冲突或修改审计基线。

移除没有源码引用的 JS OpenAI SDK、electron-store、vite-plugin-electron 与旧 autoprefixer；Python 后端 SDK 与 safeStorage 保留。密钥持久化实际是 localStorage 存储 safeStorage 处理后的内容，旧指南已修正。

在 Node 24.19.0 复核类型检查、前端构建、Electron 编译；23 项后端测试通过。用升级前源码独立构建对照新版：侧栏宽度、标题字号、可见文本、控件数量相同，未发现页面运行异常或横向溢出，初始引导截图已目视检查。这个检查不覆盖实际 AI 分类、自动监听或真实桌面安装包。

剩余 Vite CommonJS 配置兼容警告不影响本次构建；各平台签名、安装与 Electron 44 原生启动未验收。

## 2026-10-07 Apple Silicon 体验版复核

新增路径边界、并发同名、复制损坏与部分回滚重试覆盖；后端 31 项测试通过。构建产物首次从只读 DMG 复制到独立目录，原生 Electron 启动并确认后端健康；修复后重新构建的 DMG 完整性检查、独立目录原生启动、file:// 资源加载和后端健康复测均通过。安装包未签名、未公证，不提供关闭系统安全保护的指令。

边界：不覆盖恶意本地进程在边界检查后替换父目录的攻击，或断电发生在文件移动与日志落盘之间的恢复；不要把它当作数据备份。历史 NO-GO 是当时审查结论，最终体验版发布依据本批新鲜验证。

本批体验版就绪审查：GO WITH WARNINGS，仅限未签名 Apple Silicon 体验包。npm 官方扫描为 8 中危、0 高危、0 严重，剩余项在 electron-builder 的开发工具链；shell-quote 严重项升级至 1.12.0 后消除。TypeScript 与 Electron 编译、前端构建通过；31 项后端测试通过；离线样例 3 文件归档与恢复的内容校验通过。付费 AI 分类、Intel/Windows/Linux、浏览器下载 quarantine 后首次启动不在已验范围。

DMG SHA-256：`bed284ed7a9acea770a1766194fd9fa6403a30d505b7ecce7eb1ab8c10a406e3`。本地复制启动不等于签名或公证通过。发现问题时撤下 GitHub 体验版资产，源码回滚本批提交；不需要修改用户数据。

### Clean build regression (2026-10-07)

The backend builder previously changed into `backend/` before resolving FILEORGANIZER_PYTHON, so the documented relative interpreter `backend/venv/bin/python` could no longer be found. Relative paths now resolve against the caller directory before changing directories. An isolated regression covers a relative interpreter with spaces and the copied output. This changes build invocation, not file operation semantics; revert the builder change to roll back. Mac preview CI separately verifies DMG integrity, arm64 and packaged backend startup; a successful compile alone is not acceptance.
