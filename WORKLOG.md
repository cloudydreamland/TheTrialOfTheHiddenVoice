# WORKLOG — Sothstan

## iter7 / wrap-up（2026-09-28 07:14–07:20，夜间最后一轮）：终版复盘

### 终版评审记录（三视角，针对整夜产出）

**竞品核查（收尾实抓）**：modelprint 124★ / pushed 2026-09-27T09:17:35Z——**整夜零变化**
（与 iter1/2/3 轮实抓完全一致）；llm-verify 35★ / pushed 2026-09-21——无动作。
竞品整夜静止，我们的五轮迭代相当于在静态窗口里拉开了身位；但 modelprint 的推送
停在 9/27 而非更早，说明作者仍活跃，发布速度仍是第一优先级。

**资深开发者**：① 全夜 5 轮提交每轮测试全绿（41→49→56→65），无一次红着提交；
两次真 bug（seed 注入不一致、-11 滑过 -12 地板）都被测试/实验当场抓住——
验证了"测试先行 + 对抗实验"流程本身；② 未竟的架构债已显式登记
（collect/verify options 组装重复 → iter14；批量总超时 → iter14），未悄悄欠账。

**资深项目经理**：① 五轮条目全部闭环，验收标准（iter3 四条）逐条有数字落点；
② REPORT.md 的"诚实未完成项"如实列出零真实基线这一最大局限——
不夸大、不隐藏，符合项目的诚实文化定位；③ 文档链完整：
GAP_PROOF（为什么做）→ ROADMAP（怎么做）→ WORKLOG（做的时候发生了什么，
包括失败）→ REPORT（交付了什么）→ benchmarks（数字证据）。

**公司老板**：① 差异化叙事已成型且全部有证据背书："四种伪造策略 5/5 检出、
诚实对照零误判、证据链哈希可复现"——竞品（modelprint 9 项静态探测/124★）
没有统计判决、混淆集、证据链三件套中的任何一个；② PyPI 双名可用 +
竞品静止 = 明早发布的时间窗；③ 法律条款（不构成指控）已在报告模板自动附加，
月度审计的法务边界是唯一需要用户本人拍板的事项。

### 终版状态

- pytest 65 passed / ruff 0 error / selftest 5/5 PASS
- 未完成项与人工事项见 REPORT.md（诚实清单）

## iter4（2026-09-28 05:14–05:35，夜间自动化第 4 轮）：批量审计 sothstan audit

### 实现内容

- `audit.py`：CSV 目标清单解析（utf-8-sig、缺列/空行/缺值如实收集）、
  ThreadPoolExecutor 受控并发（注册表只加载一次共享）、单目标失败不拖垮整批
  （失败/缺基线也是一行，error 字段如实记录）、汇总报告（Markdown 可发布模板 +
  JSON 全量证据）、审计口径退出码（0/1/2/3，见模块 docstring）。
- CLI：`sothstan audit targets.csv -o report.md --json-out report.json --max-workers 4`，
  支持 --registry/--seed/--timeout/--retries/--adversarial/--include-demo。
- 报告：汇总表（目标/判决/margin/最强竞争解释/证据链哈希前 8 位）+ 逐端点完整
  信号证据在 JSON + 诚实声明（含"不构成法律指控"条款）自动附加。
- README 增"批量审计"章节。

### 评审记录（三视角）

**竞品核查**：relay-radar 140★ / pushed_at 2026-09-21T08:55:38Z（与 iter1 实抓一致，
无推送变化）；modelprint 已连续三轮无动作（124★，9/27）。竞品无"批量审计+证据链"
形态的公开动作（UNVERIFIED：未逐一复查全部仓库）。

**资深开发者**：
1. 【有效批评】并发跑批对同一注册表是只读共享——线程安全成立；但 ThreadPoolExecutor
   + 每目标 20+ 请求 × N 目标，默认 max_workers=4 在慢端点上总时长可能超长，
   CLI 未提供总超时——已记为已知局限（单请求 timeout 已可调，批量级总超时转 iter14）。
2. 【有效批评】audit_one 在函数体内 `import os`——不规范（本次顺手修，见下）。
3. 测试盲区：CSV 带 BOM（Windows 记事本保存）场景——utf-8-sig 已覆盖，但无测试；
   顺手补了一个 BOM 用例（当场修）。

**资深项目经理**：
1. 交付可验证：3 目标（2 诚实 + 1 换模型中转）mock 端到端测试——summary 正确
   （2 AUTHENTIC + 1 MISMATCH）、runner-up 指认正确、退出码 2、报告含法务条款。
2. "报告模板可发布"验收点：Markdown 由工具生成、含 seed 与注册表快照（可复现口径），
   JSON 含逐信号证据——满足。
3. 范围未蔓延：未提前做 iter5 的 diff 功能。

**公司老板**：
1. audit 是月度报告飞轮的生产工具，也是"被验证方自助出证"的基础（诚实中转站
   可以自己跑 audit 出报告挂徽章）——与 iter8 徽章条目天然衔接，徽章应支持
   "由 audit 报告哈希背书"——转化为 iter14 的一部分（见下）。
2. 差异化核查：relay-radar 定位是"监控/评分"，无证据链与统计判决；audit + 证据链
   哈希的组合仍是空白（基于公开 README，UNVERIFIED：其闭源部分未知）。

### 本轮完成清单

- audit.py（解析/并发/汇总/退出码）+ CLI audit 子命令 + 8 个新测试（64 passed 全绿）
- README 批量审计章节

### 诚实未完成项

- 批量级总超时未实现（慢端点会拖长整批，iter14）
- 真实端点的 audit 未跑（无官方 key 与目标清单——这本来就是用户醒来后的动作）
- audit 报告与徽章的背书联动未做（iter14）

## iter3（2026-09-28 04:14–04:50，夜间自动化第 3 轮）：对抗实验矩阵 + 权重校准

### 实验结果（35 次真实运行，全部数字见 benchmarks/evasion_matrix.md/.json）

| 策略 | 检出率 | 抓住它的信号层 |
|---|---|---|
| honest_aqua（对照） | 0% 误判（5/5 AUTHENTIC） | — |
| relay_field_only（只改字段） | 5/5 | 全层（token/template/errors/reasoning/limits） |
| relay_liar_usage（伪造 usage） | 5/5 | errors + limits + reasoning |
| relay_liar_full_naive（全套伪造，usage 不自洽） | 5/5（校准后；校准前 **0/5 逃逸**） | reasoning（completion_per_char + style_marker） |
| relay_liar_full_consistent（全套伪造+重算 usage） | 5/5 | 仅 reasoning 内容行为层（tier-2） |
| sibling_swap（同家族近亲互换） | 5/5（含/不含近亲基线均检出） | token_count + template + reasoning |

四条验收标准逐条：① 检出率+信号层归因 ✅（上表）；② 5 seeds 诚实对照零 AUTHENTIC 误判 ✅；
③ 阈值变化留痕并给理由 ✅（硬地板 -12→-10，见下）；④ 无增益项如实写 ✅
（AUTH_MIN_MARGIN 与 MISMATCH_MARGIN 校准无增益，维持不变）。

### 本轮最重要的两个发现

1. **校准前 naive 全套伪造 0/5 检出（逃逸）**：claimed 总分 -11 差 1 分滑过 -12 硬地板。
   且第一版结论文案是预写的"被抓住"——与数字矛盾，被本轮诚实文化检查拦下重写。
   校准：地板 -12 → -10（依据：两层信号矛盾已构成充分证据；诚实服务器 claimed 总分
   恒为 0，收紧零误判代价）。校准后 naive 5/5 检出、对照仍 5/5。
2. **新增信号 `reasoning.completion_per_char`**（completion_tokens×1000//len(content)）：
   抓"伪造 usage 但不按真实内容重算"的中转——零额外请求，由实验场景驱动。

### 评审记录（三视角）

**竞品核查**：modelprint 124★ / pushed_at 2026-09-27T09:17:35Z——连续三轮无变化。
**资深开发者**：① LiarFullServer 放在实验工具而非包内——正确边界（攻击模拟器不该随
pip 分发），但 consistent 变体的存在说明内容层可被风格模仿对抗，已写进矩阵"已知局限"；
② 近亲互换"不含近亲基线仍 5/5 检出"部分归功于 mock 巧合（breeze 对短 CJK 的计数
与 lite 接近），已在结论中如实标注 UNVERIFIED——真实世界必须靠注册表收录近亲基线；
③ reasoning 探测现在发 3 个信号但只有 1 次请求，信号生成成本为零——设计达标。
**资深项目经理**：① 四条验收标准全部有数字落点，本轮里程碑可验证性达标；② benchmarks/
evasion_matrix.md 由工具生成而非手写——数字与工具输出同源，杜绝手抄漂移（延续 qiegao
(results.md) 的做法）；③ 范围未蔓延（仅 iter3 条目 + 校准闭环）。
**公司老板**：① 矩阵是给用户的"信任面"：README 应引用矩阵结论（"四种伪造策略 5/5 检出"
比任何形容词有力）——转化为新条目 iter13（README 引用矩阵 + 徽章页整合）；
② consistent 全套伪造是理论上的黑盒上界（除非替代模型连风格也一致 = 等价于真服务），
这是可以直接写进论文的命题——学术联动价值高于预期，iter11 协议对齐时应引用本轮矩阵。

### 本轮完成清单

- mockserver：AQUA_LITE 同家族近亲人格（行为/错误层与 Aqua 完全一致，仅计数层 ~6% 偏移）
- reasoning 探测：新增 completion_per_char 自洽信号（demo 基线已同步重采）
- tools/evasion_matrix.py：6 策略 × 5 seeds × 混淆集变体 = 35 次运行，产出 md+json
- verdict.py：MISMATCH_TOTAL_FLOOR -12 → -10（实验驱动，理由留痕）
- 测试 56 passed 全绿，ruff 0 error

### 诚实未完成项

- 全部结论基于 mock 人格；真实模型上的信号分歧幅度未验证（需官方 key 采基线后复跑矩阵）
- 近亲互换"无近亲基线仍检出"含 mock 巧合成分（已标注）
- consistent 攻击的风格模仿上界未做自动化实验（人工论证）

## iter2（2026-09-28 03:14–03:35，夜间自动化第 2 轮）：对抗性文本模式 --adversarial

### 实现内容

- `probes/adversarial.py`：确定性对抗文本生成器——按 seed 生成（同 seed 同文本，
  fuzz 30 seeds 锁定），每条混合六类 tokenizer 高分歧素材：常用 CJK + 罕见 CJK 区块、
  ASCII 词串、长数字串、单 emoji + ZWJ 组合序列、全角形式、分解组合字符（e+U+0301）；
  内置类别不变量断言（每条必含 CJK 与 ASCII）。
- token 探测接入：`--adversarial` 时探测文本改用生成器（信号 meta 记
  `mode: adversarial` + seed），canon 模式行为不变。
- **模式不一致警示**：基线与运行模式不同（canon vs adversarial）时，判决附诚实警示
  （token 曲线不可比），不沉默、不阻断。
- CLI：check/collect 增 `--adversarial`；selftest 增第 5 场景（对抗模式往返 → AUTHENTIC）。
- README 增"对抗模式"章节（含同模式采集要求与诚实边界）。

### 评审记录（三视角）

**竞品核查（本轮实抓）**：modelprint 124★ / pushed_at 2026-09-27T09:17:35Z——
与 1 小时前完全一致，无新动作。其余竞品（TokHub 208★/relay-radar 140★/llm-verify 35★）
上一轮已实抓，本轮无变化信号（UNVERIFIED：未逐一复查）。

**资深开发者视角**：
1. 【真 bug，测试先红后绿】collect 路径未把 seed 注入 options——对抗模式采集用默认
   seed 20260928、验证用传入 seed，同参数往返得到假 MISMATCH（claimed 总分 -100.4
   触发硬地板）。**修复**：collect_baseline_signals 注入 options.setdefault("seed", seed)。
   教训记录：collect 与 verify 各自组装 options 是重复逻辑，长期应提统一 builder
   （本轮不做大重构，记录待办）。
2. ZWJ emoji 序列经真实 API 传输层可能被归一化/截断——mock 无法验证，UNVERIFIED；
   现有缓解：类别不变量断言 + 单条失败仅跳过。转化：iter10 的 KBF 探针落地时一并
   做"真实端点行为核查清单"。

**资深项目经理视角**：
1. 交付可验证性达标：fuzz 确定性（30 seeds）、对抗往返 AUTHENTIC、模式不一致警示、
   CLI 往返退出码，全部有测试锁定。
2. 文档 5 分钟路径不受影响（selftest 仍是第一步，对抗模式为进阶章节）。
3. CLI 往返测试最初漏 `--include-demo` 导致假失败（默认注册表只有 demo 基线，
   无竞争者 → 诚实 INCONCLUSIVE exit 3）——已修测试；这提醒 demo 基线默认排除的
   设计对新手有摩擦，但诚实语义优先，保持。

**公司老板视角**：
1. 差异化叙事成立："探测集随 seed 轮换，中转无法预置答案"一句话可讲，且 modelprint
   的 9 项静态探测不具备此性质。
2. 【有效批评】默认 seed 固定 = 用户不主动换 seed 时对抗性退化。但 seed 随机化与
   可复现性存在张力（随机 seed 每次换题 → 证据链失去复现基准）。**转化**：新条目
   iter12——seed 轮换策略设计（auto 模式的权衡文档 + 报告记录 seed 的规范），
   默认保持可复现优先。

### 本轮完成清单

- 新增 adversarial.py + 7 个测试（56 passed 全绿，ruff 0 error）
- 修复 collect/verify seed 注入不一致真 bug
- selftest 5 场景全 PASS

### 诚实未完成项

- 对抗文本经真实 API 的传输行为（ZWJ/组合字符存活性）未验证——需要官方 key 后实采
- seed 轮换的默认体验张力未解决（iter12）
- options 组装逻辑 collect/verify 双份（重构待办，非紧急）

## iter1（2026-09-28 02:14–02:25，夜间自动化第 1 轮）：对抗评审 #1 + 修复

### 评审记录（三视角）

**竞品情报（后台代理实抓，2026-09-28 凌晨）**：modelprint 124★（9/27 仍在推送，活跃）；
TokHub 实际 owner 为 yaojingang/TokHub（208★，8/19 后无推送）；relay-radar 140★（9/21 推送）；
llm-verify 35★（9/21 推送）；new-api 48,973★（生态参照）。**PyPI：`sothstan` 与 `taosha`
均 404 未被占用，可注册**（本轮评审最重要的好消息之一）。新文献：arXiv:2609.20457
（多模态指纹，ACM MM 2026）、arXiv:2608.31142（四阶段黑盒身份协议）、arXiv:2605.29524
（KBF 知识边界指纹，16 生产端点审计）——后两篇与我们的方法论直接相关，已转为 ROADMAP
iter10/iter11。除 modelprint 外无 >50★ 新进入者（部分搜索 429 限流，覆盖度受限，UNVERIFIED）。

**资深开发者视角（挑刺 → 修复）**：
1. 【致命】HTTP 客户端零重试：中转站限流的 429 会被 errors 探测当作"错误码族指纹"记录
   ——用负载噪声污染指纹比较。**修复**：客户端对 429/5xx/网络错误做确定性退避重试
   （默认 2 次，0.5×2^k 秒，每次尝试进转录）；重试耗尽后 errors/limits 探测记固定类别
   `"transient"`（不区分模型、不冒充指纹）。FlakyServer + 3 个新测试锁定。
2. 基线 schema 不校验 weight 类型（字符串 weight 会在评分期才崩）。**修复**：validate 阶段拦截。
3. 挂死端点会以 60s×N 拖垮整轮探测。**修复**：verify/CLI 暴露 timeout（默认 30s）与 retries。
4. 测试盲区：`--probes` 子集路径零覆盖。**修复**：新增子集测试；过程中发现并锁定一个
   行为学问题——errors 单探测器（4 个 tier-1 信号）全精确命中即判 AUTHENTIC，
   宽松度是否收紧交 iter3 对抗实验量化后定夺（已写为测试注释与 ROADMAP 验收标准）。

**资深项目经理视角（挑刺 → 修复/转化）**：
1. README 5 分钟上手路径错误：把需要官方 key 的 collect/check 放在 selftest 之前。
   **修复**：selftest 提为快速开始第一步。
2. iter3"权重校准"缺可验收的完成定义（范围蔓延风险）。**修复**：iter3 增加四条验收标准
   （逐策略检出率、≥5 seed 零误判、阈值变化留痕、无增益须如实写）。
3. JSON 报告缺 exit_code，CI 用户要自己映射。**修复**：result_to_dict 增加 exit_code。

**公司老板视角（挑刺 → 转化）**：
1. modelprint 仍在活跃推送（9/27）——窗口不是无限的，速度是第一优先级（与 qiegao
   GAP_PROOF 同款结论）。防御 = 基线资产 + 证据链 + 审计方法学的组合壁垒，加速 iter4/iter6。
2. "verified by Sothstan" 徽章是最便宜的分发杠杆，但 iter0 没有任何落地物。**转化**：新 iter8。
3. 法务边界：输出可能被用于点名指控。**修复**：诚实声明追加"不构成法律指控"条款。

### 本轮完成清单

- http.py：ApiError.transient（TRANSIENT_STATUSES）+ 客户端重试（确定性退避，转录全记）
- probes（errors/limits）：瞬时错误 → "transient" 固定类别
- baseline.py：weight 数值校验；runner/cli：timeout/retries/--timeout/--retries/--version 透传
- report.py：JSON 增 exit_code；诚实声明增"不构成法律指控"
- mockserver.py：FlakyServer（前 N 次 429）
- README：selftest 前置；ROADMAP：iter3 验收标准 + 新增 iter8/iter9/iter10/iter11
- 新测试 8 个：重试成功/不重试即抛/持续限流记 transient/子集 INCONCLUSIVE/
  errors-only AUTHENTIC 行为锁定/weight 校验/exit_code/--version

### 测试状态

49 passed / ruff 0 error（较 iter0 +8 测试）。

### 诚实未完成项

- 重试退避是确定性 0.5×2^k（无抖动）：对真实世界足够，但生产级限流场景未实测
- "errors-only 即 AUTHENTIC" 的宽松度未校准（iter3）
- 竞品搜索部分查询被 429 限流，"无其他新进入者"的结论覆盖度受限
- iter8-iter11 未开始

## iter0（2026-09-28 00:44–02:20，主会话）

### 完成清单

- 包骨架（src layout / pyproject / CI-ready / MIT / py.typed）
- `http.py`：零依赖 OpenAI 兼容客户端；请求/prompt-token 双预算熔断
  （BudgetExceeded 继承 BaseException 以穿透探测器兜底）；证据链转录
  （记录 url/headers/body/response，key 脱敏，哈希排除 latency 保证确定性）
- `probes/`：token_count（20 篇 canonical 文本 token 曲线，weight 2.0 + completion）、
  template（空消息/系统开销/多轮增长）、limits（巨型 max_tokens/logprobs/n/model 回显零权重）、
  errors（温度越界/未知参数/空消息/非法角色的错误码族）、reasoning（completion tokens/
  风格标记/reasoning 字段）
- `compare.py`：混淆集似然比评分。int_vector 逐元素精确匹配主导（-6 地板/元素）、
  categorical -5、bool -4；margin = weight × (claimed − 最强竞争者)
- `verdict.py`：公开阈值判决——覆盖率门槛（tier-1 < 3 → INCONCLUSIVE）、
  **claimed 总分硬地板（≤ −12 → MISMATCH，防 token 层淹没行为层矛盾）**、
  margin ≥ +8 且精确率 ≥ 0.6 → AUTHENTIC、无竞争基线 → INCONCLUSIVE
- `baseline.py`：schema 校验 + 注册表加载 + demo 标签（真实判决默认排除 demo 基线）
- `mockserver.py`：Aqua/Breeze 双人格（伪 tokenizer 按字符类别比率）+
  三种服务器形态（诚实/换模型中转/完美说谎中转）
- `report.py`：JSON + Markdown，自动附加诚实声明
- `cli.py`：check/collect/list-baselines/selftest；退出码 0/1/2/3/4
- `tools/gen_demo_baselines.py`：对 mock 人格走真实采集管线生成 demo 基线

### 测试状态

41 passed / ruff 0 error；`sothstan selftest` 四场景全 PASS
（诚实→AUTHENTIC、换模型→MISMATCH/breeze-8b、改字段→AUTHENTIC、伪 usage→MISMATCH）。

### 开发中当场抓住的 bug（测试先行驱动）

1. 循环导入（`__version__`）→ 拆 `_version.py`
2. `ThreadingHttpServer` 拼写 → `ThreadingHTTPServer`
3. **方法学缺陷**：完美说谎中转仅判 SUSPICIOUS——token 层 20 元素的大分差在
   margin 里淹没了行为层全面矛盾 → 引入 claimed 总分硬地板规则
4. BudgetExceeded 被探测器 `except Exception` 吞掉 → 改继承 BaseException
5. 证据链哈希含 latency 不稳定 → 哈希排除 latency
6. transcript 未记录 headers（无可脱敏对象）→ 记录 url+headers+body
7. Verdict.to_dict 漏 notes → 补
8. load_registry(None) TypeError → 默认值处理

### 诚实未完成项

- 真实模型基线为零（本机无官方 API key）——注册表只有 demo 基线
- 对抗性文本模式、批量审计、基线 diff 未做（ROADMAP iter2-5）
- 权重/阈值是工程先验，未经大规模对抗实验校准（iter3）
- 未实测任何真实中转站（需要用户授权与法务边界决策）
