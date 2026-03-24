#!/usr/bin/env python3
"""
parse.py — Parse a study schedule HTML file into a courses JSON file.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
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


def text(el):
    """Return stripped text of an element, or '' if element is None."""
    if el is None:
        return ""
    return el.get_text(separator=" ", strip=True)


def parse_day(raw: str):
    raw = raw.strip()
    if raw in ("", "n.V."):
        return None
    return DAY_MAP.get(raw.lower(), raw)


def is_date(s: str) -> bool:
    """Detect DD.MM.YYYY style dates used for block events."""
    return bool(re.match(r"^\d{2}\.\d{2}\.\d{4}$", s.strip()))


def parse_slot(event_box):
    group_el = event_box.select_one(".s-event-group")
    group_raw = group_el.get_text(strip=True) if group_el else ""
    # &nbsp; renders as a non-breaking space or just whitespace
    slot_group = None if group_raw in ("", "\xa0") else group_raw

    tag_el = event_box.select_one(".s_termin_tag")
    woche_el = event_box.select_one(".s_termin_woche")
    von_el = event_box.select_one(".s_termin_von")
    bis_el = event_box.select_one(".s_termin_bis")
    raum_el = event_box.select_one(".s_termin_raum")

    tag_raw = text(tag_el)
    woche_raw = text(woche_el)
    von_raw = text(von_el)
    bis_raw = text(bis_el)
    raum_raw = text(raum_el)

    is_block = is_date(von_raw) or is_date(bis_raw)
    day = parse_day(tag_raw)
    is_online = (day is None and not is_block and
                 not von_raw and not bis_raw)

    return {
        "slotGroup": slot_group,
        "day": day,
        "weekPattern": woche_raw if woche_raw in ("A", "B") else None,
        "timeStart": von_raw if von_raw and not is_block else None,
        "timeEnd": bis_raw if bis_raw and not is_block else None,
        "room": raum_raw or None,
        "isBlockEvent": is_block,
        "isOnline": is_online,
    }


def parse_lecturers(cours_box):
    doz_box = cours_box.select_one(".s-dozenten-box")
    if doz_box is None:
        return []
    links = doz_box.find_all("a")
    if links:
        return [a.get_text(strip=True) for a in links]
    # fallback: split on semicolons
    raw = doz_box.get_text(separator=";", strip=True)
    return [p.strip() for p in raw.split(";") if p.strip()]


def parse_course(cours_box, module_id, course_idx):
    typ_el = cours_box.select_one(".s-cours-typ")
    title_el = cours_box.select_one(".s-cours-title")
    addinfo_els = cours_box.select(".s-addinfo-row")

    course_type = text(typ_el)
    course_title = text(title_el)
    additional_info = " ".join(text(el) for el in addinfo_els).strip() or None
    lecturers = parse_lecturers(cours_box)

    slots = [parse_slot(eb) for eb in cours_box.select(".s-event-box")]

    groups = {s["slotGroup"] for s in slots if s["slotGroup"]}
    has_multiple = len(groups) > 1

    course_id = f"{module_id}-{course_type.replace(' ', '_')}-{course_idx}"

    return {
        "id": course_id,
        "type": course_type,
        "title": course_title,
        "lecturers": lecturers,
        "additionalInfo": additional_info,
        "hasMultipleSlotGroups": has_multiple,
        "slots": slots,
    }


def parse_module(modul_div, semester):
    number_el = modul_div.select_one(".s-modul-number")
    title_el = modul_div.select_one(".s-modul-title")
    cat_el = modul_div.select_one(".s-modul-sg-category")

    module_number = text(number_el)
    module_name = text(title_el)
    category = text(cat_el) or None

    courses = []
    for idx, cb in enumerate(modul_div.select(".s-cours-box")):
        courses.append(parse_course(cb, module_number, idx))

    return {
        "id": module_number,
        "number": module_number,
        "name": module_name,
        "category": category,
        "semester": semester,
        "courses": courses,
    }


def parse_semester(studgang_div):
    """Return semester number from n-studgang-titel heading."""
    titel_el = studgang_div.find("h4", class_="n-studgang-titel")
    if titel_el:
        span = titel_el.find("span")
        if span:
            m = re.search(r"(\d+)\.\s*Semester", span.get_text())
            if m:
                return int(m.group(1))
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Parse a schedule HTML file into a courses JSON file."
    )
    parser.add_argument(
        "-i", "--input-file",
        type=Path,
        help="Path to the input HTML file"
    )
    parser.add_argument(
        "-o", "--output-file",
        type=Path,
        help="Path for the output JSON file"
    )
    args = parser.parse_args()

    input_file: Path = args.input_file
    output_file: Path = args.output_file

    if not input_file.exists():
        print(f"Error: input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    html = input_file.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    # Track seen module IDs to avoid duplicates when a module appears
    # in multiple semester sections
    seen_ids = {}   # module_id -> first semester it was seen in
    duplicate_ids = []
    modules = []

    semester_divs = soup.select("div.n-studgang-semester")
    print(f"Found {len(semester_divs)} semester section(s)")
    for sem_div in semester_divs:
        semester = parse_semester(sem_div)
        for modul_div in sem_div.select("div.MODUL.s-column-container"):
            number_el = modul_div.select_one(".s-modul-number")
            title_el = modul_div.select_one(".s-modul-title")
            module_id = text(number_el)
            module_name = text(title_el)
            if module_id in seen_ids:
                print(f"  [dedup] {module_id}  \"{module_name}\"  "
                      f"(first seen in semester {seen_ids[module_id]}, skipping semester {semester})")
                duplicate_ids.append(module_id)
                continue
            seen_ids[module_id] = semester
            mod = parse_module(modul_div, semester)
            modules.append(mod)

    if duplicate_ids:
        print(f"Deduplicated {len(duplicate_ids)} module occurrence(s) "
              f"({len(set(duplicate_ids))} distinct module(s) appeared in multiple semesters)")

    result = {
        "_generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modules": modules,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(modules)} modules to {output_file}")


if __name__ == "__main__":
    main()
