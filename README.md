# The Trial of the Hidden Voice — Sothstan

简体中文 · [English](README.en.md)

> 展示名 **The Trial of the Hidden Voice** 描绘对隐匿声音的审视；Sothstan 是该项目的短名。

**中文优先的 LLM API 模型验真库。一个端点声称自己在服务模型 X——它真的在服务 X 吗？**
用多层指纹 + 混淆集似然比给出统计判决，证据链哈希锁定，可复现、可审计。

[![PyPI](https://img.shields.io/pypi/v/sothstan)](https://pypi.org/project/sothstan/)
[![Python](https://img.shields.io/pypi/pyversions/sothstan)](https://pypi.org/project/sothstan/)
[![CI](https://github.com/cloudydreamland/TheTrialOfTheHiddenVoice/actions/workflows/ci.yml/badge.svg)](https://github.com/cloudydreamland/TheTrialOfTheHiddenVoice/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
## 为什么需要它 / Why

第三方中转、代理或聚合 API 往往会返回一个自报模型名。仅凭这个字段无法验证端点的实际行为是否与所声明模型一致；差异也可能来自版本变化、采样参数、服务策略或网络错误。Sothstan 用可信基线比较多种行为信号，并保留统计结果和不确定性。

## 安装 / Install

```bash
python -m pip install sothstan
```

从源码安装（开发或最新版）：

```bash
git clone https://github.com/cloudydreamland/TheTrialOfTheHiddenVoice.git
cd TheTrialOfTheHiddenVoice
python -m pip install .
```

## 快速开始 / Quickstart

**没有官方 API key？先离线验证工具本身**（内置 mock 模型与四种攻击场景）：

```bash
sothstan selftest
# PASS  诚实服务器 → AUTHENTIC

# PASS  换模型中转 → MISMATCH（runner-up 正确指认）

# PASS  仅改 model 字段 → 仍 AUTHENTIC（字段回显零权重）

# PASS  伪造 usage 的说谎中转 → 仍 MISMATCH（行为/错误层暴露）

```

有 key 之后，两步验真：

```bash
# 第一步：对【官方】端点采集基线（至少 2 个模型，互为混淆集）

sothstan collect https://api.deepseek.com/v1 --model deepseek-chat \
    --family deepseek --out baselines/deepseek-chat.json --api-key-env DEEPSEEK_API_KEY
sothstan collect https://api.deepseek.com/v1 --model deepseek-reasoner \
    --family deepseek --out baselines/deepseek-reasoner.json --api-key-env DEEPSEEK_API_KEY

# 第二步：验证可疑端点

sothstan check https://relay.example.com/v1 --model deepseek-chat --api-key-env RELAY_KEY
# ✅ AUTHENTIC  margin +212.4  证据链 9f3a…  exit 0

# ❌ MISMATCH   runner-up: deepseek-reasoner  exit 2

```

## 工作原理 / How it works

```
探测（probe）──产出──> 指纹信号（signal）──对比──> 基线（baseline，官方端点采集）
                                                        │
                              混淆集似然比（claimed vs 全部竞争模型）
                                                        │
                                        判决 AUTHENTIC / SUSPICIOUS / MISMATCH / INCONCLUSIVE
```

- **tier-1 确定性层**：`usage` 自报 token 曲线（20 篇 canonical 文本，CJK 分歧最大）、
  chat template 开销、max_tokens 限额、logprobs/n 参数支持、错误码族
- **tier-2 行为层**：思维链形态、风格标记、reasoning 字段
- **混淆集比较**是方法核心：冒充者通常与目标同家族（r1 冒充 v3），"像不像"没有意义，
  "证据更支持谁"才有意义；且 claimed 总分低于硬地板时直接 MISMATCH——
  **token 层再像也淹没不了行为层的全面矛盾**（mock 实验可复现）
- **零权重展示项**：响应体 `model` 字段回显——改字段是最廉价的伪造，报告里可见但不计分

内置 mock 服务器（Aqua/Breeze 双人格）完整演示四种场景：诚实 → AUTHENTIC；
换模型中转 → MISMATCH（runner-up 正确指向替代模型）；只改 model 字段 → 仍 AUTHENTIC；
**伪造 usage 的完美说谎中转 → 仍 MISMATCH（行为/错误层暴露）**。

## 批量审计 / Audit

月度《中转站验真报告》的生产工具：CSV 目标清单 → 受控并发 → 可发布报告（逐端点证据链哈希）：

```csv
name,base_url,model,key_env
relay-a,https://a.example.com/v1,deepseek-chat,KEY_A
relay-b,https://b.example.com/v1,deepseek-chat,
```

```bash
sothstan audit targets.csv -o report.md --json-out report.json --max-workers 4
# 退出码：0 全部 AUTHENTIC / 1 含 SUSPICIOUS / 2 含 MISMATCH / 3 全部 INCONCLUSIVE

```

## 对抗模式 / Adversarial

canonical 文本池是公开的——中转可以对固定文本预置答案。`--adversarial` 让 token
探测改用**按 seed 确定性生成**的对抗文本（混合文种、ZWJ emoji 序列、组合字符、
罕见 CJK 区块、全角形式——tokenizer 分歧最大的类别）：

```bash
# 基线与验证必须同模式；换 --seed 即轮换探测集

sothstan collect https://api.official.com/v1 --model m1 --family f \
    --out baselines/m1.json --adversarial --seed 777 --api-key-env K1
sothstan check https://relay.example.com/v1 --model m1 --adversarial --seed 777
```

- 同 seed 同文本：证据链可复现（fuzz 测试锁定确定性）
- 模式不一致时判决会附诚实警示（基线与运行的 token 曲线不可比）
- 诚实边界：字符池公开，安全性不靠保密，靠"探测集随 seed 轮换"的不可预置性

## 诚实边界 / Honesty

- 指纹验证是**统计证据，不是数学证明**——判决阈值全部公开（`verdict.THRESHOLDS_DOC`）
- 基线必须来自官方端点；内置 `_demo_*.json` 是 mock 人格指纹，**不代表任何真实模型**
- 军备竞赛真实存在：探测可被识别、转发。对策（种子化换题/多层信号/统计聚合）
  见 [GAP_PROOF.md](GAP_PROOF.md) 第 4 节——部分可检测已远超现状（现状是零）

## 退出码（CI 友好）

| 码 | 含义 |
|---|---|
| 0 | AUTHENTIC |
| 1 | SUSPICIOUS |
| 2 | MISMATCH |
| 3 | INCONCLUSIVE（证据不足/无竞争基线——诚实说不足） |
| 4 | 基础设施错误（端点不可达/基线缺失） |

## 与现有方案的关系 / Landscape

| 方法类别 | 能回答的问题与限制 |
|---|---|
| 检查返回的 `model` 字段 | 能读取端点自报名称；不能单独证明服务端实际模型 |
| 固定提示词探测 | 可观察部分响应差异；结果会受参数、版本和服务端策略影响 |
| Sothstan | 将多个信号与可信基线比较，并报告判决、边界和可复现记录；不是密码学身份认证 |

## 路线图 / Roadmap

见 [ROADMAP.md](ROADMAP.md)。当前 v0.1.0rc1：5 探测器 + 混淆集判决 + mock 全链路 + CLI，
41 项测试全绿。接下来：对抗文本模式、对抗实验矩阵、批量审计、官方基线流水线。

## 开发 / Development

```bash
pip install -e ".[dev]"
./.venv/Scripts/python.exe -m pytest -q        # Windows Git Bash
./.venv/Scripts/python.exe -m ruff check src tests tools
./.venv/Scripts/python.exe tools/gen_demo_baselines.py   # 重新生成 demo 基线
```

## 反馈与参与

使用问题和功能建议可以在 [Discussions](https://github.com/cloudydreamland/TheTrialOfTheHiddenVoice/discussions) 交流；可复现缺陷请提交 [Issue](https://github.com/cloudydreamland/TheTrialOfTheHiddenVoice/issues)。请只附合成或脱敏后的最小样例，不要上传真实个人信息、API key 或业务原文。安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

## License

MIT
