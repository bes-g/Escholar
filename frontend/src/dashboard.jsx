import { useEffect, useState } from "react";
import { request } from "./api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDate(iso) {
  if (!iso) return "";
  const [date] = String(iso).split("T");
  const [year, month, day] = date.split("-");
  if (!year || !month || !day) return iso;
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

export function DashboardPage({ onOpenProfile }) {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    request("/api/dashboard")
      .then((data) => {
        if (!cancelled) setBoard(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <section className="panel">
        <h2>Dashboard</h2>
        <div className="banner" role="alert">
          <p>{error.message}</p>
        </div>
      </section>
    );
  }
  if (!board) {
    return (
      <section className="panel">
        <p>Loading your dashboard…</p>
      </section>
    );
  }

  return (
    <>
      <section className="panel">
        <h2>{board.student_name ? `Hello, ${board.student_name}` : "Your dashboard"}</h2>
        <p className="muted">
          {board.level?.label
            ? `Matches below use your ${board.level.label} profile. Eligibility still comes from the catalog rules.`
            : "Choose a student type on your profile so the form and the matches follow your studies."}
        </p>
        {board.needs_level && (
          <div className="actions">
            <button type="button" className="primary" onClick={onOpenProfile}>
              Complete profile
            </button>
          </div>
        )}
      </section>
      <div className="stat-grid">
        <article className="stat">
          <span>Eligible</span>
          <strong>{board.counts.eligible}</strong>
        </article>
        <article className="stat">
          <span>Needs a fact</span>
          <strong>{board.counts.undetermined}</strong>
        </article>
        <article className="stat">
          <span>New notices</span>
          <strong>{board.counts.notifications}</strong>
        </article>
      </div>
      <div className="layout">
        <section className="panel">
          <h2>Relevant scholarships</h2>
          {!board.profile_ready && <p>Finish the profile before matches can be calculated.</p>}
          {board.profile_ready && board.matches.length === 0 && <p>No published scholarship matches this profile yet.</p>}
          <div className="plan-list">
            {board.matches.map((item) => (
              <article key={item.id} className="plan-item">
                <h4>
                  {item.name} <span className={`pill pill-${item.status}`}>{item.status}</span>
                </h4>
                <p>
                  {item.id} · {item.provider} · Deadline {formatDate(item.deadline)}
                </p>
                <p>{item.summary}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>Notices</h2>
          <p className="muted">
            {board.email_configured
              ? "A match is emailed and listed here."
              : "Matches are listed here. Email is sent once SMTP is configured on the server."}
          </p>
          {board.notifications.length === 0 && <p>No match has been recorded yet.</p>}
          <div className="plan-list">
            {board.notifications.map((item) => (
              <article key={item.id} className="plan-item">
                <h4>
                  {item.title} <span>{item.reason}</span>
                </h4>
                <p>{item.body}</p>
                <p className="muted">Email: {item.email_status}</p>
              </article>
            ))}
          </div>
          {board.related?.length > 0 && (
            <>
              <h3>Similar passages</h3>
              <div className="plan-list">
                {board.related.map((item) => (
                  <article key={item.chunk_id} className="plan-item">
                    <h4>
                      {item.name} <span>{item.score}</span>
                    </h4>
                    <p>{item.passage}</p>
                  </article>
                ))}
              </div>
            </>
          )}
          {board.related_note && <p className="muted">{board.related_note}</p>}
        </section>
      </div>
    </>
  );
}
