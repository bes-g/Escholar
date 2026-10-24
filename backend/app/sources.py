"""Turn a public scholarship page into a draft record. Nothing is matched until it is published."""

import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from app.record import assemble_sections, content_root, missing_facts, provider_name, related_pages, section_blocks, study_level

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "E-ScholarCatalogBot/1.0 (scholarship catalog review)"
MAX_BYTES = 1_000_000
FETCH_HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
RULE_FIELDS = {
    "country",
    "citizenship",
    "degree_level",
    "gpa",
    "field_of_study",
    "year_of_study",
    "gender",
    "financial_need",
    "english",
}
RULE_OPS = {"eq", "gte", "lte", "in", "between", "english"}


class SourceError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SourceError("Enter a full http or https link.")
    if parsed.username or parsed.password:
        raise SourceError("Links with a username or password are not accepted.")
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if not host or host in {"localhost"} or host.endswith(".local") or host.endswith(".internal"):
        raise SourceError("That link points at a private address.")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror as exc:
            raise SourceError("That address could not be resolved.") from exc
        addresses = [item[4][0] for item in infos]
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise SourceError("That link points at a private address.")
    return raw


def _robots_allows(text: str, path: str) -> bool:
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal agents, rules
        if agents or rules:
            groups.append((agents, rules))
        agents, rules = [], []

    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if rules:
                flush()
            agents.append(value.lower())
        elif key in {"allow", "disallow"}:
            rules.append((key, value))
    flush()

    selected: list[tuple[str, str]] = []
    for group_agents, group_rules in groups:
        if "*" in group_agents or "e-scholarcatalogbot" in group_agents:
            selected = group_rules
            if "e-scholarcatalogbot" in group_agents:
                break
    best: tuple[str, str] | None = None
    for kind, prefix in selected:
        if prefix and path.startswith(prefix) and (best is None or len(prefix) > len(best[1])):
            best = (kind, prefix)
    return best is None or best[0] == "allow"


def _check_robots(client: httpx.Client, url: str) -> None:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        validate_public_url(robots_url)
        response = client.get(robots_url, timeout=5.0)
    except (SourceError, httpx.HTTPError):
        return
    if response.status_code != 200 or "text" not in response.headers.get("content-type", ""):
        return
    path = parsed.path or "/"
    if not _robots_allows(response.text[:100_000], path):
        raise SourceError("That site's robots.txt disallows this page. Use a page the site allows, or enter the scholarship by hand.")


_SKIP_PATHS = (
    "imprint",
    "privacy",
    "datenschutz",
    "cookie",
    "newsletter",
    "login",
    "search",
    "contact",
    "accessibility",
    "barrierefreiheit",
)
_SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".doc", ".docx")
CRAWL_PAGE_CAP = {1: 1, 2: 160, 3: 200}


def _skipped_path(path: str) -> bool:
    blocked = set(_SKIP_PATHS)
    for segment in path.split("/"):
        if not segment:
            continue
        words = set(segment.replace("-", " ").split())
        if segment in blocked or words & blocked:
            return True
        if any(word in segment for word in ("privacy", "datenschutz", "cookie", "newsletter", "imprint", "barrierefreiheit")):
            return True
    return False


def _site_stem(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for prefix in ("www2.", "www."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def discover_pages(html: str, page_url: str, limit: int = 40) -> list[dict]:
    """Same-site programme links. Menus inside the page are kept; the footer is not."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "footer"]):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": "contentinfo"}):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    found = []
    seen = set()
    stem = _site_stem(page_url)
    for link in root.find_all("a", href=True):
        raw = link["href"].strip()
        if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, raw)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or _site_stem(absolute) != stem:
            continue
        path = parsed.path.casefold()
        if path.endswith(_SKIP_EXTENSIONS) or _skipped_path(path):
            continue
        label = " ".join(link.get_text(" ", strip=True).split())
        folded = label.casefold()
        named_programme = 12 <= len(label) <= 140 and path.count("/") >= 2
        interesting = (
            "detail=" in parsed.query.casefold()
            or any(word in path for word in ("scholarship", "stipend", "funding", "programme", "program"))
            or any(word in folded for word in ("scholarship", "funding", "programme", "program", "stipend", "applicant"))
            or named_programme
        )
        if not interesting:
            continue
        clean = parsed._replace(fragment="").geturl()
        if clean.rstrip("/") == page_url.rstrip("/") or clean in seen:
            continue
        seen.add(clean)
        title = label[:140] or parsed.path.rstrip("/").split("/")[-1].replace("-", " ")
        found.append({"title": title, "url": clean})
        if len(found) >= limit:
            break
    found.extend(linked_catalogue(html, page_url))
    found.sort(key=lambda item: (_link_rank(item["url"]), item["title"].casefold()))
    unique = []
    seen_urls = set()
    for item in found:
        key = item["url"].rstrip("/")
        if key in seen_urls or key == page_url.rstrip("/"):
            continue
        seen_urls.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def _link_rank(url: str) -> int:
    folded = url.casefold()
    if "detail=" in folded:
        return 0
    if any(word in folded for word in ("scholarship", "stipend", "funding")):
        return 1
    return 2


def scholarship_catalogue(script_text: str, basic_url: str) -> list[dict]:
    start, end = script_text.find("["), script_text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        rows = json.loads(script_text[start : end + 1])
    except json.JSONDecodeError:
        return []
    pages = []
    seen = set()
    base = basic_url.split("?", 1)[0]
    for row in rows:
        if not isinstance(row, dict) or not row.get("sapProgid"):
            continue
        url = f"{base}?detail={row['sapProgid']}"
        if url in seen:
            continue
        seen.add(url)
        title = str(row.get("programmnameEn") or row.get("nameEn") or "Scholarship").strip()
        pages.append({"title": title[:140], "url": url})
    return pages


def linked_catalogue(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    script_url = ""
    basic_url = ""
    for script in soup.find_all("script"):
        source = script.get("src") or ""
        if "scholarships.js" in source:
            script_url = urljoin(page_url, source)
        raw = script.string or ""
        if "var basicLink" in raw:
            match = re.search(r"var basicLink = '([^']+)'", raw)
            if match:
                basic_url = urljoin(page_url, match.group(1))
    if "detail=" in urlparse(page_url).query.casefold() or not script_url or not basic_url:
        return []
    try:
        _final, text = fetch_public_html(script_url, allow_script=True)
    except SourceError:
        return []
    return scholarship_catalogue(text, basic_url)


def discover_links(html: str, page_url: str, limit: int = 40) -> list[str]:
    return [item["url"] for item in discover_pages(html, page_url, limit)]


def _robots_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _allow_origin(client: httpx.Client, url: str, robots: dict | None) -> None:
    if robots is None:
        _check_robots(client, url)
        return
    origin = _robots_origin(url)
    if origin in robots:
        return
    _check_robots(client, url)
    robots[origin] = True


def fetch_public_html(
    url: str,
    *,
    allow_script: bool = False,
    client: httpx.Client | None = None,
    robots: dict | None = None,
) -> tuple[str, str]:
    current = validate_public_url(url)
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=12.0, follow_redirects=False, headers=FETCH_HEADERS)
    try:
        _allow_origin(client, current, robots)
        for _ in range(4):
            try:
                response = client.get(current)
            except httpx.HTTPError as exc:
                raise SourceError("The page could not be fetched. Check the link and try again.") from exc
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise SourceError("The page redirected without a destination.")
                current = validate_public_url(urljoin(current, location))
                _allow_origin(client, current, robots)
                continue
            if response.status_code >= 400:
                raise SourceError(f"The page returned status {response.status_code}.")
            content_type = response.headers.get("content-type", "")
            allowed = ("html", "text/plain", "javascript", "ecmascript", "json") if allow_script else ("html", "text/plain")
            if not any(kind in content_type for kind in allowed):
                raise SourceError("That link is not an HTML page.")
            body = response.content[: MAX_BYTES + 1]
            if len(body) > MAX_BYTES:
                raise SourceError("That page is too large to review.")
            return current, body.decode(response.encoding or "utf-8", errors="replace")
        raise SourceError("The page redirected too many times.")
    finally:
        if owns_client:
            client.close()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _iso_date(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def _find_deadline(text: str) -> str:
    lowered = text.lower()
    window = text
    index = lowered.find("deadline")
    if index >= 0:
        window = text[max(0, index - 40) : index + 180]
    patterns = [
        (window, re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")),
        (window, re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b")),
        (window, re.compile(r"\b([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})\b")),
        (text, re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")),
        (text, re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b")),
        (window, re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b")),
        (text, re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b")),
    ]
    for sample, pattern in patterns:
        match = pattern.search(sample)
        if not match:
            continue
        parts = match.groups()
        if parts[0].isdigit() and len(parts[0]) == 4:
            found = _iso_date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif parts[1].isdigit() and len(parts[1]) <= 2 and parts[2].isdigit() and "." in match.group(0):
            found = _iso_date(int(parts[2]), int(parts[1]), int(parts[0]))
        elif parts[0].isdigit():
            month = MONTHS.get(parts[1].lower())
            found = _iso_date(int(parts[2]), month, int(parts[0])) if month else None
        else:
            month = MONTHS.get(parts[0].lower())
            found = _iso_date(int(parts[2]), month, int(parts[1])) if month else None
        if found:
            return found
    return ""


def _section_items(soup: BeautifulSoup, keywords: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for header in soup.find_all(["h2", "h3", "h4", "strong"]):
        label = header.get_text(" ", strip=True).lower()
        if not any(keyword in label for keyword in keywords):
            continue
        listing = header.find_next(["ul", "ol"])
        if listing is None:
            continue
        for item in listing.find_all("li"):
            text = _clean(item.get_text(" ", strip=True))
            if text and text not in found:
                found.append(text[:180])
            if len(found) >= 8:
                return found
    return found


def _json_ld(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict) and (item.get("name") or item.get("headline")):
                return item
    return {}


def _add_rule(rules: list[dict], field: str, op: str, value, label: str) -> None:
    if any(rule["field"] == field for rule in rules):
        return
    rules.append({"field": field, "op": op, "value": value, "label": label})


def suggest_criteria(text: str) -> list[dict]:
    rules: list[dict] = []
    gpa = re.search(r"GPA(?:\s+of|\s+at least|\s+minimum(?:\s+of)?|\s*>=)?\s*(\d+(?:\.\d+)?)", text, re.I)
    if gpa:
        _add_rule(rules, "gpa", "gte", float(gpa.group(1)), f"GPA is at least {gpa.group(1)} on a 4.0 scale")
    ielts = re.search(r"IELTS(?:\s+Academic)?(?:\s+score)?(?:\s+of|\s+at least)?\s*(\d+(?:\.\d+)?)", text, re.I)
    toefl = re.search(r"TOEFL(?:\s+iBT)?(?:\s+score)?(?:\s+of|\s+at least)?\s*(\d+(?:\.\d+)?)", text, re.I)
    if ielts or toefl:
        thresholds = {
            "ielts": float(ielts.group(1)) if ielts else 6.5,
            "toefl": float(toefl.group(1)) if toefl else 80,
        }
        _add_rule(
            rules,
            "english",
            "english",
            thresholds,
            f"English result is IELTS {thresholds['ielts']} or TOEFL {thresholds['toefl']}",
        )
    if re.search(r"ethiopian citizens|citizens of ethiopia|must be ethiopian", text, re.I):
        _add_rule(rules, "citizenship", "eq", "Ethiopian", "Citizenship is Ethiopian")
    if re.search(r"(residing|resident|studying|living) in ethiopia|country of residence[^.]{0,40}ethiopia", text, re.I):
        _add_rule(rules, "country", "eq", "Ethiopia", "Country of residence is Ethiopia")
    if re.search(r"open to women|female (students|applicants) only|must be female", text, re.I):
        _add_rule(rules, "gender", "eq", "Female", "Gender is Female")
    level = study_level(text[:240], text)
    if level:
        _add_rule(rules, "degree_level", "eq", level, f"Degree level is {level}")
    return rules[:6]


def extract_scholarship(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    linked = _json_ld(soup)
    root = content_root(soup)
    title = _clean(
        (soup.find("meta", property="og:title") or {}).get("content", "")
        if soup.find("meta", property="og:title")
        else ""
    )
    if not title and root.find("h1"):
        title = _clean(root.find("h1").get_text(" ", strip=True))
    if not title and soup.title:
        title = _clean(soup.title.get_text(" ", strip=True))
    if soup.title:
        document_title = re.split(r"\s+-\s+DAAD\b", _clean(soup.title.get_text(" ", strip=True)), maxsplit=1)[0]
        if document_title and title.casefold() in {"finding scholarships", "scholarship database", "scholarships & funding"}:
            title = document_title
    title = re.split(r"\s+\|\s+", title or "Untitled scholarship", maxsplit=1)[0][:180]
    if linked.get("name"):
        candidate = _clean(str(linked["name"]))[:180]
        if candidate.casefold() not in {"finding scholarships", "scholarship database", "scholarships & funding"}:
            title = candidate or title
    description = ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta and meta.get("content"):
        description = _clean(meta["content"])
    if not description and linked.get("description"):
        description = _clean(str(linked["description"]))
    if not description:
        paragraph = root.find("p")
        description = _clean(paragraph.get_text(" ", strip=True) if paragraph else "")[:500]
    text = root.get_text("\n", strip=True)
    deadline = ""
    if isinstance(linked.get("endDate"), str):
        deadline = linked["endDate"][:10]
    if not deadline:
        deadline = _find_deadline(text)
    host = urlparse(url).hostname or ""
    documents = _section_items(root, ("document", "what to submit", "you will need", "application checklist"))
    notes = _section_items(root, ("eligib", "who can apply", "requirements", "criteria"))
    blocks = section_blocks(root)
    links = related_pages(root, url)
    known = {item["url"].rstrip("/") for item in links}
    for item in discover_pages(html, url):
        key = item["url"].rstrip("/")
        if key not in known:
            links.append(item)
            known.add(key)
    country = "Germany" if "germany" in text.casefold() or "daad" in host.casefold() else ""
    sections = assemble_sections(
        title=title,
        summary=description,
        deadline=deadline,
        documents=documents,
        notes=notes,
        blocks=blocks,
        links=links,
        host_country=country,
    )
    if sections["page_kind"] == "directory" and not description:
        description = "This page lists funding programmes. Open one scholarship and fetch that page."
    record = {
        "name": title or "Untitled scholarship",
        "provider": provider_name(host),
        "deadline": deadline,
        "summary": (description or blocks.get("overview") or "Review the source page and write a short summary.")[:600],
        "required_documents": documents,
        "criteria": [
            rule
            for rule in suggest_criteria(f"{title}\n{text}")
            if sections["page_kind"] == "scholarship" or rule["field"] != "degree_level"
        ],
        "eligibility_notes": (sections["blocks"].get("who_can_apply") or "\n".join(notes))[:2000],
        "excerpt": (
            "\n".join(part for part in sections["blocks"].values() if part).strip() or text
        )[:3500],
        "source_url": url,
        "sections": sections,
    }
    record["missing"] = missing_facts(record, sections)
    return record


def _number(value, label: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SourceError(f"{label} must be a number.") from exc


def normalize_criteria(raw_rules, scholarship_id: str) -> list[dict]:
    if not isinstance(raw_rules, list):
        raise SourceError("Criteria must be a list.")
    normalized = []
    for index, raw in enumerate(raw_rules, start=1):
        if not isinstance(raw, dict):
            raise SourceError("Each criterion must be an object.")
        field = str(raw.get("field") or "").strip()
        op = str(raw.get("op") or "").strip()
        if field not in RULE_FIELDS or op not in RULE_OPS:
            raise SourceError("A criterion uses an unknown field or comparison.")
        if op == "english" and field != "english":
            field = "english"
        value = raw.get("value")
        if op == "in":
            if isinstance(value, str):
                value = [part.strip() for part in value.split(",") if part.strip()]
            if not isinstance(value, list) or not value:
                raise SourceError("An 'is one of' rule needs at least one value.")
        elif op == "between":
            if isinstance(value, str):
                parts = [part.strip() for part in value.split(",")]
                if len(parts) != 2:
                    raise SourceError("A between rule needs two numbers, such as 1, 4.")
                value = parts
            if not isinstance(value, list) or len(value) != 2:
                raise SourceError("A between rule needs two numbers.")
            value = [_number(value[0], "Between"), _number(value[1], "Between")]
        elif op == "english":
            if isinstance(value, str):
                parts = [part.strip() for part in value.split(",")]
                if len(parts) != 2:
                    raise SourceError("An English rule needs IELTS and TOEFL minimums, such as 6.5, 80.")
                value = {"ielts": _number(parts[0], "IELTS"), "toefl": _number(parts[1], "TOEFL")}
            elif isinstance(value, dict):
                value = {"ielts": _number(value.get("ielts"), "IELTS"), "toefl": _number(value.get("toefl"), "TOEFL")}
            else:
                raise SourceError("An English rule needs IELTS and TOEFL minimums.")
        elif op in {"gte", "lte"}:
            value = _number(value, "The rule value")
        elif field == "financial_need":
            value = str(value).strip().lower() in {"yes", "true", "1"}
        else:
            value = str(value or "").strip()
            if not value:
                raise SourceError("A criterion is missing its expected value.")
        label = _clean(str(raw.get("label") or "")) or f"{field} {op} {value}"
        normalized.append(
            {
                "id": f"{scholarship_id}-C{index}",
                "label": label[:180],
                "field": field,
                "op": op,
                "value": value,
            }
        )
    return normalized


def validate_for_publish(record: dict) -> None:
    if not _clean(record.get("name", "")):
        raise SourceError("Add the scholarship name before publishing.")
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", record.get("deadline") or ""):
        raise SourceError("Add a deadline as YYYY-MM-DD before publishing.")
    if len(_clean(record.get("summary", ""))) < 20:
        raise SourceError("Add a short summary of at least 20 characters before publishing.")
    if len(record.get("criteria") or []) < 2:
        raise SourceError("Publish only after at least two explicit rules are confirmed.")
    if (record.get("sections") or {}).get("page_kind") == "directory":
        raise SourceError("This page lists programmes. Fetch one scholarship link, then confirm its deadline and rules.")


def source_payload(row) -> dict:
    fetched = row.fetched_at
    if isinstance(fetched, datetime):
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        fetched = fetched.astimezone(timezone.utc).isoformat()
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "deadline": row.deadline,
        "summary": row.summary,
        "required_documents": list(row.required_documents or []),
        "criteria": list(row.criteria or []),
        "source_url": row.source_url,
        "status": row.status,
        "origin": row.origin,
        "eligibility_notes": row.eligibility_notes or "",
        "excerpt": row.excerpt or "",
        "sections": row.sections or {},
        "missing": missing_facts(
            {
                "name": row.name,
                "provider": row.provider,
                "deadline": row.deadline,
                "summary": row.summary,
                "eligibility_notes": row.eligibility_notes,
                "required_documents": row.required_documents,
                "criteria": row.criteria,
            },
            row.sections or {},
        ),
        "fetched_at": fetched,
    }
