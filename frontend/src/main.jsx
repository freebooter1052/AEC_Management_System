import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./components/auth";
import { ToastProvider } from "./components/Toast";
// Fonts are bundled with the app (SIL Open Font License), so pages look the same offline and load no third-party CSS.
import "@fontsource-variable/inter";
import "@fontsource-variable/space-grotesk";
import "./styles/app.css";

// Back/forward may restore a signed-in page from the browser's page cache after logout; reload so it re-checks the session.
window.addEventListener("pageshow", (e) => {
  if (e.persisted && !localStorage.getItem("aec.token") && !/^\/(login|register|forgot-password)\//.test(location.pathname)) location.reload();
});

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
