import { initializeApp } from "@firebase/app";
import { createUserWithEmailAndPassword, getAuth, signInWithEmailAndPassword, signOut } from "@firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || undefined,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || undefined,
};

export const firebaseConfigured = Boolean(config.apiKey && config.authDomain && config.projectId && config.appId);

let auth = null;

function client() {
  if (!firebaseConfigured) return null;
  if (!auth) auth = getAuth(initializeApp(config));
  return auth;
}

export async function firebaseSignUp(email, password) {
  const credential = await createUserWithEmailAndPassword(client(), email, password);
  return credential.user.getIdToken();
}

export async function firebaseSignIn(email, password) {
  const credential = await signInWithEmailAndPassword(client(), email, password);
  return credential.user.getIdToken();
}

export async function firebaseSignOut() {
  if (!auth) return;
  await signOut(auth);
}

export function firebaseErrorMessage(error) {
  const code = error?.code || "";
  if (
    code === "auth/invalid-credential" ||
    code === "auth/wrong-password" ||
    code === "auth/user-not-found" ||
    code === "auth/invalid-email"
  ) {
    return "Email or password is not correct.";
  }
  if (code === "auth/email-already-in-use") return "An account with that email already exists.";
  if (code === "auth/weak-password" || code === "auth/password-does-not-meet-requirements") {
    return "Password must be at least 8 characters.";
  }
  if (code === "auth/too-many-requests") return "Too many attempts. Wait a moment and try again.";
  return "Sign-in could not be completed. Check the email and password.";
}
