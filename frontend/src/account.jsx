import { useRef, useState } from "react";
import { request } from "./api";
import { firebaseErrorMessage, firebaseSignIn, firebaseSignUp } from "./firebase";
import { ProfileFields, blankProfile } from "./fields";

function ErrorList({ error }) {
  if (!error) return null;
  return (
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
  );
}

async function firebaseToken(email, password, creating) {
  try {
    return creating ? await firebaseSignUp(email, password) : await firebaseSignIn(email, password);
  } catch (error) {
    if (creating && error?.code === "auth/email-already-in-use") {
      try {
        return await firebaseSignIn(email, password);
      } catch (signInError) {
        const wrapped = new Error(firebaseErrorMessage(signInError));
        wrapped.errors = [];
        throw wrapped;
      }
    }
    const wrapped = new Error(firebaseErrorMessage(error));
    wrapped.errors = [];
    throw wrapped;
  }
}

export function SignupPage({ fields, levels, levelForms, firebaseReady, onDone, onSwitch }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [level, setLevel] = useState("");
  const [profile, setProfile] = useState(() => blankProfile(fields));
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const levelPicker = useRef(null);

  async function submit(event) {
    event.preventDefault();
    if (!level) {
      setError({ message: "Choose high school, BSc, master's, or PhD." });
      levelPicker.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const filled = { ...profile, student_level: level };
      const data = firebaseReady
        ? await request("/api/auth/firebase", {
            method: "POST",
            body: JSON.stringify({ id_token: await firebaseToken(email, password, true), profile: filled }),
          })
        : await request("/api/signup", {
            method: "POST",
            body: JSON.stringify({ email, password, profile: filled }),
          });
      onDone(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel auth-card">
      <h2>Create a student account</h2>
      <p className="muted">
        Choose the kind of student first. High school, BSc, master's, and PhD each keep a different profile. Do not
        enter a real passport number or upload documents here.
      </p>
      <ErrorList error={error} />
      <form onSubmit={submit}>
        <div ref={levelPicker}>
          <LevelPicker
            levels={levels}
            level={level}
            onChange={(value) => {
              setLevel(value);
              setError(null);
            }}
          />
        </div>
        <div className="grid">
          <label>
            <span>Email *</span>
            <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label>
            <span>Password *</span>
            <input
              type="password"
              autoComplete="new-password"
              value={password}
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <small>At least 8 characters.</small>
          </label>
        </div>
        {level && (
          <ProfileFields
            fields={(levelForms || {})[level] || []}
            profile={profile}
            onChange={(name, value) => setProfile((current) => ({ ...current, [name]: value }))}
            idPrefix="signup-"
          />
        )}
        {!level && <p className="field-hint">Choose a student type above, then create the account.</p>}
        <div className="actions">
          <button type="submit" className="primary" disabled={loading}>
            Create account
          </button>
          <button type="button" onClick={onSwitch} disabled={loading}>
            I already have an account
          </button>
        </div>
      </form>
    </section>
  );
}

const SIGN_IN_ACCOUNTS = [
  { name: "Selam Demo", role: "Student", email: "selam.demo@example.com", password: "demo-pass-1" },
  { name: "Administrator", role: "Admin", email: "admin@escholar.local", password: "admin-pass-1" },
];

export function LoginPage({ firebaseReady, onDone, onSwitch }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = firebaseReady
        ? await request("/api/auth/firebase", {
            method: "POST",
            body: JSON.stringify({ id_token: await firebaseToken(email, password, false) }),
          })
        : await request("/api/login", {
            method: "POST",
            body: JSON.stringify({ email, password }),
          });
      onDone(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel auth-card auth-narrow">
      <h2>Sign in</h2>
      <p className="muted">
        {firebaseReady
          ? "Email and password are checked by Firebase, then this app opens your page."
          : "Tap a name to fill the sign-in fields."}
      </p>
      <ErrorList error={error} />
      {!firebaseReady && (
      <div className="account-picks">
        {SIGN_IN_ACCOUNTS.map((account) => (
          <button
            key={account.email}
            type="button"
            className={email === account.email ? "account-pick on" : "account-pick"}
            onClick={() => {
              setEmail(account.email);
              setPassword(account.password);
            }}
          >
            <strong>{account.name}</strong>
            <span>{account.role}</span>
          </button>
        ))}
      </div>
      )}
      <form onSubmit={submit}>
        <div className="grid">
          <label className="wide">
            <span>Email</span>
            <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label className="wide">
            <span>Password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
        </div>
        <div className="actions">
          <button type="submit" className="primary" disabled={loading}>
            Sign in
          </button>
          <button type="button" onClick={onSwitch} disabled={loading}>
            Create an account
          </button>
        </div>
      </form>
    </section>
  );
}

function LevelPicker({ levels, level, onChange }) {
  return (
    <div className="choice-grid" role="group" aria-label="Student type">
      {(levels || []).map((item) => (
        <button
          key={item.id}
          type="button"
          className={level === item.id ? "choice on" : "choice"}
          onClick={() => onChange(item.id)}
        >
          <strong>{item.label}</strong>
          <span>{item.detail}</span>
        </button>
      ))}
    </div>
  );
}

export function ProfilePage({ levels, levelForms, account, onDone }) {
  const [profile, setProfile] = useState(account.profile);
  const [level, setLevel] = useState(account.profile?.student_level || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!level) {
      setError({ message: "Choose high school, BSc, master's, or PhD." });
      return;
    }
    setLoading(true);
    setError(null);
    setSaved(false);
    try {
      const data = await request("/api/profile", {
        method: "PUT",
        body: JSON.stringify({
          profile: { ...profile, student_level: level },
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setSaved(true);
      onDone(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel auth-card">
      <h2>Your profile</h2>
      <p className="muted">
        Signed in as {account.user.email}. The form follows the student type you choose. The dashboard uses this
        profile for matches.
      </p>
      <ErrorList error={error} />
      {saved && <p className="note">Profile saved.</p>}
      <form onSubmit={submit}>
        <LevelPicker levels={levels} level={level} onChange={setLevel} />
        {level && (
          <ProfileFields
            fields={(levelForms || {})[level] || []}
            profile={profile}
            onChange={(name, value) => setProfile((current) => ({ ...current, [name]: value }))}
            idPrefix="profile-"
          />
        )}
        <h3>Password</h3>
        <p className="muted">Leave these blank to keep your current password.</p>
        <div className="grid">
          <label>
            <span>Current password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </label>
          <label>
            <span>New password</span>
            <input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </label>
        </div>
        <div className="actions">
          <button type="submit" className="primary" disabled={loading || !level}>
            Save profile
          </button>
        </div>
      </form>
    </section>
  );
}
