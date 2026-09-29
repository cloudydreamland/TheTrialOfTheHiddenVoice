# ROADMAP — 夜间自动化迭代驱动表

> 规则：自动迭代每一轮从上到下找第一个未勾选条目，完整做完（代码+测试+文档）再勾选。
> 每条目设计为一轮（≤55 分钟）可完成。做完更新 WORKLOG.md 并提交。
> 每轮固定动作：① 选条目实现；② **对抗评审**（资深开发者/资深项目经理/公司老板三视角挑刺，
> 可上网核查 modelprint/TokHub/relay-radar/llm-verify 等竞品动态，结论写入 WORKLOG"评审记录"）；
> ③ 有效批评转化为新条目追加到表末尾；④ 全量 pytest + ruff 必须绿；⑤ git 提交。
> 环境提示：本机 Windows + Git Bash；测试命令 `./.venv/Scripts/python.exe -m pytest -q`；
> lint `./.venv/Scripts/python.exe -m ruff check src tests tools`。
> 本机环境变量中没有官方 LLM API key——今晚**不做真实基线采集**，全部离线 mock 驱动。

## 迭代条目

- [x] **iter0（2026-09-28 凌晨，主会话完成）**：核心框架全部落地——零依赖 OpenAI 兼容客户端
  （预算双熔断 + 证据链转录 + key 脱敏）、5 个探测器（token 曲线/模板开销/限额/错误码族/行为层，
  tier 分级）、混淆集似然比评分（claimed vs 全部竞争模型，margin 判决 + claimed 总分硬地板）、
  基线注册表（schema 校验 + demo 标签隔离）、mock 双人格服务器 + 三种服务器形态
  （诚实/换模型中转/完美说谎中转）、报告渲染（JSON/Markdown + 自动诚实声明）、
  CLI（check/collect/list-baselines/selftest，CI 友好退出码）、demo 基线生成工具。
  41 项测试全绿 + ruff 清零；selftest 四个攻击场景全 PASS。
- [x] **iter1（2026-09-28 02:14–02:25，夜间第 1 轮）— 对抗评审 #1 + 修复**：三视角评审
  + 竞品实抓（modelprint 124★ 活跃/PyPI `sothstan`+`taosha` 均可注册/3 篇新论文）。
  修复：客户端瞬时错误重试（429/5xx，确定性退避，转录全记）+ 探测层 "transient" 隔离
  + weight schema 校验 + timeout/retries/--version 透传 + JSON 报告 exit_code
  + README selftest 前置 + 法务声明条款；转化：iter3 验收标准、新条目
  iter8（徽章）/iter9（reasoning 适配）/iter10（KBF 知识边界探针）/iter11（四阶段协议对齐）。
  49 测试全绿（+8）。详见 WORKLOG 评审记录。
- [x] **iter2（2026-09-28 03:14–03:35，夜间第 2 轮）— 对抗性文本模式**：确定性生成器
  （六类高分歧素材 + 类别不变量断言 + fuzz 30 seeds）、token 探测 `--adversarial` 接入
  （meta 记 mode/seed）、模式不一致诚实警示、CLI 双命令支持、selftest 第 5 场景。
  评审抓到并修复 collect/verify seed 注入不一致真 bug（对抗往返假 MISMATCH）。
  新增 iter12（seed 轮换策略）。56 测试全绿。
- [x] **iter3（2026-09-28 04:14–04:50，夜间第 3 轮）— 对抗实验矩阵**：6 策略 × 5 seeds
  = 35 次真实运行。四条验收标准全过：检出率+信号层归因、对照零误判（5/5 AUTHENTIC）、
  阈值变更留痕（硬地板 -12→-10，naive 全套伪造以 -11 滑过旧地板逃逸的实验证据）、
  无增益项如实记录（两条 margin 阈值不变）。新增 `reasoning.completion_per_char`
  自洽信号。关键发现：consistent 全套伪造仅剩内容行为层可检（黑盒上界命题）；
  近亲互换依赖注册表收录近亲基线。新增 iter13（README 引用矩阵）。56 测试全绿。
- [x] **iter4（2026-09-28 05:14–05:40，夜间第 4 轮）— 批量审计 sothstan audit**：CSV 目标
  清单（utf-8-sig/缺列校验/BOM 兼容）→ ThreadPoolExecutor 受控并发（注册表单次加载共享，
  单目标失败不拖垮整批）→ 可发布报告（Markdown 摘要含证据链哈希 + JSON 全量信号证据 +
  法务条款自动附加）+ 审计口径退出码 0/1/2/3。mock 端到端：2 诚实 + 1 换模型中转 →
  2 AUTHENTIC + 1 MISMATCH（runner-up 正确）、退出码 2。65 测试全绿。新增 iter14
  （批量总超时 + 徽章/audit 出证闭环）。
- [ ] **iter5 — 基线工程化**：`sothstan diff`（基线快照间差异/漂移警报）；collect 韧性
  （部分失败/限速重试/断点）；`docs/baseline_refresh.md` 附 GitHub Actions nightly 官方基线
  采集模板（用户提供 key 后启用）。
- [ ] **iter6 — 文档与发布工程**：README_EN；`docs/audit_methodology.md`（点名标准：
  证据阈值/置信声明/回应渠道/复核流程）；`docs/launch_checklist.md`
  （V2EX/知乎/即刻/X/HN 文案要点）；GitHub Action 用法示例。
- [x] **iter7（2026-09-28 07:14–07:20，夜间最后一轮）— 终版复盘**：65 测试全绿、
  ruff 清零、selftest 5/5；REPORT.md 终版；终版评审记录见 WORKLOG。

## 收尾条目

- [x] **wrap-up（已完成）**：REPORT.md 终版 + 终版提交完成（07:20）。

## 评审追加条目（iter1）

- [ ] **iter8 — 徽章生成**：`sothstan badge`：对通过验证的端点生成 "verified by Sothstan"
  SVG 徽章（含验证日期 + 证据哈希前 8 位），供诚实中转站自证并回链仓库——
  被验证方替我们分发（老板评审的 star 增长机制）。
- [ ] **iter9 — reasoning 模型适配**：部分推理模型在 max_tokens=1 下必然报错
  （思考 tokens 挤占预算），token 探测遇此应自动升到自适应上限并把"使用了升格"
  写进信号 meta 与基线（开发者评审的测试盲区）。
- [ ] **iter10 — 知识边界探针（KBF 风格）**：参考 arXiv:2605.29524（KBF）与
  arXiv:2608.31142（四阶段黑盒身份协议），实现 knowledge-cutoff 探针族作为 tier-2
  信号；README/GAP_PROOF 引用四篇 2026 论文站住学术位置。
- [ ] **iter11 —（文献落地）四阶段协议对齐**：读 arXiv:2608.31142，把其协议阶段映射到
  sothstan 的探测计划（probe plan），在 docs/probe_design.md 增加对照表——
  "我们实现了该协议的哪几阶段、差在哪"，作为学术对话的诚实起点。
- [ ] **iter12 —（iter2 评审追加）seed 轮换策略**：对抗模式的默认 seed 固定使对抗性
  退化为 canon；设计 auto 轮换模式并写下与可复现性的权衡文档（报告已记录 seed，
  auto 模式下证据链以"seed+文本"重放复现），给生产部署的轮换指引。
- [ ] **iter13 —（iter3 评审追加）README 引用对抗矩阵**：把 evasion_matrix 的核心数字
  （四种伪造策略 5/5 检出、对照零误判）写进 README 首屏与徽章页——用实测数字替代形容词。
- [ ] **iter14 —（iter4 评审追加）audit 收尾**：批量级总超时（--total-timeout，防慢端点
  拖长整批）；徽章（iter8）支持由 audit 报告哈希背书——"被验证方自助出证"闭环。

## 用户醒来后的人工事项

- 注册 GitHub 仓库并 push；PyPI 发布需用户 token
- 用官方 API key 采集真实基线（deepseek/glm/qwen/kimi 系至少各 1 个 +
  主要近亲混淆对），填入注册表
- 首篇《中转站模型验真报告》需要用户决定发布渠道与法务边界
