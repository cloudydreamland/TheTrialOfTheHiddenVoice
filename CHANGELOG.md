# CHANGELOG — sothstan

## 0.1.0 (2026-10-05)

首个稳定版，功能与 0.1.0rc1 一致：探测框架（5 探测器，tier 分级）、混淆集似然比
判决、基线注册表、mock 双人格服务器、CLI（check/collect/list-baselines/selftest）。
README 安装说明更新为 PyPI 安装优先。

## 0.1.0rc1 (2026-09-28)

- 首个可用版本：探测框架（5 探测器，tier 分级）、混淆集似然比判决
  （margin + claimed 总分硬地板）、基线注册表（schema 校验/demo 隔离）、
  mock 双人格服务器（诚实/换模型/完美说谎三形态）、
  CLI（check/collect/list-baselines/selftest，退出码 0-4）、
  证据链转录（脱敏 + 确定性哈希）、demo 基线生成工具。
- 41 项测试全绿，ruff 清零，selftest 四攻击场景 PASS。
