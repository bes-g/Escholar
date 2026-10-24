import { useEffect, useState } from "react";
import { request } from "./api";

export function ChunkingPage() {
  const [form, setForm] = useState({ small_chunk_size: 400, large_chunk_size: 1200, chunk_overlap: 80 });
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    request("/api/admin/chunking")
      .then((data) => {
        if (cancelled) return;
        setStatus(data);
        setForm({
          small_chunk_size: data.small_chunk_size,
          large_chunk_size: data.large_chunk_size,
          chunk_overlap: data.chunk_overlap,
        });
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function update(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function save(event) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await request("/api/admin/chunking", {
        method: "PUT",
        body: JSON.stringify({
          small_chunk_size: Number(form.small_chunk_size),
          large_chunk_size: Number(form.large_chunk_size),
          chunk_overlap: Number(form.chunk_overlap),
        }),
      });
      setStatus(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel auth-card">
      <h2>Chunking</h2>
      <p className="muted">
        Published scholarship text is split into a large passage and smaller pieces inside it. Both sizes are embedded
        and saved. Small chunks locate a match. Large chunks are the passage shown to the student. Saving these limits
        rebuilds every published scholarship.
      </p>
      {error && (
        <div className="banner" role="alert">
          <p>{error.message}</p>
          {error.errors?.length > 0 && (
            <ul>
              {error.errors.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {status?.last_error && <p className="note">{status.last_error}</p>}
      <form onSubmit={save}>
        <div className="grid">
          <label>
            <span>Small chunk</span>
            <input
              type="number"
              min={80}
              max={2000}
              value={form.small_chunk_size}
              onChange={(event) => update("small_chunk_size", event.target.value)}
              required
            />
            <small>80–2000 characters.</small>
          </label>
          <label>
            <span>Large chunk</span>
            <input
              type="number"
              min={200}
              max={8000}
              value={form.large_chunk_size}
              onChange={(event) => update("large_chunk_size", event.target.value)}
              required
            />
            <small>200–8000 characters, larger than the small chunk.</small>
          </label>
          <label>
            <span>Overlap</span>
            <input
              type="number"
              min={0}
              max={1999}
              value={form.chunk_overlap}
              onChange={(event) => update("chunk_overlap", event.target.value)}
              required
            />
            <small>Must be smaller than the small chunk.</small>
          </label>
        </div>
        <div className="actions">
          <button type="submit" className="primary" disabled={loading}>
            {loading ? "Embedding…" : "Save and embed"}
          </button>
        </div>
      </form>
      {status && (
        <p className="muted">
          {status.embedded_count} embeddings saved across {status.chunk_count} chunks. Store: {status.vector_store}. Model:{" "}
          {status.embedding_model} ({status.embedding_dimensions} dimensions).
          {status.pinecone_configured
            ? ` Pinecone index ${status.pinecone_index} receives a copy.`
            : " Set PINECONE_API_KEY to copy the same vectors into Pinecone."}
        </p>
      )}
    </section>
  );
}
