"""命令行入口。

退出码（CI 友好）：
- 0 AUTHENTIC / 1 SUSPICIOUS / 2 MISMATCH / 3 INCONCLUSIVE / 4 基础设施错误
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sothstan.baseline import load_baseline, load_registry
from sothstan.mockserver import AQUA, BREEZE, shutdown_server, start_server
from sothstan.report import render_markdown, result_to_dict
from sothstan.runner import EXIT_CODES, collect_and_save, verify
from sothstan.verdict import VerdictLabel


def _key_from_env(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name)
    if not value:
        print(f"警告: 环境变量 {name} 未设置，将以匿名方式请求", file=sys.stderr)
    return value


def cmd_check(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    if args.baseline:
        baseline = load_baseline(args.baseline)
    else:
        if args.model not in registry:
            print(
                f"错误: 注册表中没有 {args.model} 的基线。请先对官方端点执行 sothstan collect。",
                file=sys.stderr,
            )
            return EXIT_CODES["ERROR"]
        baseline = registry[args.model]
    if baseline.model_id != args.model:
        print(
            f"错误: 基线的 model_id ({baseline.model_id}) 与 --model ({args.model}) 不一致。",
            file=sys.stderr,
        )
        return EXIT_CODES["ERROR"]
    # 混淆集 = 注册表中除声称模型外的全部基线；demo 基线默认不参与真实判决
    rivals = [
        b
        for mid, b in registry.items()
        if mid != args.model and (args.include_demo or not b.is_demo)
    ]
    result = verify(
        base_url=args.base_url,
        model=args.model,
        baseline=baseline,
        rivals=rivals,
        api_key=_key_from_env(args.api_key_env),
        seed=args.seed,
        probe_names=args.probes.split(",") if args.probes else None,
        max_requests=args.max_requests,
        max_prompt_tokens=args.max_prompt_tokens,
        timeout=args.timeout,
        retries=args.retries,
        options={"adversarial": args.adversarial} if args.adversarial else None,
    )
    report = result_to_dict(result, args.base_url, args.model, args.seed)
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return result.exit_code


def cmd_collect(args: argparse.Namespace) -> Path | int:
    out = collect_and_save(
        base_url=args.base_url,
        model=args.model,
        family=args.family,
        out_path=args.out,
        api_key=_key_from_env(args.api_key_env),
        seed=args.seed,
        tags=[t for t in args.tags.split(",") if t],
        honesty_note=args.honesty_note or "",
        adversarial=args.adversarial,
    )
    print(f"基线已写入: {out}")
    print("提醒: 基线必须采集自官方端点；来路不明的基线会让判决失去意义。")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from sothstan.audit import audit_exit_code, load_targets, render_audit_markdown, run_audit

    targets, problems = load_targets(args.targets)
    if problems:
        for p in problems:
            print(f"错误: {p}", file=sys.stderr)
        return EXIT_CODES["ERROR"]
    report = run_audit(
        targets,
        registry_dir=args.registry,
        include_demo=args.include_demo,
        seed=args.seed,
        max_workers=args.max_workers,
        timeout=args.timeout,
        retries=args.retries,
        adversarial=args.adversarial,
    )
    markdown = render_audit_markdown(report)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"报告已写入: {args.out}")
    if args.json_out:
        import json

        Path(args.json_out).write_text(
            json.dumps(
                {
                    "created_at": report.created_at,
                    "seed": report.seed,
                    "summary": report.summary,
                    "rows": report.rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"JSON 已写入: {args.json_out}")
    if not args.out and not args.json_out:
        print(markdown)
    s = report.summary
    print(
        f"汇总: {s.get('total', 0)} 目标 | AUTHENTIC {s.get('AUTHENTIC', 0)}"
        f" | SUSPICIOUS {s.get('SUSPICIOUS', 0)} | MISMATCH {s.get('MISMATCH', 0)}"
        f" | INCONCLUSIVE {s.get('INCONCLUSIVE', 0)} | 失败 {s.get('errors', 0)}"
    )
    return audit_exit_code(report)


def cmd_list_baselines(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    if not registry:
        print("(注册表为空——用 sothstan collect 采集官方基线)")
        return 0
    for mid, b in registry.items():
        flag = " [demo]" if b.is_demo else ""
        print(
            f"{mid}{flag}  family={b.family}  signals={len(b.signals)}"
            f"  collected={b.collected_at}"
        )
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    """离线自检：mock 服务器上验证整条管线的行为符合预期。"""
    registry = load_registry()
    aqua = registry.get("aqua-70b")
    breeze = registry.get("breeze-8b")
    if aqua is None or breeze is None:
        print("错误: 内置 demo 基线缺失，包安装不完整。", file=sys.stderr)
        return EXIT_CODES["ERROR"]

    checks: list[tuple[str, bool, str]] = []

    s1, url1 = start_server(AQUA)
    try:
        r = verify(url1, "aqua-70b", aqua, [breeze])
        checks.append(("诚实服务器 → AUTHENTIC", r.verdict.label is VerdictLabel.AUTHENTIC,
                       f"got {r.verdict.label.value}"))
    finally:
        shutdown_server(s1)

    s2, url2 = start_server(BREEZE, claim="aqua-70b")
    try:
        r = verify(url2, "aqua-70b", aqua, [breeze])
        checks.append(("换模型中转 → MISMATCH", r.verdict.label is VerdictLabel.MISMATCH
                       and r.verdict.runner_up == "breeze-8b",
                       f"got {r.verdict.label.value}/{r.verdict.runner_up}"))
    finally:
        shutdown_server(s2)

    s3, url3 = start_server(AQUA, claim="some-other-name")
    try:
        r = verify(url3, "aqua-70b", aqua, [breeze])
        checks.append(("仅改 model 字段 → 仍 AUTHENTIC（字段回显零权重）",
                       r.verdict.label is VerdictLabel.AUTHENTIC,
                       f"got {r.verdict.label.value}"))
    finally:
        shutdown_server(s3)

    s4, url4 = start_server(BREEZE, claim="aqua-70b", liar_usage=AQUA)
    try:
        r = verify(url4, "aqua-70b", aqua, [breeze])
        checks.append(("伪造 usage 的说谎中转 → MISMATCH（行为/错误层暴露）",
                       r.verdict.label is VerdictLabel.MISMATCH,
                       f"got {r.verdict.label.value}/{r.verdict.runner_up}"))
    finally:
        shutdown_server(s4)

    s5, url5 = start_server(AQUA)
    try:
        from sothstan.runner import collect_baseline_signals

        baseline_adv = collect_baseline_signals(
            url5, "aqua-70b", "aqua", tags=["demo"], adversarial=True
        )
        r = verify(url5, "aqua-70b", baseline_adv, [breeze], options={"adversarial": True})
        checks.append(("对抗模式往返（seed 生成文本采集+验证）→ AUTHENTIC",
                       r.verdict.label is VerdictLabel.AUTHENTIC,
                       f"got {r.verdict.label.value}"))
    finally:
        shutdown_server(s5)

    ok = True
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {name}  ({detail})")
        ok = ok and passed
    print("selftest: " + ("ALL PASS" if ok else "FAILED"))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    from sothstan._version import __version__

    parser = argparse.ArgumentParser(
        prog="sothstan", description="Sothstan — LLM API 模型验真"
    )
    parser.add_argument("--version", action="version", version=f"sothstan {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="验证端点是否真的在服务声称的模型")
    p_check.add_argument("base_url", help="OpenAI 兼容端点，如 https://api.example.com/v1")
    p_check.add_argument("--model", required=True, help="声称的模型 ID")
    p_check.add_argument("--baseline", help="声称模型的基线文件（默认查注册表）")
    p_check.add_argument("--registry", help="基线注册表目录（默认用内置）")
    p_check.add_argument("--api-key-env", help="从该环境变量读 API key")
    p_check.add_argument("--seed", type=int, default=20260928)
    p_check.add_argument("--max-requests", type=int, default=64)
    p_check.add_argument("--max-prompt-tokens", type=int, default=200000)
    p_check.add_argument("--timeout", type=float, default=30.0, help="单请求超时秒数")
    p_check.add_argument("--retries", type=int, default=2, help="瞬时错误（429/5xx）重试次数")
    p_check.add_argument("--probes", help="逗号分隔的探测名子集")
    p_check.add_argument(
        "--adversarial",
        action="store_true",
        help="对抗模式：探测文本按 seed 生成（基线须以同模式采集）",
    )
    p_check.add_argument("--json", action="store_true", help="输出 JSON 报告")
    p_check.add_argument("--out", help="把 JSON 报告写入文件")
    p_check.add_argument("--include-demo", action="store_true", help="允许 demo 基线作为混淆集候选")
    p_check.set_defaults(func=cmd_check)

    p_collect = sub.add_parser("collect", help="对官方端点采集模型指纹基线")
    p_collect.add_argument("base_url")
    p_collect.add_argument("--model", required=True)
    p_collect.add_argument("--family", required=True, help="模型家族名（如 deepseek/glm/qwen）")
    p_collect.add_argument("--out", required=True, help="基线输出路径")
    p_collect.add_argument("--api-key-env")
    p_collect.add_argument("--seed", type=int, default=20260928)
    p_collect.add_argument("--tags", default="", help="逗号分隔标签")
    p_collect.add_argument("--honesty-note", default="")
    p_collect.add_argument(
        "--adversarial", action="store_true", help="对抗模式采集（token 探测用 seed 生成文本）"
    )
    p_collect.set_defaults(func=cmd_collect)

    p_audit = sub.add_parser("audit", help="批量审计：CSV 目标清单 → 汇总报告")
    p_audit.add_argument("targets", help="CSV 文件（表头: name,base_url,model,key_env）")
    p_audit.add_argument("-o", "--out", help="Markdown 报告输出路径")
    p_audit.add_argument("--json-out", help="JSON 报告输出路径（含逐端点完整证据）")
    p_audit.add_argument("--registry", help="基线注册表目录（默认用内置）")
    p_audit.add_argument("--include-demo", action="store_true")
    p_audit.add_argument("--seed", type=int, default=20260928)
    p_audit.add_argument("--max-workers", type=int, default=4)
    p_audit.add_argument("--timeout", type=float, default=30.0)
    p_audit.add_argument("--retries", type=int, default=2)
    p_audit.add_argument(
        "--adversarial", action="store_true", help="对抗模式（基线须以同模式采集）"
    )
    p_audit.set_defaults(func=cmd_audit)

    p_list = sub.add_parser("list-baselines", help="列出注册表中的基线")
    p_list.add_argument("--registry")
    p_list.set_defaults(func=cmd_list_baselines)

    p_self = sub.add_parser("selftest", help="离线自检（mock 服务器，不需要网络与 key）")
    p_self.set_defaults(func=cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    raise SystemExit(result)


if __name__ == "__main__":
    main()
