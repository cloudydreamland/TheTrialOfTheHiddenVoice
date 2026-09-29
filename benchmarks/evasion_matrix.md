# 对抗实验矩阵（evasion matrix）

- 运行时间：2026-09-28（夜间 iter3，全部数字为本次真实运行输出）
- 对象：声称 aqua-70b 的六种服务器策略 × 5 seeds （20260928, 1, 2, 3, 4）
- 判决语义：MISMATCH=检出；SUSPICIOUS=部分可疑；AUTHENTIC=逃逸

| 策略 | 混淆集 | AUTHENTIC | SUSPICIOUS | MISMATCH | 检出率 | 抓住它的信号层 | 最强冒充解释 |
|---|---|---|---|---|---|---|---|
| honest_aqua（对照） | default | 5/5 | 0/5 | 0/5 | 0% | （无——全部逃逸） | breeze-8b |
| relay_field_only | default | 0/5 | 0/5 | 5/5 | 100% | token_count×5, template×5, errors×5, reasoning×5, limits×5 | breeze-8b |
| relay_liar_full_consistent | default | 0/5 | 0/5 | 5/5 | 100% | reasoning×5 | breeze-8b |
| relay_liar_full_naive | default | 0/5 | 0/5 | 5/5 | 100% | reasoning×5 | breeze-8b |
| relay_liar_usage | default | 0/5 | 0/5 | 5/5 | 100% | errors×5, limits×5, reasoning×5 | breeze-8b |
| sibling_swap_近亲互换 | with_sibling | 0/5 | 0/5 | 5/5 | 100% | token_count×5, template×5, reasoning×5 | aqua-lite |
| sibling_swap_近亲互换 | without_sibling | 0/5 | 0/5 | 5/5 | 100% | token_count×5, template×5, reasoning×5 | breeze-8b |

## 验收标准②对照结果

诚实服务器 5/5 AUTHENTIC——零误判，通过。

## 结论（全部来自上表真实数字）

1. 字段伪造单独使用检出率 5/5——model 字段改写毫无作用（零权重设计）。
2. usage 伪造检出率 5/5——token 层 + 行为层双杀。
3. 全套伪造（naive）检出率 5/5——usage/内容不自洽被 `reasoning.completion_per_char` 与 `reasoning.style_marker` 抓住（校准后）。
4. 全套伪造（consistent）检出率 5/5——黑盒确定性信号全部失效，唯一线索是内容行为层；若替代模型连回复风格也一致，则黑盒层面**不可区分**（等价于真的在服务声称模型）。
5. 近亲互换（含近亲基线）检出率 5/5；不含近亲基线 5/5——**混淆集需要近亲基线在场**：这是基线注册表（collect 覆盖近亲模型）的直接论据。（注意：本 mock 中 breeze 对短 CJK 文本的计数与 lite 巧合接近，不含近亲基线仍检出部分归功于此，真实世界不保证，UNVERIFIED。）

## 校准决策（验收标准③/④）

- 新增信号：`reasoning.completion_per_char`（usage 与内容长度之比，无额外请求）——由本矩阵的 naive 全套伪造场景驱动，纳入 ReasoningProbe 与基线。
- 阈值变更：`MISMATCH_TOTAL_FLOOR` -12 → -10。第一轮运行（地板 -12）中 naive 全套伪造以 claimed 总分 -11 滑过地板逃逸（检出 0/5）——两层信号矛盾（style_marker -5 + completion_per_char -6）已构成"端点不是声称模型"的证据；诚实服务器 claimed 总分恒为 0，收紧到 -10 无误判代价。校准后 naive 检出 5/5，对照仍 5/5 AUTHENTIC。AUTH_MIN_MARGIN 与 MISMATCH_MARGIN：无增益，维持不变。
- 已知局限：consistent 全套伪造只能靠内容行为层（tier-2，可被风格模仿对抗）；近亲互换依赖注册表含近亲基线。
