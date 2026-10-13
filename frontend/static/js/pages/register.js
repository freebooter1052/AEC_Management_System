(function () {
  "use strict";
  const { api, session, $, showFieldErrors } = AEC;

  if (session.token && session.user) location.replace("/dashboard/");

  const form = $("#register-form");
  const alertBox = $("#alert");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    alertBox.className = "alert hidden";
    const body = Object.fromEntries(new FormData(form).entries());
    for (const k of Object.keys(body)) body[k] = body[k].trim();

    if (body.password !== body.password2) {
      showFieldErrors(form, { password2: ["Passwords do not match."] });
      return;
    }
    delete body.password2;

    const btn = $("#submit");
    btn.disabled = true; btn.textContent = "Creating account…";
    try {
      const data = await api("/auth/register/", { method: "POST", body });
      session.save(data.token, data.user);
      location.href = "/profile/?welcome=1";
    } catch (err) {
      if (err.status === 400) showFieldErrors(form, err.data);
      alertBox.className = "alert alert-error";
      alertBox.textContent = err.status === 400 ? "Please correct the highlighted fields." : err.message;
      btn.disabled = false; btn.textContent = "Create account";
    }
  });
})();
