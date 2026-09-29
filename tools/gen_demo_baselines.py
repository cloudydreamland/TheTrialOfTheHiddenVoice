"""生成内置 demo 基线（对 mock 人格真实运行完整采集管线）。

产出的基线是"对 mock 人格的真实指纹"——采集路径与生产完全一致，
只是对象是本库自带的人格。带 demo 标签，仅用于离线测试与 selftest。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sothstan.mockserver import AQUA, BREEZE, shutdown_server, start_server  # noqa: E402
from sothstan.runner import collect_and_save  # noqa: E402

OUT = Path(__file__).parent.parent / "src" / "sothstan" / "baselines"
NOTE = "内置 mock 人格的指纹，仅用于离线测试与 selftest，不代表任何真实模型。"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (AQUA, BREEZE):
        server, url = start_server(p)
        try:
            path = collect_and_save(
                base_url=url,
                model=p.model_id,
                family=p.family,
                out_path=OUT / f"_demo_{p.model_id}.json",
                tags=["demo"],
                honesty_note=NOTE,
            )
            print(f"ok {path}")
        finally:
            shutdown_server(server)


if __name__ == "__main__":
    main()
