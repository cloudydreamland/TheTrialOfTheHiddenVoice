"""iter4 批量审计：CSV 解析、并发跑批、汇总报告、退出码。"""

from __future__ import annotations

import json
import threading

import pytest

from sothstan.audit import (
    AuditTarget,
    audit_exit_code,
    load_targets,
    render_audit_markdown,
    run_audit,
)
from sothstan.cli import main
from sothstan.mockserver import AQUA, BREEZE, _MockServer, shutdown_server


def _serve(personality, claim=None) -> tuple[_MockServer, str]:
    server = _MockServer(personality, claim=claim)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


@pytest.fixture()
def three_endpoints():
    """三个目标：官方直连 / 换模型中转 / 第二家诚实代理。"""
    servers = []
    urls = []
    for p, claim in [(AQUA, None), (BREEZE, "aqua-70b"), (AQUA, None)]:
        s, u = _serve(p, claim)
        servers.append(s)
        urls.append(u)
    rows = [
        ("official", urls[0], "aqua-70b"),
        ("relay-suspect", urls[1], "aqua-70b"),
        ("proxy-honest", urls[2], "aqua-70b"),
    ]
    yield rows, servers
    for s in servers:
        shutdown_server(s)


def _write_csv(tmp_path, rows):
    p = tmp_path / "targets.csv"
    lines = ["name,base_url,model,key_env"]
    lines += [",".join(r) for r in rows]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_load_targets_parses_and_validates(tmp_path):
    p = _write_csv(tmp_path, [
        ("official", "http://x/v1", "aqua-70b", ""),
        ("", "", "", ""),  # 空行跳过
        ("bad", "", "m", ""),  # 缺 base_url → problem
    ])
    targets, problems = load_targets(p)
    assert len(targets) == 1
    assert targets[0].name == "official"
    assert len(problems) == 1


def test_load_targets_missing_header(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("nome,base_url\na,b\n", encoding="utf-8")
    targets, problems = load_targets(p)
    assert targets == []
    assert any("表头缺列" in x for x in problems)


def test_load_targets_handles_utf8_bom(tmp_path):
    """Windows 记事本保存的 CSV 带 BOM——表头必须仍能识别。"""
    p = tmp_path / "bom.csv"
    p.write_text(
        "name,base_url,model,key_env\nx,http://x/v1,aqua-70b,\n", encoding="utf-8-sig"
    )
    targets, problems = load_targets(p)
    assert problems == []
    assert len(targets) == 1
    assert targets[0].name == "x"


def test_run_audit_three_endpoints(three_endpoints):
    rows, _ = three_endpoints
    objs = [AuditTarget(name=n, base_url=u, model=m) for n, u, m in rows]
    report = run_audit(objs, include_demo=True, max_workers=3)
    s = report.summary
    assert s["total"] == 3
    assert s["AUTHENTIC"] == 2
    assert s["MISMATCH"] == 1
    by_name = {r["name"]: r for r in report.rows}
    assert by_name["relay-suspect"]["report"]["verdict"]["runner_up"] == "breeze-8b"
    assert all(
        len(r["report"]["transcript_sha256"]) == 64 for r in report.rows if r["report"]
    )


def test_run_audit_missing_baseline_row():
    report = run_audit(
        [AuditTarget(name="x", base_url="http://127.0.0.1:1/v1", model="no-such-model")],
        include_demo=True,
        max_workers=1,
    )
    assert report.rows[0]["error"] and "基线" in report.rows[0]["error"]


def test_audit_markdown_publishable(three_endpoints):
    rows, _ = three_endpoints
    objs = [AuditTarget(name=n, base_url=u, model=m) for n, u, m in rows]
    report = run_audit(objs, include_demo=True, max_workers=3)
    md = render_audit_markdown(report)
    assert "# Sothstan批量审计报告" in md
    assert "**MISMATCH**" in md
    assert "诚实声明" in md
    assert "不构成对任何服务提供方的法律指控" in md


def test_audit_exit_codes(three_endpoints):
    rows, _ = three_endpoints
    objs = [AuditTarget(name=n, base_url=u, model=m) for n, u, m in rows]
    report = run_audit(objs, include_demo=True, max_workers=3)
    assert audit_exit_code(report) == 2  # 含 MISMATCH
    assert report.summary["AUTHENTIC"] == 2


def test_cli_audit_end_to_end(tmp_path, three_endpoints):
    rows, _ = three_endpoints
    csv_path = _write_csv(tmp_path, rows)
    md_out = tmp_path / "report.md"
    json_out = tmp_path / "report.json"
    with pytest.raises(SystemExit) as exc:
        main([
            "audit", str(csv_path), "-o", str(md_out),
            "--json-out", str(json_out), "--include-demo",
            "--max-workers", "3",
        ])
    assert exc.value.code == 2
    assert md_out.exists() and json_out.exists()
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["summary"]["MISMATCH"] == 1
    assert len(payload["rows"]) == 3


def test_cli_audit_bad_csv_exits_4(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("nome,url\na,b\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["audit", str(p)])
    assert exc.value.code == 4
