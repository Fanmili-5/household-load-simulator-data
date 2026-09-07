"""Render two illustrative SFT records; no generation, imputation or training.

Profiles intentionally use the selected-field framework examples. These outputs
are format demonstrations, not complete profiles or a training release.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source):
    source_path = ROOT / "examples" / f"{source}_full_day_example.json"
    profile_path = ROOT / "examples/framework_design" / f"{source}_profile_fragment.json"
    observation = read_json(source_path)
    fragment = read_json(profile_path)
    assert fragment["metadata"]["household_id"] == observation["metadata"]["household_id"]
    assert fragment["metadata"]["source_example_sha256"] == sha256(source_path)

    history = observation["input"]["history"]
    context = observation["input"]["context"]
    window = context["target_window"]
    target = observation["output"]
    dt = datetime.fromisoformat
    assert history["end"] == context["forecast_origin"] == window["start"]
    assert (dt(history["end"]) - dt(history["start"])).total_seconds() == 7 * 86400
    assert (dt(window["end"]) - dt(window["start"])).total_seconds() == 86400
    assert len(history["energy_kwh"]) * history["interval_minutes"] == 7 * 1440
    assert len(target["energy_kwh"]) * window["interval_minutes"] == 1440

    payload = {
        "profile": fragment["input_fragment"],
        "history": history,
        "context": context,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "根据提供的家庭信息、过去七天的用电序列和目标日条件，"
                "预测接下来24小时的整户用电曲线。负荷序列中每个值表示"
                "对应时间区间的电量，单位为kWh；采样间隔由interval_minutes声明。"
                "null表示信息未知。按目标窗口的时间顺序，仅输出含energy_kwh数组的JSON对象。"
            ),
        },
        {
            "role": "user",
            "content": "请预测以下目标窗口的整户用电曲线。\n"
            + json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        },
        {
            "role": "assistant",
            "content": json.dumps(target, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        },
    ]
    metadata = {
        "example_scope": "format_demo_with_partial_profile_not_training_release",
        "formal_training_release": False,
        "source": source,
        "household_id": observation["metadata"]["household_id"],
        "source_observation": str(source_path.relative_to(ROOT)),
        "source_observation_sha256": sha256(source_path),
        "source_profile_fragment": str(profile_path.relative_to(ROOT)),
        "source_profile_fragment_sha256": sha256(profile_path),
        "history_values": len(history["energy_kwh"]),
        "target_values": len(target["energy_kwh"]),
        "target_origin": "unchanged observed target from the existing full-day example",
        "desired_loss_scope": "assistant content only; must be implemented by the future trainer",
        "training_executed": False,
        "known_limitations": [
            "Only fields in the illustrative profile fragment are included.",
            "Profile availability date and individual event-notice availability are not certified here.",
            "Clock labels are preserved without inferring a UTC offset.",
        ],
    }
    output = {"schema_version": "sft-format-demo/0.1", "messages": messages, "metadata": metadata}
    dest = ROOT / "examples/sft_format" / f"{source}_messages.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    # Check the delivered serialization, not just the in-memory source object.
    written = read_json(dest)
    input_back = json.loads(written["messages"][1]["content"].split("\n", 1)[1])
    answer_back = json.loads(written["messages"][2]["content"])
    assert input_back == payload
    assert answer_back == target
    assert set(input_back) == {"profile", "history", "context"}
    assert "output" not in input_back and "metadata" not in input_back
    assert observation["metadata"]["household_id"] not in written["messages"][1]["content"]
    assert [m["role"] for m in written["messages"]] == ["system", "user", "assistant"]
    return {"source": source, "history_points": len(history["energy_kwh"]), "target_points": len(target["energy_kwh"]), "round_trip_exact": True}


if __name__ == "__main__":
    print(json.dumps([build(source) for source in ("sgsc", "iflex")], ensure_ascii=False, indent=2))
