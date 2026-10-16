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
