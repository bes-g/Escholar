"""One scholarship, split into the facts a student match needs. Each fact is embedded on its own."""

import re
from urllib.parse import urljoin, urlparse

SECTION_SPECS = [
    ("overview", "Overview"),
    ("who_can_apply", "Who can apply"),
    ("academic_requirements", "Academic requirements"),
    ("funding", "What is funded"),
    ("dates", "Deadline and duration"),
    ("documents", "Documents"),
    ("how_to_apply", "How to apply"),
]

_HEADING_SECTIONS = [
    ("documents", ("document", "what to submit", "checklist", "application papers")),
    ("how_to_apply", ("how to apply", "application procedure", "application process", "where to apply")),
    ("dates", ("deadline", "duration", "selection", "start of")),
    ("funding", ("funded", "funding", "value", "scholarship payments", "what can be funded", "coverage")),
    ("academic_requirements", ("academic", "degree", "gpa", "language", "subject", "discipline", "requirement")),
    ("who_can_apply", ("who can apply", "eligib", "target group", "applicants")),
]

_BOILER = (
    "imprint",
    "data privacy",
    "privacy statement",
    "cookies",
    "newsletter",
    "jump to content",
    "colour switch",
    "color switch",
    "accessibility",
    "all addresses",
    "useful links",
    "daad newsletters",
    "kennedyallee",
    "53175",
    "to homepage",
    "©",
    "strategy 2030",
    "offices worldwide",
)

_SKIP_HEADINGS = ("address", "useful links", "newsletter", "contact", "press")

_LINK_WORDS = ("scholarship", "funding", "programme", "program", "stipend", "applicant", "mobility", "artist")


def empty_sections(page_kind: str = "scholarship") -> dict:
    return {
        "page_kind": page_kind,
        "study_level": "",
        "host_country": "",
        "related_pages": [],
        "blocks": {key: "" for key, _label in SECTION_SPECS},
    }


def provider_name(hostname: str) -> str:
    host = (hostname or "").lower().removeprefix("www.")
    if host.endswith("daad.de") or "daad" in host:
        return "DAAD"
    label = host.split(".")[0].replace("-", " ").strip()
    return label.title() if label else "Source"


def study_level(*texts: str) -> str:
    blob = " ".join(texts).casefold()
    if re.search(r"\bph\.?\s*d\b|\bdoctoral\b", blob):
        return "PhD"
    if re.search(r"\bmaster(?:'s|s)?\b", blob):
        return "Master"
    if re.search(r"\bbachelor(?:'s)?\b|\bundergraduate\b", blob):
        return "Bachelor"
    if re.search(r"\bhigh school\b|\bsecondary school\b", blob):
        return "High school"
    return ""


def classify_heading(label: str) -> str:
    folded = label.casefold()
    for key, words in _HEADING_SECTIONS:
        if any(word in folded for word in words):
            return key
    return ""


def _useful_line(text: str) -> bool:
    folded = text.casefold().strip()
    if len(folded) < 25:
        return False
    return not any(phrase in folded for phrase in _BOILER)


def content_root(soup):
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": ["navigation", "contentinfo", "banner"]}):
        tag.decompose()
    return soup.find("main") or soup.find("article") or soup.body or soup


def related_pages(root, page_url: str) -> list[dict]:
    found = []
    seen = set()
    for link in root.find_all("a", href=True):
        label = " ".join(link.get_text(" ", strip=True).split())
        folded = label.casefold()
        if len(label) < 8 or len(label) > 140:
            continue
        if any(phrase in folded for phrase in _BOILER):
            continue
        if not any(word in folded for word in _LINK_WORDS):
            continue
        href = urljoin(page_url, link["href"].strip())
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or href in seen:
            continue
        if parsed.netloc != urlparse(page_url).netloc:
            continue
        seen.add(href)
        found.append({"title": label, "url": href})
        if len(found) >= 12:
            break
    return found


def section_blocks(root) -> dict[str, str]:
    blocks = {key: "" for key, _label in SECTION_SPECS}
    overview = []
    for node in root.find_all(["h1", "h2", "h3", "p", "li"]):
        text = " ".join(node.get_text(" ", strip=True).split())
        if not text or any(phrase in text.casefold() for phrase in _BOILER):
            continue
        if node.name in {"h2", "h3"}:
            continue
        parent_heading = node.find_previous(["h2", "h3"])
        heading = parent_heading.get_text(" ", strip=True) if parent_heading else ""
        if any(phrase in heading.casefold() for phrase in _SKIP_HEADINGS):
            continue
        key = classify_heading(heading) if heading else ""
        if node.name == "li" and key:
            line = f"- {text[:220]}"
            blocks[key] = (blocks[key] + "\n" + line).strip()[:2000]
        elif node.name == "p" and _useful_line(text):
            if key:
                blocks[key] = (blocks[key] + "\n" + text).strip()[:2000]
            elif len(overview) < 3:
                overview.append(text[:500])
    blocks["overview"] = "\n".join(overview)[:1200]
    return blocks


def assemble_sections(*, title: str, summary: str, deadline: str, documents: list[str], notes: list[str], blocks: dict, links: list[dict], host_country: str = "") -> dict:
    level = study_level(
        title,
        blocks.get("overview", ""),
        blocks.get("who_can_apply", ""),
        blocks.get("academic_requirements", ""),
        blocks.get("funding", ""),
    )
    if notes and not blocks.get("who_can_apply"):
        blocks["who_can_apply"] = "\n".join(f"- {note}" for note in notes)[:2000]
    if documents and not blocks.get("documents"):
        blocks["documents"] = "\n".join(f"- {item}" for item in documents)[:2000]
    if deadline and not blocks.get("dates"):
        blocks["dates"] = f"Application deadline {deadline}."
    if summary and not blocks.get("overview"):
        blocks["overview"] = summary
    has_award = bool(deadline or documents or notes or blocks.get("who_can_apply") or blocks.get("funding"))
    page_kind = "directory" if len(links) >= 4 and not has_award else "scholarship"
    record = empty_sections(page_kind)
    record["study_level"] = level
    record["host_country"] = host_country
    record["related_pages"] = links
    record["blocks"] = blocks
    return record


def missing_facts(record: dict, sections: dict | None) -> list[str]:
    sections = sections or empty_sections()
    blocks = sections.get("blocks") or {}
    missing = []
    if sections.get("page_kind") == "directory":
        missing.append("This page lists programmes. Open one scholarship link and fetch that page.")
    if not (record.get("name") or "").strip():
        missing.append("Scholarship name")
    if not (record.get("provider") or "").strip():
        missing.append("Provider")
    if not (record.get("deadline") or "").strip():
        missing.append("Application deadline")
    if len((record.get("summary") or "").strip()) < 20 and len(blocks.get("overview", "").strip()) < 20:
        missing.append("What the scholarship is")
    if not (blocks.get("who_can_apply") or record.get("eligibility_notes")):
        missing.append("Who can apply")
    if not blocks.get("academic_requirements") and not record.get("criteria"):
        missing.append("Academic requirements, such as degree, field, or GPA")
    if not blocks.get("documents") and not record.get("required_documents"):
        missing.append("Required documents")
    if not blocks.get("how_to_apply"):
        missing.append("How to apply")
    if not blocks.get("funding"):
        missing.append("What the scholarship pays for")
    return missing


def vector_documents(name: str, provider: str, source_url: str, summary: str, deadline: str, notes: str, documents: list, criteria: list, sections: dict | None) -> list[dict]:
    sections = sections or empty_sections()
    blocks = dict(sections.get("blocks") or {})
    if not blocks.get("overview"):
        blocks["overview"] = summary or ""
    if not blocks.get("who_can_apply"):
        blocks["who_can_apply"] = notes or ""
    if not blocks.get("documents"):
        blocks["documents"] = "\n".join(f"- {item}" for item in documents or [])
    if not blocks.get("dates") and deadline:
        blocks["dates"] = f"Application deadline {deadline}."
    if criteria and not blocks.get("academic_requirements"):
        blocks["academic_requirements"] = "\n".join(
            f"- {rule.get('label')}" for rule in criteria if isinstance(rule, dict) and rule.get("label")
        )
    identity = f"{name}. Provider: {provider}."
    if sections.get("study_level"):
        identity += f" Study level: {sections['study_level']}."
    if source_url:
        identity += f" Source: {source_url}."
    documents_out = []
    for key, label in SECTION_SPECS:
        body = " ".join((blocks.get(key) or "").split())
        if len(body) < 12:
            continue
        documents_out.append({"section": key, "text": f"{label}. {identity} {body}"})
    return documents_out
