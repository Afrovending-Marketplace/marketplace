// Reports browser errors to the backend error log. Never sends form values, query strings or payment details.
const URL_ = `${process.env.REACT_APP_BACKEND_URL}/api/v1/ops/client-errors`;
const seen = new Set();
let sent = 0;

export const reportError = (kind, message, stack = "") => {
  const key = `${kind}|${message}`;
  if (seen.has(key) || sent >= 10) return;
  seen.add(key);
  sent += 1;
  try {
    fetch(URL_, {
      method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
      body: JSON.stringify({ kind: String(kind).slice(0, 80), message: String(message || "").slice(0, 1000), stack: String(stack || "").slice(0, 4000), page: window.location.pathname }),
    }).catch(() => {});
  } catch { /* reporting must never break the page */ }
};

export const installErrorReporter = () => {
  window.addEventListener("error", (e) => reportError(e.error?.name || "Error", e.message, e.error?.stack));
  window.addEventListener("unhandledrejection", (e) => {
    const r = e.reason;
    if (r?.isAxiosError) return;
    reportError(r?.name || "UnhandledRejection", r?.message || String(r), r?.stack);
  });
};
