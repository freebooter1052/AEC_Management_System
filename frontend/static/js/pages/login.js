(function () {
  "use strict";
  const { api, session, $, $$ } = AEC;
  const params = new URLSearchParams(location.search);
  let portal = "student";

  if (session.token && session.user) location.replace("/dashboard/");

  const alertBox = $("#alert");
  function showAlert(msg, kind = "error") {
    alertBox.className = "alert alert-" + kind;
    alertBox.textContent = msg;
  }
  if (params.get("expired")) showAlert("Your session has ended. Please sign in again.", "info");

  $$(".portal-tabs button").forEach((btn) => btn.addEventListener("click", () => {
    portal = btn.dataset.role;
    $$(".portal-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
    $("#register-hint").hidden = portal !== "student";
    $("#staff-hint").hidden = portal === "student";
  }));

  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = $("#email").value.trim();
    const password = $("#password").value;
    if (!email || !password) { showAlert("Enter your email and password."); return; }

    const btn = $("#submit");
    btn.disabled = true; btn.textContent = "Signing in…";
    try {
      const data = await api("/auth/login/", { method: "POST", body: { email, password, role: portal } });
      session.save(data.token, data.user);
      const next = params.get("next");
      location.href = next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard/";
    } catch (err) {
      showAlert(err.message);
      btn.disabled = false; btn.textContent = "Sign in";
    }
  });
})();
