from app.record import vector_documents
from app.sources import discover_links, extract_scholarship


DAAD_HUB = """
<html>
  <head><title>Scholarships & Funding - DAAD</title></head>
  <body>
    <nav>
      <a href="/en/">Study & research in Germany</a>
      <a href="/en/imprint/">Imprint</a>
    </nav>
    <main>
      <h1>Scholarships & Funding</h1>
      <p>International students can apply to numerous organisations for a scholarship, for example to the DAAD, to party-related foundations or business-affiliated institutions. You can find information on the various types of scholarships in the DAAD scholarship database.</p>
      <a href="/en/find-scholarships/">Find Scholarships</a>
      <a href="/en/daad-scholarships/">DAAD-Scholarships – An Overview</a>
      <a href="/en/applicants/">Information for Scholarship Applicants</a>
      <a href="/en/artists/">Funding Programmes for Musicians and Artists</a>
      <a href="/en/other-funding/">Other Funding Options</a>
      <p>© Büssemeier / DAAD</p>
      <h2>Address</h2>
      <p>Deutscher Akademischer Austauschdienst e.V. Kennedyallee 50, 53175 Bonn, Germany</p>
      <a href="/en/phd/">PhD Studies and Research</a>
    </main>
    <footer>
      <p>Deutscher Akademischer Austauschdienst e.V. Kennedyallee 50, 53175 Bonn</p>
      <a href="/en/privacy/">Data Privacy Statement</a>
    </footer>
  </body>
</html>
"""


DAAD_AWARD = """
<html>
  <head><title>Study Scholarships - Master Studies for All Academic Disciplines</title></head>
  <body>
    <main>
      <h1>Study Scholarships - Master Studies for All Academic Disciplines</h1>
      <p>This scholarship offers a postgraduate degree at a German university.</p>
      <h2>Who can apply?</h2>
      <p>You can apply after a first degree. The programme is aimed at graduates from any discipline.</p>
      <h2>What can be funded?</h2>
      <p>A full Master's degree in Germany for 10 to 24 months, with a monthly payment of 992 euros.</p>
      <h2>Application deadline</h2>
      <p>The application deadline is 31.08.2026.</p>
      <h2>Application documents</h2>
      <ul><li>Curriculum vitae</li><li>Letter of motivation</li></ul>
      <h2>Application procedure</h2>
      <p>Submit the application in the DAAD portal.</p>
    </main>
  </body>
</html>
"""


def test_programme_links_inside_the_page_menu_are_kept():
    html = """
    <html><body><main>
      <nav>
        <a href="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/">Scholarship database</a>
        <a href="/en/studying-in-germany/scholarships/daad-scholarships/">DAAD-Scholarships - An Overview</a>
        <a href="/en/studying-in-germany/phd-studies-research/">PhD Studies and Research</a>
        <a href="/en/imprint/">Imprint</a>
      </nav>
      <p>International students can apply for a scholarship in any field of study at a German university.</p>
    </main>
    <footer><a href="/en/privacy/">Data Privacy Statement</a></footer>
    </body></html>
    """
    links = discover_links(html, "https://www.daad.de/en/studying-in-germany/scholarships/")
    assert any("scholarship-database" in link for link in links)
    assert any(link.endswith("/daad-scholarships/") for link in links)
    assert any(link.endswith("/phd-studies-research/") for link in links)
    assert not any("imprint" in link or "privacy" in link for link in links)


def test_scholarship_catalogue_lists_programmes_by_id():
    from app.sources import scholarship_catalogue

    script = 'var scholarships = TAFFY([{"sapProgid":10000092,"programmnameEn":"Prussian Cultural Heritage Foundation: Grant Programme"}]);'
    pages = scholarship_catalogue(script, "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/")
    assert pages == [
        {
            "title": "Prussian Cultural Heritage Foundation: Grant Programme",
            "url": "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=10000092",
        }
    ]


def test_depth_follows_scholarship_links_and_stops():
    links = discover_links(DAAD_HUB, "https://www.daad.de/en/studying-in-germany/scholarships/")
    assert "https://www.daad.de/en/find-scholarships/" in links
    assert "https://www.daad.de/en/privacy/" not in links
    assert all("Kennedyallee" not in link for link in links)


def test_crawl_stores_linked_pages_at_the_chosen_depth(client, monkeypatch):
    hub = DAAD_HUB.replace("https://www.daad.de", "https://example.edu")
    html_by_url = {
        "https://example.edu/scholarships": hub,
        "https://example.edu/en/find-scholarships/": DAAD_AWARD,
        "https://example.edu/en/daad-scholarships/": DAAD_AWARD.replace(
            "Master Studies for All Academic Disciplines", "Law Scholarships"
        ),
    }

    def fake_fetch(url, **_kwargs):
        if url not in html_by_url:
            from app.sources import SourceError

            raise SourceError(f"missing {url}")
        return url, html_by_url[url]

    monkeypatch.setattr("app.main.fetch_public_html", fake_fetch)
    client.cookies.clear()
    from tests.test_accounts import _profile

    client.post("/api/signup", json={"email": "crawl@example.com", "password": "long-secret", "profile": _profile()})
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    user = db.query(User).filter(User.email == "crawl@example.com").one()
    user.role = "admin"
    db.commit()
    db.close()
    created = client.post("/api/sources", json={"url": "https://example.edu/scholarships"})
    assert created.status_code == 200
    result = client.post(f"/api/sources/{created.json()['id']}/crawl", json={"depth": 2})
    assert result.status_code == 200
    body = result.json()
    assert body["depth"] == 2
    assert body["stored"] >= 1
    stored = [item for item in body["pages"] if item["status"] == "stored" and item["depth"] == 2]
    assert stored
    assert all(item["url"].startswith("https://example.edu/") for item in stored)
    for item in body["pages"]:
        if item["id"]:
            client.delete(f"/api/sources/{item['id']}")
    client.post("/api/logout")
    client.cookies.clear()


def test_daad_hub_is_a_programme_list_not_one_scholarship():
    record = extract_scholarship(DAAD_HUB, "https://www.daad.de/en/study-and-research-in-germany/scholarships/")
    assert record["provider"] == "DAAD"
    assert record["sections"]["page_kind"] == "directory"
    assert record["deadline"] == ""
    titles = {item["title"] for item in record["sections"]["related_pages"]}
    assert "Find Scholarships" in titles
    assert "Kennedyallee" not in record["excerpt"]
    assert "Kennedyallee" not in record["sections"]["blocks"]["overview"]
    assert "Büssemeier" not in record["sections"]["blocks"]["overview"]
    assert "Data Privacy" not in record["summary"]
    assert all(rule["field"] != "degree_level" for rule in record["criteria"])
    assert any("lists programmes" in item for item in record["missing"])


def test_one_daad_scholarship_is_split_into_match_facts():
    record = extract_scholarship(DAAD_AWARD, "https://www.daad.de/en/scholarships/master/")
    assert record["sections"]["page_kind"] == "scholarship"
    assert record["deadline"] == "2026-08-31"
    assert record["sections"]["study_level"] == "Master"
    assert "992 euros" in record["sections"]["blocks"]["funding"]
    assert "DAAD portal" in record["sections"]["blocks"]["how_to_apply"]
    assert "Curriculum vitae" in record["required_documents"]
    assert any(rule["field"] == "degree_level" and rule["value"] == "Master" for rule in record["criteria"])
    docs = vector_documents(
        record["name"],
        record["provider"],
        record["source_url"],
        record["summary"],
        record["deadline"],
        record["eligibility_notes"],
        record["required_documents"],
        record["criteria"],
        record["sections"],
    )
    by_section = {item["section"]: item["text"] for item in docs}
    assert "992 euros" in by_section["funding"]
    assert "992 euros" not in by_section["who_can_apply"]
    assert "Curriculum vitae" in by_section["documents"]


def test_scraped_files_survive_startup_and_reload(client, tmp_path, monkeypatch):
    from app.catalog import seed_catalog
    from app.database import SessionLocal
    from app.models import Scholarship
    from app.scrapes import catalogue_records, load_scrapes, write_scrape

    assert client.get("/api/catalog").status_code == 200
    monkeypatch.setattr("app.scrapes.SCRAPE_DIR", tmp_path)
    script = (
        'var scholarships = TAFFY([{"sapProgid":99900001,'
        '"programmnameEn":"Prussian Cultural Heritage Foundation: Grant Programme",'
        '"introduction":{"en":"The programme enables academics to undertake research residencies."}}]);'
    )
    records = catalogue_records(script)
    assert len(records) == 1
    assert records[0]["id"] == "DAAD-99900001"
    assert records[0]["source_url"].endswith("?detail=99900001")
    write_scrape(records[0])

    db = SessionLocal()
    try:
        seed_catalog(db)
        assert db.get(Scholarship, "DAAD-99900001") is None
        assert load_scrapes(db) == 1
        kept = db.get(Scholarship, "DAAD-99900001")
        assert kept is not None
        assert kept.origin == "url"
        assert kept.status == "draft"
        seed_catalog(db)
        assert db.get(Scholarship, "DAAD-99900001") is not None
        assert load_scrapes(db) == 0
    finally:
        db.rollback()
        row = db.get(Scholarship, "DAAD-99900001")
        if row is not None:
            db.delete(row)
            db.commit()
        db.close()
