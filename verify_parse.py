#!/usr/bin/env python3
"""
verify_parse.py — Audit a parsed JSON file against its source HTML.

Usage:
    python3 verify_parse.py -i "Master Informatik.html" -o datasets/courses_ma_ss26.json
    python3 verify_parse.py -i "Bachelor Informatik.html" -o datasets/courses_ba_ss26.json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup

DAY_MAP = {
    "montags": "monday",
    "dienstags": "tuesday",
    "mittwochs": "wednesday",
    "donnerstags": "thursday",
    "freitags": "friday",
    "samstags": "saturday",
    "sonntags": "sunday",
}


def t(el):
    if el is None:
        return ""
    return el.get_text(separator=" ", strip=True)


def is_date(s):
    return bool(re.match(r"^\d{2}\.\d{2}\.\d{4}$", s.strip()))


def main():
    parser = argparse.ArgumentParser(description="Verify parse.py output against source HTML.")
    parser.add_argument("-i", "--input-file", type=Path, required=True, help="Source HTML file")
    parser.add_argument("-o", "--output-file", type=Path, required=True, help="Parsed JSON file")
    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Error: HTML file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    if not args.output_file.exists():
        print(f"Error: JSON file not found: {args.output_file}", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(args.input_file.read_text(encoding="utf-8"), "lxml")
    data = json.loads(args.output_file.read_text(encoding="utf-8"))
    modules_json = {m["id"]: m for m in data["modules"]}

    issues = []

    # ── 1. Semester section summary ──────────────────────────────────────────
    print("=== Semester sections ===")
    total_raw = 0
    for sem_div in soup.select("div.n-studgang-semester"):
        h4 = sem_div.find("h4", class_="n-studgang-titel")
        span = h4.find("span") if h4 else None
        label = span.get_text(strip=True) if span else "?"
        raw_mods = sem_div.select("div.MODUL.s-column-container")
        total_raw += len(raw_mods)
        print(f"  {label}: {len(raw_mods)} modules")
    print(f"  Total raw: {total_raw}  →  after dedup: {len(modules_json)}")
    print()

    # ── 2. Per-module field audit ─────────────────────────────────────────────
    print("=== Per-module audit ===")
    audited_modules = 0
    for sem_div in soup.select("div.n-studgang-semester"):
        for modul_div in sem_div.select("div.MODUL.s-column-container"):
            mod_num = t(modul_div.select_one(".s-modul-number"))
            if mod_num not in modules_json:
                continue  # deduplicated occurrence — skip
            audited_modules += 1
            mod_json = modules_json[mod_num]

            # Name
            name_html = t(modul_div.select_one(".s-modul-title"))
            if name_html != mod_json["name"]:
                issues.append(f"NAME MISMATCH [{mod_num}]:\n    HTML: '{name_html}'\n    JSON: '{mod_json['name']}'")

            # Category
            cat_html = t(modul_div.select_one(".s-modul-sg-category")) or None
            if cat_html != mod_json["category"]:
                issues.append(f"CATEGORY MISMATCH [{mod_num}]:\n    HTML: '{cat_html}'\n    JSON: '{mod_json['category']}'")

            # Course count
            courses_html = modul_div.select(".s-cours-box")
            courses_json = mod_json["courses"]
            if len(courses_html) != len(courses_json):
                issues.append(
                    f"COURSE COUNT [{mod_num}] '{mod_json['name']}':\n"
                    f"    HTML: {len(courses_html)}  JSON: {len(courses_json)}"
                )
                continue  # can't zip mismatched lists meaningfully

            for i, (cb_html, c_json) in enumerate(zip(courses_html, courses_json)):
                prefix = f"[{mod_num}][course {i}]"

                # Type
                typ_html = t(cb_html.select_one(".s-cours-typ"))
                if typ_html != c_json["type"]:
                    issues.append(f"COURSE TYPE {prefix}:\n    HTML: '{typ_html}'\n    JSON: '{c_json['type']}'")

                # Title
                title_html = t(cb_html.select_one(".s-cours-title"))
                if title_html != c_json["title"]:
                    issues.append(f"COURSE TITLE {prefix}:\n    HTML: '{title_html}'\n    JSON: '{c_json['title']}'")

                # Slot count
                slots_html = cb_html.select(".s-event-box")
                slots_json = c_json["slots"]
                if len(slots_html) != len(slots_json):
                    issues.append(
                        f"SLOT COUNT {prefix} ({c_json['type']}):\n"
                        f"    HTML: {len(slots_html)}  JSON: {len(slots_json)}"
                    )
                    continue

                for j, (eb, s_json) in enumerate(zip(slots_html, slots_json)):
                    sprefix = f"{prefix}[slot {j}]"

                    # Slot group
                    grp_raw = t(eb.select_one(".s-event-group"))
                    grp_html = None if grp_raw in ("", "\xa0") else grp_raw
                    if s_json["slotGroup"] != grp_html:
                        issues.append(f"SLOT GROUP {sprefix}:\n    HTML: '{grp_html}'\n    JSON: '{s_json['slotGroup']}'")

                    # Day
                    day_raw = t(eb.select_one(".s_termin_tag"))
                    day_html = DAY_MAP.get(day_raw.lower(), day_raw) if day_raw and day_raw != "n.V." else None
                    if s_json["day"] != day_html:
                        issues.append(f"DAY {sprefix}:\n    HTML: '{day_html}'\n    JSON: '{s_json['day']}'")

                    # Week pattern
                    woche_html = t(eb.select_one(".s_termin_woche"))
                    woche_exp = woche_html if woche_html in ("A", "B") else None
                    if s_json["weekPattern"] != woche_exp:
                        issues.append(f"WEEK PATTERN {sprefix}:\n    HTML: '{woche_exp}'\n    JSON: '{s_json['weekPattern']}'")

                    # Times / block detection
                    von_raw = t(eb.select_one(".s_termin_von"))
                    bis_raw = t(eb.select_one(".s_termin_bis"))
                    is_block = is_date(von_raw) or is_date(bis_raw)
                    expected_start = von_raw if von_raw and not is_block else None
                    expected_end   = bis_raw if bis_raw and not is_block else None
                    if s_json["timeStart"] != expected_start:
                        issues.append(f"TIME START {sprefix}:\n    HTML: '{expected_start}'\n    JSON: '{s_json['timeStart']}'")
                    if s_json["timeEnd"] != expected_end:
                        issues.append(f"TIME END {sprefix}:\n    HTML: '{expected_end}'\n    JSON: '{s_json['timeEnd']}'")

                    # Room
                    raum_html = t(eb.select_one(".s_termin_raum")) or None
                    if s_json["room"] != raum_html:
                        issues.append(f"ROOM {sprefix}:\n    HTML: '{raum_html}'\n    JSON: '{s_json['room']}'")

                    # isBlockEvent flag
                    if s_json["isBlockEvent"] != is_block:
                        issues.append(f"IS_BLOCK {sprefix}:\n    expected: {is_block}  JSON: {s_json['isBlockEvent']}")

    print(f"Audited {audited_modules} modules (first occurrences only).")
    print()

    # ── 3. Slot summary table ─────────────────────────────────────────────────
    print("=== Timed slots (non-block, non-online) ===")
    count = 0
    for m in data["modules"]:
        for c in m["courses"]:
            for s in c["slots"]:
                if s["day"] and not s["isBlockEvent"] and not s["isOnline"] and s["timeStart"]:
                    print(
                        f"  {m['number']:22s} | {c['type']:22s} | "
                        f"{s['day']:10s} | {s['timeStart']}-{s['timeEnd']} | "
                        f"grp={str(s['slotGroup']):4s} | wk={str(s['weekPattern']):4s} | "
                        f"room={s['room']}"
                    )
                    count += 1
    print(f"  Total timed slots: {count}")
    print()

    # ── 4. Block / online / no-time summary ──────────────────────────────────
    blocks, online, no_time = [], [], []
    for m in data["modules"]:
        for c in m["courses"]:
            for s in c["slots"]:
                if s["isBlockEvent"]:
                    blocks.append((m["number"], c["type"]))
                elif s["isOnline"]:
                    online.append((m["number"], c["type"]))
                elif not s["timeStart"]:
                    no_time.append((m["number"], c["type"], s))

    print(f"=== Block events: {len(blocks)} ===")
    for num, typ in blocks:
        print(f"  {num} / {typ}")

    print(f"\n=== Online/no-schedule slots: {len(online)} ===")
    for num, typ in online:
        print(f"  {num} / {typ}")

    if no_time:
        print(f"\n=== Slots with no time and not block/online: {len(no_time)} ===")
        for num, typ, s in no_time:
            print(f"  {num} / {typ} — {s}")

    # ── 5. Result ─────────────────────────────────────────────────────────────
    print()
    if issues:
        print(f"FOUND {len(issues)} ISSUE(S):")
        for iss in issues:
            print(f"  {iss}")
        sys.exit(1)
    else:
        print(f"All checks passed. No issues found.")


if __name__ == "__main__":
    main()
