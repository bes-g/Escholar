import { useEffect, useRef, useState } from "react";
import { LoginPage, ProfilePage, SignupPage } from "./account";
import { request } from "./api";
import { ChunkingPage } from "./chunking";
import { DashboardPage } from "./dashboard";
import { FieldControl, blankProfile } from "./fields";
import { firebaseConfigured, firebaseSignOut } from "./firebase";
import { SourcesPage } from "./sources";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDate(iso) {
  if (!iso) return "";
  const [date] = String(iso).split("T");
  const [year, month, day] = date.split("-");
  if (!year || !month || !day) return iso;
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
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
      <p className="docs">Documents: {item.required_documents.join(", ")}</p>
      {safeHttpUrl(item.source_url) && (
        <p className="docs">
          <a href={safeHttpUrl(item.source_url)} target="_blank" rel="noreferrer">
            Source page
          </a>
        </p>
      )}
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
  const [page, setPage] = useState("login");
  const [account, setAccount] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const profileTouched = useRef(false);
  const savedProfile = useRef(null);
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
        if (!profileTouched.current) setProfile(savedProfile.current || blankProfile(metaData.fields));
        setCatalog(catalogData.opportunities || []);
        setPlans(planData.plans || []);
      })
      .catch((err) => {
        if (!cancelled) setError({ message: err.message, errors: [], retryable: true });
      });
    request("/api/me")
      .then((data) => {
        if (cancelled) return;
        setAccount(data);
        savedProfile.current = data.profile;
        if (!profileTouched.current) setProfile(data.profile);
        setPage(data.user?.role === "admin" ? "sources" : "dashboard");
      })
      .catch(() => {
        if (!cancelled) {
          setAccount(null);
          setPage("login");
        }
      })
      .finally(() => {
        if (!cancelled) setAuthReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function homeFor(data) {
    return data?.user?.role === "admin" ? "sources" : "dashboard";
  }

  function acceptAccount(data) {
    profileTouched.current = false;
    setAccount(data);
    if (data.profile) setProfile(data.profile);
    setPage(homeFor(data));
    refreshPlans().catch(() => {});
  }

  async function signOut() {
    await firebaseSignOut().catch(() => {});
    await request("/api/logout", { method: "POST" }).catch(() => {});
    setAccount(null);
    setMenuOpen(false);
    setPage("login");
    refreshPlans().catch(() => {});
  }

  function go(next) {
    setPage(next);
    setMenuOpen(false);
  }

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
    profileTouched.current = true;
    setProfile((current) => ({ ...current, [name]: value }));
  }

  function loadExample(example) {
    profileTouched.current = true;
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

  if (!meta || !authReady) {
    return (
      <main className="boot">
        <p>{error ? error.message : "Loading E-Scholar…"}</p>
      </main>
    );
  }

  const fields = meta.fields;
  const firebaseReady = Boolean(meta.firebase) && firebaseConfigured;
  const byName = Object.fromEntries(fields.map((field) => [field.name, field]));
  const groups = [
    ["eligible", "Eligible"],
    ["undetermined", "Undetermined"],
    ["ineligible", "Ineligible"],
  ];
  const step = advice?.saved_plan ? 4 : advice?.awaiting_confirmation ? 3 : advice ? 2 : 1;
  const openPlan = plans.find((plan) => plan.id === openPlanId) || advice?.saved_plan;
  const isAdmin = account?.user?.role === "admin";
  const titles = {
    dashboard: "Dashboard",
    advise: "Adviser",
    plans: "Saved plans",
    profile: "Profile",
    sources: "Sources",
    chunking: "Chunking",
    login: "Sign in",
    signup: "Create account",
  };
  const activePage = !account
    ? page === "signup"
      ? "signup"
      : "login"
    : (isAdmin ? ["sources", "chunking"] : ["dashboard", "advise", "plans", "profile"]).includes(page)
      ? page
      : homeFor(account);
  const initials = (account?.profile?.student_name || account?.user?.email || "G")
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const pageBody = (
    <>

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

        {activePage === "dashboard" ? (
          <DashboardPage onOpenProfile={() => go("profile")} />
        ) : activePage === "chunking" ? (
          <ChunkingPage />
        ) : activePage === "profile" ? (
          <ProfilePage
            levels={meta.levels}
            levelForms={meta.level_forms}
            account={account}
            onDone={(data) => {
              savedProfile.current = data.profile;
              setAccount(data);
            }}
          />
        ) : activePage === "sources" ? (
          <SourcesPage />
        ) : activePage === "plans" ? (
          <section className="panel">
            <h2>Saved plans</h2>
            <p className="muted">
              {account
                ? "These plans belong to your account. Use fictitious names unless you are comfortable storing this profile."
                : "Plans saved without an account are visible to anyone using this demo. Sign in to keep plans on your account."}
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
              <p className="muted">
                Eligibility is calculated from catalog rules, not by the model.
                {account ? " Load your saved profile, or type a one-off check without changing it." : " Sign in to keep this profile."}
              </p>
              <div className="examples">
                {account && (
                  <button
                    type="button"
                    onClick={() => {
                      profileTouched.current = false;
                      setProfile(account.profile);
                      setSessionId(null);
                      setAdvice(null);
                      setError(null);
                    }}
                    disabled={loading}
                  >
                    Load saved profile
                  </button>
                )}
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
    </>
  );

  if (!account) {
    return (
      <div className="auth-shell">
        <div className="auth-intro">
          <p className="brand">E-Scholar</p>
          <h2>{titles[activePage]}</h2>
          <p>Sign in to open your page. Students and administrators see different workspaces.</p>
        </div>
        {activePage === "signup" ? (
          <SignupPage
            fields={fields}
            levels={meta.levels}
            levelForms={meta.level_forms}
            firebaseReady={firebaseReady}
            onDone={acceptAccount}
            onSwitch={() => setPage("login")}
          />
        ) : (
          <LoginPage firebaseReady={firebaseReady} onDone={acceptAccount} onSwitch={() => setPage("signup")} />
        )}
        <p className="auth-foot">Scholarship matching for a fictitious catalog. Do not enter real personal documents.</p>
      </div>
    );
  }

  return (
    <div className="shell">
      <div className={menuOpen ? "backdrop open" : "backdrop"} onClick={() => setMenuOpen(false)} />
      <aside className={menuOpen ? "sidebar open" : "sidebar"}>
        <button type="button" className="sidebar-brand" onClick={() => go(homeFor(account))}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="2" y="4" width="20" height="16" rx="2" fill="#0ab39c" opacity="0.25" />
            <path d="M6 16V10l4 3 4-3v6M6 8h12" stroke="#fff" strokeWidth="1.75" strokeLinecap="round" />
          </svg>
          <span className="brand">E-Scholar</span>
        </button>
        <nav>
          <p className="menu-label">{isAdmin ? "Admin" : "Student"}</p>
          {isAdmin ? (
            <>
              <button type="button" className={activePage === "sources" ? "on" : ""} onClick={() => go("sources")}>
                Sources
              </button>
              <button type="button" className={activePage === "chunking" ? "on" : ""} onClick={() => go("chunking")}>
                Chunking
              </button>
            </>
          ) : (
            <>
              <button type="button" className={activePage === "dashboard" ? "on" : ""} onClick={() => go("dashboard")}>
                Dashboard
              </button>
              <button type="button" className={activePage === "advise" ? "on" : ""} onClick={() => go("advise")}>
                Adviser
              </button>
              <button type="button" className={activePage === "plans" ? "on" : ""} onClick={() => go("plans")}>
                Saved plans
              </button>
              <button type="button" className={activePage === "profile" ? "on" : ""} onClick={() => go("profile")}>
                Profile
              </button>
            </>
          )}
        </nav>
        <div className="sidebar-user">
          <p>{isAdmin ? "Administrator" : account.profile?.student_name || "Student"}</p>
          <small>{account.user.email}</small>
          <span className="role-badge">{isAdmin ? "Admin" : "Student"}</span>
        </div>
      </aside>
      <div className="shell-main">
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button type="button" className="menu-toggle" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              ☰
            </button>
            <div>
              <p className="eyebrow">{isAdmin ? "Administrator" : "Student"}</p>
              <h1>{titles[activePage] || "Adviser"}</h1>
            </div>
          </div>
          <button type="button" className="avatar-btn" onClick={signOut}>
            <span className="avatar">{initials}</span>
            <span>Sign out</span>
          </button>
        </header>
        <main className="content">
          <p className="crumbs">
            <strong>{titles[activePage] || "Adviser"}</strong> / {isAdmin ? "Admin" : "Student"}
          </p>
          {activePage === "advise" && (
            <ol className="steps" aria-label="Progress">
              {["Profile", "Check", "Confirm", "Saved"].map((label, index) => (
                <li key={label} className={step >= index + 1 ? "on" : ""}>
                  {label}
                </li>
              ))}
            </ol>
          )}
          {pageBody}
        </main>
        <footer className="app-footer">
          <span>{new Date().getFullYear()} © E-Scholar</span>
          <span>Fictitious catalog. Do not enter real personal data.</span>
        </footer>
      </div>
    </div>
  );
}
