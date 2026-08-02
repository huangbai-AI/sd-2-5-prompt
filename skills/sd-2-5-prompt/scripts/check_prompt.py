#!/usr/bin/env python3
"""Check common structural problems in an SD 2.5 video prompt."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


TIME_RANGE = re.compile(
    r"(?P<start>\d+(?:\.\d+)?)\s*(?:秒)?\s*[—–-]\s*(?P<end>\d+(?:\.\d+)?)\s*秒"
)

KNOWN_BRANDS = (
    "fanta",
    "芬达",
    "coca-cola",
    "coca cola",
    "可口可乐",
    "pepsi",
    "百事",
    "sprite",
    "雪碧",
    "mcdonald",
    "麦当劳",
    "kfc",
    "肯德基",
    "logitech",
    "罗技",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", type=Path, help="UTF-8 prompt text or Markdown file")
    parser.add_argument("--duration", type=float, help="Expected duration in seconds")
    parser.add_argument(
        "--unbranded",
        action="store_true",
        help="Flag common real-world brand names in an unbranded prompt",
    )
    return parser.parse_args()


def add(items: list[dict[str, str]], level: str, code: str, message: str) -> None:
    items.append({"level": level, "code": code, "message": message})


def check_timeline(text: str, duration: float | None, findings: list[dict[str, str]]) -> None:
    ranges = [(float(m.group("start")), float(m.group("end"))) for m in TIME_RANGE.finditer(text)]
    if not ranges:
        add(findings, "warning", "timeline.missing", "未识别到“开始—结束秒”的时间段。")
        return

    ordered = sorted(ranges)
    if ordered != ranges:
        add(findings, "error", "timeline.order", "时间段没有按开始时间递增排列。")

    for start, end in ranges:
        if end <= start:
            add(findings, "error", "timeline.invalid", f"时间段 {start:g}—{end:g} 秒的结束时间不大于开始时间。")

    unique = []
    for item in ranges:
        if item not in unique:
            unique.append(item)

    unique.sort()
    if unique and abs(unique[0][0]) > 0.01:
        add(findings, "warning", "timeline.start", f"时间轴从 {unique[0][0]:g} 秒开始，而不是 0 秒。")

    for (_, prev_end), (next_start, _) in zip(unique, unique[1:]):
        if next_start > prev_end + 0.01:
            add(findings, "warning", "timeline.gap", f"时间轴在 {prev_end:g}—{next_start:g} 秒之间有空档。")
        elif next_start < prev_end - 0.01:
            add(findings, "error", "timeline.overlap", f"时间轴在 {next_start:g} 秒附近发生重叠。")

    if duration is not None and unique:
        last_end = max(end for _, end in unique)
        if abs(last_end - duration) > 0.05:
            add(
                findings,
                "error",
                "timeline.duration",
                f"时间轴结束于 {last_end:g} 秒，目标时长是 {duration:g} 秒。",
            )


def check_sections(text: str, findings: list[dict[str, str]]) -> None:
    requirements = {
        "subject.missing": ("【主体】", "主体：", "主体"),
        "style.missing": ("【风格】", "风格：", "风格"),
        "bgm.missing": ("【BGM】", "BGM：", "背景音乐", "无 BGM", "无BGM"),
        "limits.missing": ("【限制】", "限制：", "避免", "禁止"),
    }
    messages = {
        "subject.missing": "缺少“主体”部分。",
        "style.missing": "缺少“风格”部分。",
        "bgm.missing": "缺少“BGM”部分。",
        "limits.missing": "缺少“限制”部分。",
    }
    for code, terms in requirements.items():
        if not any(term in text for term in terms):
            add(findings, "warning", code, messages[code])

    if "@图" in text or "@视频" in text or "@音频" in text:
        if not any(term in text for term in ("只用于", "只参考", "锁定", "不复制", "不参考")):
            add(findings, "warning", "reference.scope", "使用了参考素材，但没有明确素材职责或禁止迁移项。")

    complex_terms = ("攻击", "打斗", "追逐", "抛接", "飞向", "射流", "换位", "格挡")
    causal_terms = ("出发", "路径", "来向", "落点", "从", "沿", "作用于")
    if any(term in text for term in complex_terms) and not any(term in text for term in causal_terms):
        add(findings, "warning", "action.causality", "复杂动作缺少发起位置、运动路径、来向或落点。")


def check_unbranded(text: str, findings: list[dict[str, str]]) -> None:
    lowered = text.lower()
    hits = [brand for brand in KNOWN_BRANDS if brand.lower() in lowered]
    if hits:
        add(findings, "error", "brand.detected", "无品牌模式发现现实品牌词：" + "、".join(sorted(set(hits))))
    if not any(term in text for term in ("无品牌", "无商标", "不出现任何文字", "不出现现实品牌")):
        add(findings, "warning", "brand.lock", "无品牌模式缺少明确的无品牌、无商标或原创包装约束。")


def main() -> int:
    args = parse_args()
    if not args.prompt.is_file():
        print(json.dumps({"ok": False, "error": f"文件不存在：{args.prompt}"}, ensure_ascii=False))
        return 2

    text = args.prompt.read_text(encoding="utf-8")
    findings: list[dict[str, str]] = []
    check_timeline(text, args.duration, findings)
    check_sections(text, findings)
    if args.unbranded:
        check_unbranded(text, findings)

    errors = sum(item["level"] == "error" for item in findings)
    warnings = sum(item["level"] == "warning" for item in findings)
    result = {
        "ok": errors == 0,
        "file": str(args.prompt),
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
