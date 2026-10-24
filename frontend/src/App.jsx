import { useEffect, useRef, useState } from "react";
import { request } from "./api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDate(iso) {
  if (!iso) return "";
  const [date] = String(iso).split("T");
  const [year, month, day] = date.split("-");
  if (!year || !month || !day) return iso;
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

function optionValue(option) {
  return typeof option === "string" ? option : option.value;
}

function optionLabel(option) {
  return typeof option === "string" ? option : option.label;
}

function blankProfile(fields) {
  const profile = {};
  for (const field of fields) {
    profile[field.name] = field.name === "country" ? "Ethiopia" : "";
  }
  return profile;
}

function FieldControl({ field, value, onChange, id }) {
  const common = {
    id,
    name: field.name,
    value: value ?? "",
    onChange: (event) => onChange(field.name, event.target.value),
  };
  if (field.kind === "select") {
    return (
      <select {...common} required={field.required}>
        <option value="">{field.required ? "Choose one" : "Not specified"}</option>
        {(field.options || []).map((option) => (
          <option key={optionValue(option)} value={optionValue(option)}>
            {optionLabel(option)}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      {...common}
      type={field.kind === "number" ? "number" : "text"}
      min={field.min}
      max={field.max}
      step={field.step}
      inputMode={field.kind === "number" ? "decimal" : undefined}
      required={field.required}
    />
  );
}

function CriterionList({ title, items }) {
  if (!items?.length) return null;
  return (
    <div className="criteria">
      <h4>{title}</h4>
      <ul>
        {items.map((item) => (
          <li key={item.id}>{item.detail}</li>
        ))}
      </ul>
    </div>
  );
}

function OpportunityCard({ item }) {
  return (
    <article className={`card status-${item.status}`}>
      <header>
        <div>
          <p className="kicker">{item.source_record.id}</p>
          <h3>{item.name}</h3>
          <p className="muted">{item.provider}</p>
        </div>
        <span className={`pill pill-${item.status}`}>{item.status}</span>
      </header>
      <p>{item.summary}</p>
      <p className="deadline">Deadline {formatDate(item.deadline)}</p>
      <CriterionList title="Passed" items={item.passed} />
      <CriterionList title="Failed" items={item.failed} />
      <CriterionList title="Unknown" items={item.unknown} />
      <p className="docs">
        Documents: {item.required_documents.join(", ")}
      </p>
    </article>
  );
}

function PlanItems({ items }) {
  return (
    <div className="plan-items">
      {items.map((item) => (
        <article key={item.opportunity_id} className="plan-item">
          <h4>
            {item.name} <span>{item.source_record_id}</span>
          </h4>
          <p>Deadline {formatDate(item.deadline)}</p>
          <h5>Next actions</h5>
          <ol>
            {item.next_actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ol>
          <h5>Checklist</h5>
          <ul className="check">
            {item.checklist.map((entry) => (
              <li key={entry.item}>{entry.item}</li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [plans, setPlans] = useState([]);
  const [profile, setProfile] = useState({});
  const [sessionId, setSessionId] = useState(null);
  const [advice, setAdvice] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("");
  const [page, setPage] = useState("advise");
  const [planName, setPlanName] = useState("");
  const [missingDraft, setMissingDraft] = useState({});
  const [openPlanId, setOpenPlanId] = useState(null);
  const resultsRef = useRef(null);
  const profileRef = useRef(profile);
  const sessionRef = useRef(sessionId);
  profileRef.current = profile;
  sessionRef.current = sessionId;

  async function refreshPlans() {
    const data = await request("/api/plans");
    setPlans(data.plans || []);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([request("/api/meta"), request("/api/catalog"), request("/api/plans")])
      .then(([metaData, catalogData, planData]) => {
        if (cancelled) return;
        setMeta(metaData);
        setProfile(blankProfile(metaData.fields));
        setCatalog(catalogData.opportunities || []);
        setPlans(planData.plans || []);
      })
      .catch((err) => {
        if (!cancelled) setError({ message: err.message, errors: [], retryable: true });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function applyAdvice(data) {
    setAdvice(data);
    setSessionId(data.session_id);
    if (data.profile) setProfile(data.profile);
    if (data.plan_preview?.plan_name) setPlanName(data.plan_preview.plan_name);
    const draft = {};
    for (const field of data.missing_fields || []) {
      draft[field.field] = data.profile?.[field.field] ?? "";
    }
    setMissingDraft(draft);
    if (data.saved_plan) refreshPlans().catch(() => {});
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function send(nextProfile, sid, simulate = false) {
    setLoading(true);
    setError(null);
    setLoadingLabel(
      simulate ? "Simulating a failure…" : "Searching the catalog and checking eligibility…",
    );
    try {
      const data = await request("/api/advise", {
        method: "POST",
        body: JSON.stringify({
          profile: nextProfile,
          session_id: sid,
          simulate: simulate ? "model" : null,
        }),
      });
      applyAdvice(data);
      if (data.error) setError({ message: data.error, errors: [], retryable: true });
    } catch (err) {
      setError({
        message: err.message,
        errors: err.errors || [],
        retryable: Boolean(err.retryable),
      });
      if (err.sessionId) setSessionId(err.sessionId);
    } finally {
      setLoading(false);
    }
  }

  async function confirmPlan() {
    setLoading(true);
    setError(null);
    setLoadingLabel("Saving the confirmed plan…");
    try {
      const data = await request(`/api/sessions/${sessionId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ plan_name: planName }),
      });
      applyAdvice(data);
      if (data.error) setError({ message: data.error, errors: [], retryable: true });
    } catch (err) {
      setError({
        message: err.message,
        errors: err.errors || [],
        retryable: Boolean(err.retryable),
      });
    } finally {
      setLoading(false);
    }
  }

  function update(name, value) {
    setProfile((current) => ({ ...current, [name]: value }));
  }

  function loadExample(example) {
    setProfile({ ...blankProfile(meta.fields), ...example.profile });
    setSessionId(null);
    setAdvice(null);
    setError(null);
    setPage("advise");
  }

  function startOver() {
    setSessionId(null);
    setAdvice(null);
    setError(null);
  }

  if (!meta) {
    return (
      <main className="boot">
        <p>{error ? error.message : "Loading the adviser…"}</p>
      </main>
    );
  }

  const fields = meta.fields;
  const byName = Object.fromEntries(fields.map((field) => [field.name, field]));
  const groups = [
    ["eligible", "Eligible"],
    ["undetermined", "Undetermined"],
    ["ineligible", "Ineligible"],
  ];
  const step = advice?.saved_plan ? 4 : advice?.awaiting_confirmation ? 3 : advice ? 2 : 1;
  const openPlan = plans.find((plan) => plan.id === openPlanId) || advice?.saved_plan;

  return (
    <>
      <header className="topbar">
        <div className="wrap bar">
          <div>
            <p className="brand">E-Scholar</p>
            <p className="tag">Scholarship adviser for a fictitious Ethiopian catalog</p>
          </div>
          <nav>
            <button type="button" className={page === "advise" ? "on" : ""} onClick={() => setPage("advise")}>
              Adviser
            </button>
            <button type="button" className={page === "plans" ? "on" : ""} onClick={() => setPage("plans")}>
              Saved plans ({plans.length})
            </button>
          </nav>
        </div>
      </header>

      <main className="wrap">
        <ol className="steps" aria-label="Progress">
          {["Profile", "Check", "Confirm", "Saved"].map((label, index) => (
            <li key={label} className={step >= index + 1 ? "on" : ""}>
              {label}
            </li>
          ))}
        </ol>

        {!meta.model_configured && (
          <p className="note">
            The server has no model key yet. Add <code>LLM_API_KEY</code> to <code>backend/.env</code> before a live
            check. The catalog, validation, and the failure test still work.
          </p>
        )}

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
            {error.retryable && (
              <button type="button" onClick={() => send(profileRef.current, sessionRef.current, false)} disabled={loading}>
                Retry
              </button>
            )}
          </div>
        )}

        {page === "plans" ? (
          <section className="panel">
            <h2>Saved plans</h2>
            <p className="muted">
              Plans are stored in the shared database for this demo. They are not private. Use fictitious names only.
            </p>
            {plans.length === 0 && <p>No plan has been saved yet.</p>}
            <div className="plan-list">
              {plans.map((plan) => (
                <button
                  type="button"
                  key={plan.id}
                  className={openPlanId === plan.id ? "plan-pick on" : "plan-pick"}
                  onClick={() => setOpenPlanId(plan.id)}
                >
                  <strong>{plan.plan_name}</strong>
                  <span>
                    {plan.id} · {formatDate(plan.created_at)} · {plan.opportunities.length} scholarships
                  </span>
                </button>
              ))}
            </div>
            {openPlan && openPlanId && (
              <div className="saved">
                <h3>{openPlan.plan_name}</h3>
                <p className="muted">
                  {openPlan.student_name} · saved {formatDate(openPlan.created_at)}
                </p>
                <PlanItems items={openPlan.opportunities} />
              </div>
            )}
          </section>
        ) : (
          <div className="layout">
            <section className="panel">
              <h2>Student profile</h2>
              <p className="muted">Fictitious details only. Eligibility is calculated from catalog rules, not by the model.</p>
              <div className="examples">
                {meta.examples.map((example) => (
                  <button type="button" key={example.id} onClick={() => loadExample(example)} disabled={loading}>
                    {example.label}
                  </button>
                ))}
              </div>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  send(profile, sessionId, false);
                }}
              >
                <div className="grid">
                  {fields.map((field) => {
                    if (field.name === "english_score" && !["IELTS", "TOEFL"].includes(profile.english_test)) {
                      return null;
                    }
                    return (
                      <label key={field.name} className={field.wide ? "wide" : ""}>
                        <span>
                          {field.label}
                          {field.required ? " *" : ""}
                        </span>
                        <FieldControl field={field} value={profile[field.name]} onChange={update} id={field.name} />
                        {field.hint && <small>{field.hint}</small>}
                      </label>
                    );
                  })}
                </div>
                <div className="actions">
                  <button type="submit" className="primary" disabled={loading}>
                    {sessionId ? "Check again" : "Check scholarships"}
                  </button>
                  <button type="button" onClick={startOver} disabled={loading}>
                    New check
                  </button>
                  <button type="button" className="quiet" onClick={() => send(profile, sessionId, true)} disabled={loading}>
                    Simulate a failure
                  </button>
                </div>
              </form>
              <details className="catalog">
                <summary>Fictitious catalog ({catalog.length})</summary>
                {catalog.map((item) => (
                  <article key={item.id}>
                    <h3>
                      {item.id} · {item.name}
                    </h3>
                    <p>Deadline {formatDate(item.deadline)}</p>
                    <ul>
                      {item.criteria.map((rule) => (
                        <li key={rule.id}>{rule.label}</li>
                      ))}
                    </ul>
                  </article>
                ))}
              </details>
            </section>

            <section className="panel results" ref={resultsRef} aria-busy={loading}>
              <h2>Result</h2>
              {loading && <p className="loading">{loadingLabel}</p>}
              {!advice && !loading && (
                <div className="empty">
                  <p>Submit a profile. The adviser has to use three tools:</p>
                  <ol>
                    <li>
                      <strong>search_opportunities</strong> reads the catalog from the database.
                    </li>
                    <li>
                      <strong>check_eligibility</strong> applies the written rules in code.
                    </li>
                    <li>
                      <strong>save_application_plan</strong> runs only after you confirm.
                    </li>
                  </ol>
                </div>
              )}

              {advice && (
                <>
                  <blockquote>{advice.assistant_message}</blockquote>
                  {groups.map(([status, label]) => {
                    const items = (advice.eligibility || []).filter((item) => item.status === status);
                    if (!items.length) return null;
                    return (
                      <section key={status} className="group">
                        <h3>
                          {label} <span>{items.length}</span>
                        </h3>
                        {items.map((item) => (
                          <OpportunityCard key={item.opportunity_id} item={item} />
                        ))}
                      </section>
                    );
                  })}

                  {advice.missing_fields?.length > 0 && (
                    <form
                      className="followup"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const next = { ...profile, ...missingDraft };
                        setProfile(next);
                        send(next, sessionId, false);
                      }}
                    >
                      <h3>Missing information</h3>
                      <p>The shortlist stays provisional until these facts are filled in.</p>
                      {advice.missing_fields.map((field) => (
                        <label key={field.field}>
                          <span>{field.label}</span>
                          <FieldControl
                            field={byName[field.field] || { name: field.field, label: field.label, kind: "text" }}
                            value={missingDraft[field.field]}
                            onChange={(name, value) => setMissingDraft((current) => ({ ...current, [name]: value }))}
                            id={`missing-${field.field}`}
                          />
                          <small>{field.reasons?.[0]}</small>
                        </label>
                      ))}
                      <button type="submit" className="primary" disabled={loading}>
                        Update profile and recheck
                      </button>
                    </form>
                  )}

                  {advice.awaiting_confirmation && advice.plan_preview && (
                    <div className="followup">
                      <h3>Application plan</h3>
                      <p>Nothing is written to the database until you confirm.</p>
                      <label>
                        <span>Plan name</span>
                        <input value={planName} onChange={(event) => setPlanName(event.target.value)} />
                      </label>
                      <PlanItems items={advice.plan_preview.items} />
                      <button type="button" className="primary" onClick={confirmPlan} disabled={loading}>
                        Confirm and save plan
                      </button>
                      <p className="muted">Saved plans on this demo are shared and not private.</p>
                    </div>
                  )}

                  {advice.saved_plan && (
                    <div className="followup saved">
                      <h3>Saved</h3>
                      <p>
                        Plan <code>{advice.saved_plan.id}</code> is in the database. Open it again from Saved plans.
                      </p>
                      <PlanItems items={advice.saved_plan.opportunities} />
                      <button
                        type="button"
                        onClick={() => {
                          setOpenPlanId(advice.saved_plan.id);
                          setPage("plans");
                        }}
                      >
                        Reopen this plan
                      </button>
                    </div>
                  )}

                  <details className="log" open>
                    <summary>
                      Tool log · {advice.tool_log?.length || 0} this turn · {advice.model}
                    </summary>
                    {(advice.tool_log || []).length === 0 && <p>No tool was called on this turn.</p>}
                    <ol>
                      {(advice.tool_log || []).map((entry, index) => (
                        <li key={`${entry.tool}-${index}`} className={entry.ok ? "ok" : "bad"}>
                          <p>
                            <strong>{entry.tool}</strong> — {entry.summary}
                          </p>
                          <details>
                            <summary>Arguments and output</summary>
                            <pre>{JSON.stringify({ arguments: entry.arguments, output: entry.output }, null, 2)}</pre>
                          </details>
                        </li>
                      ))}
                    </ol>
                  </details>
                </>
              )}
            </section>
          </div>
        )}
        <footer>
          First load on a sleeping free host can take up to a minute. The catalog is fictitious. Do not enter real
          personal data.
        </footer>
      </main>
    </>
  );
}
