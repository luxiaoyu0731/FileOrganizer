# 贡献指南

先说明问题与可复现输入，提交小范围修改，附对应测试结果。不要上传用户文件、论文、密钥、模型权重或环境目录。文档修正与代码修正分清范围。对外部模型行为请使用离线 mock；需要收费实验时先与维护者确认。

提交 PR 前运行 README 中的相关检查，并列出未运行项目。

## 从一个小任务开始 / Starter tasks

先在 Issue 中说明选择的任务和复现方法，再提交最小修改。测试只使用合成资料；不把外部模型收费作为贡献前提。

- **离线样例的只读 HTML 目录对比** — `examples/try_archive.py`。验收：样例结果生成独立 HTML；明确合成数据；无需模型；已有目录不覆盖。
- **补充空文件和 Unicode 文件名的往返测试** — `backend/tests/integration/test_archiver.py`。验收：新目录中的文件归档、撤销后字节一致；测试不依赖模型或用户目录。

[报告问题 / Report a bug](https://github.com/luxiaoyu0731/FileOrganizer/issues/new?template=bug_report.yml) · [首次使用反馈 / First-use feedback](https://github.com/luxiaoyu0731/FileOrganizer/issues/new?template=first_use.yml)
