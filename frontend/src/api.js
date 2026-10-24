export async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch {
    const error = new Error(
      "The server could not be reached. Your entries are still in the form. Retry when you are ready.",
    );
    error.retryable = true;
    throw error;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.message || "The request failed. Your entries were kept.");
    error.status = response.status;
    error.errors = data.errors || [];
    error.sessionId = data.session_id || null;
    error.retryable = response.status >= 500;
    throw error;
  }
  return data;
}
