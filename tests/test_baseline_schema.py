"""基线 schema 校验与注册表加载。"""

from __future__ import annotations

import json

import pytest

from sothstan.baseline import (
    baseline_from_dict,
    load_registry,
    save_baseline,
    validate_baseline_dict,
)


def _good() -> dict:
    return {
        "schema_version": 1,
        "model_id": "some-model",
        "family": "some",
        "signals": {
            "token_count.prompt_curve": {"kind": "int_vector", "value": [1, 2, 3]},
            "limits.logprobs_support": {"kind": "bool", "value": True},
        },
    }


def test_valid_baseline_passes():
    assert validate_baseline_dict(_good()) == []


def test_rejects_bad_kind():
    bad = _good()
    bad["signals"]["x"] = {"kind": "float", "value": 1.5}
    problems = validate_baseline_dict(bad)
    assert any("kind" in p for p in problems)


def test_rejects_type_mismatch():
    bad = _good()
    bad["signals"]["token_count.prompt_curve"]["value"] = "not a list"
    assert validate_baseline_dict(bad)


def test_roundtrip_save_load(tmp_path):
    b = baseline_from_dict(_good())
    path = save_baseline(b, tmp_path / "reg" / "some-model.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["model_id"] == "some-model"
    loaded = baseline_from_dict(data)
    assert loaded.get_signal("token_count.prompt_curve").value == [1, 2, 3]


def test_load_registry_skips_corrupt_files(tmp_path):
    (tmp_path / "good.json").write_text(json.dumps(_good()), encoding="utf-8")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "worse.json").write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    registry = load_registry(tmp_path)
    assert set(registry) == {"some-model"}


def test_baseline_from_dict_raises_on_garbage():
    with pytest.raises(ValueError):
        baseline_from_dict({"schema_version": 1})
