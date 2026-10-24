import { useEffect, useState } from "react";
import { request } from "./api";

const FIELDS = [
  ["gpa", "GPA"],
  ["year_of_study", "Year of study"],
  ["country", "Country of residence"],
  ["citizenship", "Citizenship"],
  ["degree_level", "Degree level"],
  ["field_of_study", "Field of study"],
  ["gender", "Gender"],
  ["financial_need", "Financial need"],
  ["english", "English test"],
];

const OPS = [
  ["eq", "equals"],
  ["gte", "at least"],
  ["lte", "at most"],
  ["in", "is one of"],
  ["between", "between"],
  ["english", "IELTS / TOEFL"],
];

function valueToInput(rule) {
  if (!rule) return "";
  if (rule.op === "in" && Array.isArray(rule.value)) return rule.value.join(", ");
  if (rule.op === "between" && Array.isArray(rule.value)) return rule.value.join(", ");
  if (rule.op === "english" && rule.value && typeof rule.value === "object") {
    return `${rule.value.ielts ?? ""}, ${rule.value.toefl ?? ""}`;
  }
  if (typeof rule.value === "boolean") return rule.value ? "yes" : "no";
  return rule.value ?? "";
}

function emptyRule() {
  return { field: "gpa", op: "gte", value: "", label: "" };
}

function toEditor(source) {
  return {
    ...source,
    documentsText: (source.required_documents || []).join("\n"),
    criteria: (source.criteria || []).map((rule) => ({
      field: rule.field,
      op: rule.op,
      label: rule.label || "",
      value: valueToInput(rule),
    })),
  };
}

const SECTION_FIELDS = [
  ["overview", "Overview"],
  ["who_can_apply", "Who can apply"],
  ["academic_requirements", "Academic requirements"],
  ["funding", "What is funded"],
  ["dates", "Deadline and duration"],
  ["documents", "Documents"],
  ["how_to_apply", "How to apply"],
];

function toPayload(editor) {
  return {
    name: editor.name,
    provider: editor.provider,
    deadline: editor.deadline,
    summary: editor.summary,
    eligibility_notes: editor.eligibility_notes,
    required_documents: editor.documentsText.split("\n"),
    sections: editor.sections || {},
    criteria: editor.criteria.map((rule) => ({
      field: rule.op === "english" ? "english" : rule.field,
      op: rule.op,
      value: rule.value,
      label: rule.label,
    })),
  };
}

export function SourcesPage() {
  const [sources, setSources] = useState([]);
  const [url, setUrl] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [editor, setEditor] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [depth, setDepth] = useState(2);
  const [crawlNote, setCrawlNote] = useState("");

  async function refresh() {
    const data = await request("/api/sources");
    setSources(data.sources || []);
    return data.sources || [];
  }

  useEffect(() => {
    refresh().catch((err) => setError(err));
  }, []);

  function openSource(source) {
    setSelectedId(source.id);
    setEditor(toEditor(source));
    setError(null);
  }

  async function addSource(event) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const created = await request("/api/sources", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      setUrl("");
      await refresh();
      openSource(created);
      if (depth > 1) {
        const result = await request(`/api/sources/${created.id}/crawl`, {
          method: "POST",
          body: JSON.stringify({ depth }),
        });
        const rows = await refresh();
        const current = rows.find((item) => item.id === created.id);
        if (current) openSource(current);
        setCrawlNote(
          `Depth ${result.depth}: stored ${result.stored}, already saved ${result.skipped}, failed ${result.failed}. Limit ${result.limit} pages.`,
        );
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function save(publish) {
    setLoading(true);
    setError(null);
    try {
      const path = publish ? `/api/sources/${selectedId}/publish` : `/api/sources/${selectedId}`;
      const saved = await request(path, {
        method: publish ? "POST" : "PUT",
        body: JSON.stringify(toPayload(editor)),
      });
      await refresh();
      openSource(saved);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function unpublish() {
    setLoading(true);
    setError(null);
    try {
      const saved = await request(`/api/sources/${selectedId}/unpublish`, { method: "POST" });
      await refresh();
      openSource(saved);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function remove() {
    setLoading(true);
    setError(null);
    try {
      await request(`/api/sources/${selectedId}`, { method: "DELETE" });
      setSelectedId(null);
      setEditor(null);
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  function updateRule(index, key, value) {
    setEditor((current) => {
      const criteria = current.criteria.map((rule, ruleIndex) => {
        if (ruleIndex !== index) return rule;
        const next = { ...rule, [key]: value };
        if (key === "op" && value === "english") next.field = "english";
        return next;
      });
      return { ...current, criteria };
    });
  }

  return (
    <div className="source-layout">
      <section className="panel">
        <h2>Scholarship sources</h2>
        <p className="muted">
          Administrator review. Paste a public scholarship page, or the DAAD scholarship database. Depth 2 stores each
          scholarship linked from that page. Nothing is used for matching until you publish it.
        </p>
        {error && (
          <div className="banner" role="alert">
            <p>{error.message}</p>
          </div>
        )}
        <form onSubmit={addSource}>
          <div className="grid">
            <label className="wide">
              <span>Page link</span>
              <input
                type="url"
                placeholder="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
              />
            </label>
            <label>
              <span>Depth</span>
              <input
                type="number"
                min={1}
                max={3}
                value={depth}
                onChange={(event) => setDepth(Number(event.target.value))}
              />
              <small>
                1 keeps this page. 2 stores each scholarship linked from it, up to 160 pages. 3 follows those pages one
                step further, up to 200.
              </small>
            </label>
          </div>
          <div className="actions">
            <button type="submit" className="primary" disabled={loading}>
              {loading ? "Collecting…" : depth > 1 ? "Fetch and collect" : "Fetch page"}
            </button>
          </div>
          {crawlNote && <p className="note">{crawlNote}</p>}
        </form>
        <div className="plan-list">
          {sources.length === 0 && <p className="muted">No sources yet.</p>}
          {sources.map((source) => (
            <button
              type="button"
              key={source.id}
              className={selectedId === source.id ? "plan-pick on" : "plan-pick"}
              onClick={() => openSource(source)}
            >
              <strong>{source.name}</strong>
              <span>
                {source.status} · {source.id}
                {source.sections?.crawl_depth ? ` · depth ${source.sections.crawl_depth}` : ""}
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        {!editor && (
          <div className="empty">
            <p>Fetched pages stay as drafts. Publishing adds the scholarship to the catalog the adviser searches.</p>
          </div>
        )}
        {editor && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              save(false);
            }}
          >
            <p className="kicker">
              {editor.status} · {editor.id}
            </p>
            <h2>{editor.name || "Review source"}</h2>
            {editor.source_url && (
              <p>
                <a href={editor.source_url} target="_blank" rel="noreferrer">
                  {editor.source_url}
                </a>
              </p>
            )}
            <div className="grid">
              <label>
                <span>Depth</span>
                <input
                  type="number"
                  min={1}
                  max={3}
                  value={depth}
                  onChange={(event) => setDepth(Number(event.target.value))}
                />
                <small>
                  1 keeps this page. 2 stores each scholarship linked from it, up to 160 pages. 3 follows those pages
                  one step further, up to 200. Every field of study on those pages is kept.
                </small>
              </label>
            </div>
            <div className="actions">
              <button
                type="button"
                className="primary"
                disabled={loading}
                onClick={async () => {
                  setLoading(true);
                  setError(null);
                  setCrawlNote("");
                  try {
                    const result = await request(`/api/sources/${selectedId}/crawl`, {
                      method: "POST",
                      body: JSON.stringify({ depth }),
                    });
                    await refresh();
                    setCrawlNote(
                      `Depth ${result.depth}: stored ${result.stored}, already saved ${result.skipped}, failed ${result.failed}. Limit ${result.limit} pages.`,
                    );
                  } catch (err) {
                    setError(err);
                  } finally {
                    setLoading(false);
                  }
                }}
              >
                {loading ? "Collecting…" : "Collect into the database"}
              </button>
            </div>
            {crawlNote && <p className="note">{crawlNote}</p>}
            {editor.missing?.length > 0 && (
              <div className="banner">
                <p>{editor.sections?.page_kind === "directory" ? "This page is a programme list." : "Still needed for one scholarship."}</p>
                <ul>
                  {editor.missing.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {editor.sections?.related_pages?.length > 0 && (
              <div className="plan-list">
                {editor.sections.related_pages.map((page) => (
                  <button key={page.url} type="button" className="plan-pick" onClick={() => setUrl(page.url)}>
                    <strong>{page.title}</strong>
                    <span>Put this link in the fetch box</span>
                  </button>
                ))}
              </div>
            )}
            <div className="grid">
              <label className="wide">
                <span>Name</span>
                <input value={editor.name} onChange={(event) => setEditor({ ...editor, name: event.target.value })} />
              </label>
              <label>
                <span>Provider</span>
                <input value={editor.provider} onChange={(event) => setEditor({ ...editor, provider: event.target.value })} />
              </label>
              <label>
                <span>Deadline</span>
                <input
                  placeholder="YYYY-MM-DD"
                  value={editor.deadline}
                  onChange={(event) => setEditor({ ...editor, deadline: event.target.value })}
                />
              </label>
              <label className="wide">
                <span>Summary</span>
                <textarea
                  rows={3}
                  value={editor.summary}
                  onChange={(event) => setEditor({ ...editor, summary: event.target.value })}
                />
              </label>
              <label className="wide">
                <span>Required documents, one per line</span>
                <textarea
                  rows={4}
                  value={editor.documentsText}
                  onChange={(event) => setEditor({ ...editor, documentsText: event.target.value })}
                />
              </label>
              <label className="wide">
                <span>Eligibility notes from the page</span>
                <textarea
                  rows={4}
                  value={editor.eligibility_notes}
                  onChange={(event) => setEditor({ ...editor, eligibility_notes: event.target.value })}
                />
              </label>
            </div>

            <h3>Facts saved for matching</h3>
            <p className="muted">
              Each block is embedded separately. Navigation, the postal address, and the privacy links are left out.
            </p>
            {editor.sections?.blocks && (
            <div className="grid">
              {SECTION_FIELDS.map(([key, label]) => (
                <label key={key} className="wide">
                  <span>{label}</span>
                  <textarea
                    rows={3}
                    value={editor.sections.blocks[key] || ""}
                    onChange={(event) =>
                      setEditor({
                        ...editor,
                        sections: {
                          ...editor.sections,
                          blocks: { ...editor.sections.blocks, [key]: event.target.value },
                        },
                      })
                    }
                  />
                </label>
              ))}
            </div>
            )}

            <h3>Rules the checker will use</h3>
            <p className="muted">
              Suggestions are not trusted until you save them. For “is one of”, separate values with commas. For English,
              enter the IELTS minimum, then the TOEFL minimum, such as 6.5, 80.
            </p>
            {editor.criteria.map((rule, index) => (
              <div className="rule-row" key={`${editor.id}-${index}`}>
                <label>
                  <span>Fact</span>
                  <select value={rule.field} onChange={(event) => updateRule(index, "field", event.target.value)}>
                    {FIELDS.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Comparison</span>
                  <select value={rule.op} onChange={(event) => updateRule(index, "op", event.target.value)}>
                    {OPS.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Value</span>
                  <input value={rule.value} onChange={(event) => updateRule(index, "value", event.target.value)} />
                </label>
                <button
                  type="button"
                  className="quiet"
                  onClick={() =>
                    setEditor({ ...editor, criteria: editor.criteria.filter((_, ruleIndex) => ruleIndex !== index) })
                  }
                >
                  Remove
                </button>
                <label className="wide">
                  <span>Explanation shown to the student</span>
                  <input
                    value={rule.label}
                    onChange={(event) => updateRule(index, "label", event.target.value)}
                    placeholder="GPA is at least 3.5"
                  />
                </label>
              </div>
            ))}
            <div className="actions">
              <button type="button" onClick={() => setEditor({ ...editor, criteria: [...editor.criteria, emptyRule()] })}>
                Add rule
              </button>
              <button type="submit" disabled={loading}>
                Save draft
              </button>
              <button type="button" className="primary" disabled={loading} onClick={() => save(true)}>
                Publish to catalog
              </button>
              {editor.status === "published" && (
                <button type="button" disabled={loading} onClick={unpublish}>
                  Unpublish
                </button>
              )}
              {editor.status !== "published" && (
                <button type="button" className="quiet" disabled={loading} onClick={remove}>
                  Delete draft
                </button>
              )}
            </div>
            {editor.excerpt && (
              <details className="catalog">
                <summary>Text read from the page</summary>
                <pre>{editor.excerpt}</pre>
              </details>
            )}
          </form>
        )}
      </section>
    </div>
  );
}
