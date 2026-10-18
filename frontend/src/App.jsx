import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./components/auth";
import Application from "./pages/Application";
import Applications from "./pages/Applications";
import Counselling from "./pages/Counselling";
import Counsellors from "./pages/Counsellors";
import Dashboard from "./pages/Dashboard";
import Documents from "./pages/Documents";
import ForgotPassword from "./pages/ForgotPassword";
import Login from "./pages/Login";
import Notifications from "./pages/Notifications";
import { AccessDenied, NotFound } from "./pages/NotFound";
import Profile from "./pages/Profile";
import Recommendations from "./pages/Recommendations";
import Register from "./pages/Register";
import Students from "./pages/Students";
import Universities from "./pages/Universities";

const STAFF = ["counsellor", "admin"];

/**
 * Signed-in pages: signed-out visitors go to sign in (and come back afterwards); a signed-in user whose role
 * may not use the page sees an explanation instead of the page. Both happen before the page mounts or calls
 * the API, and the API enforces every rule again - this only decides what to render.
 */
function RequireAuth({ roles, children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to={"/login/?next=" + encodeURIComponent(location.pathname + location.search)} replace />;
  if (roles && !roles.includes(user.role)) return <AccessDenied />;
  return children;
}

const auth = (page, roles) => <RequireAuth roles={roles}>{page}</RequireAuth>;

export default function App() {
  const location = useLocation();
  // Keyed by URL so following a link always starts the page fresh, like a full page load.
  return (
    <Routes key={location.pathname + location.search}>
      <Route path="/" element={<Navigate to="/dashboard/" replace />} />
      <Route path="/login/" element={<Login />} />
      <Route path="/register/" element={<Register />} />
      <Route path="/forgot-password/" element={<ForgotPassword />} />
      <Route path="/dashboard/" element={auth(<Dashboard />)} />
      <Route path="/profile/" element={auth(<Profile />, ["student"])} />
      <Route path="/students/" element={auth(<Students />, STAFF)} />
      <Route path="/students/:studentId/" element={auth(<Profile />, STAFF)} />
      <Route path="/counsellors/" element={auth(<Counsellors />, STAFF)} />
      <Route path="/universities/" element={auth(<Universities />)} />
      <Route path="/applications/" element={auth(<Applications />)} />
      <Route path="/applications/:applicationId/" element={auth(<Application />)} />
      <Route path="/documents/" element={auth(<Documents />)} />
      <Route path="/counselling/" element={auth(<Counselling />)} />
      <Route path="/recommendations/" element={auth(<Recommendations />)} />
      <Route path="/notifications/" element={auth(<Notifications />)} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
