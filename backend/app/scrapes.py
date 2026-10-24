"""Scraped scholarships are files first, then rows. Startup can rebuild the rows from the files."""

import json
import logging
import re
from datetime import datetime, timezone

from app.config import BACKEND_DIR
from app.models import Scholarship
from app.record import empty_sections, study_level
from app.sources import _clean, normalize_criteria, suggest_criteria

logger = logging.getLogger("escholar")

SCRAPE_DIR = BACKEND_DIR / "data" / "scrapes"
DETAIL_BASE = "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/"


def catalogue_records(script_text: str) -> list[dict]:
    start, end = script_text.find("["), script_text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        rows = json.loads(script_text[start : end + 1])
    except json.JSONDecodeError:
        return []
    records = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get("sapProgid"):
            continue
        record = _catalogue_record(row)
        if record["source_url"] in seen:
            continue
        seen.add(record["source_url"])
        records.append(record)
    return records


def _catalogue_record(row: dict) -> dict:
    program_id = row["sapProgid"]
    scholarship_id = f"DAAD-{program_id}"
    name = _clean(str(row.get("programmnameEn") or row.get("nameEn") or "Scholarship"))[:180]
    introduction = row.get("introduction") if isinstance(row.get("introduction"), dict) else {}
    summary = _clean(str(introduction.get("en") or introduction.get("de") or ""))[:600]
    level = study_level(name, summary)
    rules = suggest_criteria(f"{name}\n{summary}")
    if level and not any(rule["field"] == "degree_level" for rule in rules):
        rules.append(
            {
                "field": "degree_level",
                "op": "eq",
                "value": level,
                "label": f"Degree level is {level}",
            }
        )
    sections = empty_sections("scholarship")
    sections["study_level"] = level
    sections["host_country"] = "Germany"
    sections["blocks"]["overview"] = summary
    return {
        "id": scholarship_id,
        "name": name or "Untitled scholarship",
        "provider": "DAAD",
        "deadline": "",
        "summary": summary or name,
        "required_documents": [],
        "criteria": normalize_criteria(rules[:6], scholarship_id),
        "source_url": f"{DETAIL_BASE}?detail={program_id}",
        "status": "draft",
        "origin": "url",
        "eligibility_notes": "",
        "excerpt": summary[:3500],
        "sections": sections,
    }


def record_from_row(row: Scholarship) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "deadline": row.deadline or "",
        "summary": row.summary or "",
        "required_documents": list(row.required_documents or []),
        "criteria": list(row.criteria or []),
        "source_url": row.source_url or "",
        "status": row.status,
        "origin": row.origin or "url",
        "eligibility_notes": row.eligibility_notes or "",
        "excerpt": row.excerpt or "",
        "sections": row.sections or {},
    }


def remove_scrape(scholarship_id: str) -> None:
    path = SCRAPE_DIR / f"{scholarship_id}.json"
    if path.is_file():
        path.unlink()


def write_scrape(record: dict) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", str(record.get("id") or "")):
        return
    SCRAPE_DIR.mkdir(parents=True, exist_ok=True)
    path = SCRAPE_DIR / f"{record['id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def load_scrapes(db) -> int:
    if not SCRAPE_DIR.is_dir():
        return 0
    known_ids = {item for (item,) in db.query(Scholarship.id).all()}
    known_urls = {item for (item,) in db.query(Scholarship.source_url).all() if item}
    added = 0
    now = datetime.now(timezone.utc)
    for path in sorted(SCRAPE_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            logger.exception("Could not read %s", path.name)
            continue
        scholarship_id = str(record.get("id") or "")
        source_url = str(record.get("source_url") or "")
        if not scholarship_id or scholarship_id in known_ids or (source_url and source_url in known_urls):
            continue
        db.add(
            Scholarship(
                id=scholarship_id[:32],
                name=str(record.get("name") or "Untitled scholarship")[:200],
                provider=str(record.get("provider") or "Source")[:200],
                deadline=str(record.get("deadline") or "")[:20],
                summary=str(record.get("summary") or ""),
                required_documents=list(record.get("required_documents") or []),
                criteria=list(record.get("criteria") or []),
                source_url=source_url[:1000],
                status="draft" if record.get("status") != "published" else "published",
                origin="url",
                eligibility_notes=str(record.get("eligibility_notes") or ""),
                excerpt=str(record.get("excerpt") or ""),
                sections=record.get("sections") if isinstance(record.get("sections"), dict) else {},
                fetched_at=now,
                submitted_by=None,
            )
        )
        known_ids.add(scholarship_id)
        if source_url:
            known_urls.add(source_url)
        added += 1
    if added:
        db.commit()
    return added
