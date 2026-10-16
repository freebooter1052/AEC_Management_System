import { Link } from "react-router-dom";
import { usePageTitle } from "./Shell";

export default function AuthLayout({ title, children }) {
  usePageTitle(title);
  return (
    <div className="auth">
      <section className="auth-brand" aria-label="About AEC Admissions">
        <div className="orb orb-1" aria-hidden="true" />
        <div className="orb orb-2" aria-hidden="true" />
        <Link className="brand" to="/login/"><span className="brand-mark" aria-hidden="true">AE</span>AEC Admissions</Link>
        <div className="auth-copy">
          <span className="eyebrow">Overseas education consultants</span>
          <h1>Study abroad, guided every step of the way.</h1>
          <p className="lede">From choosing the right country and university to submitting your application,
            your personal counsellor is with you from the first conversation to the offer letter.</p>
          <ul className="services">
            <li>
              <span className="svc-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 5h16v11H8l-4 4z" /><path d="M8 9h8M8 12h5" /></svg></span>
              <div><b>One-to-one counselling</b>Sessions with your own counsellor, with notes, agreed actions and follow-ups kept in one place.</div>
            </li>
            <li>
              <span className="svc-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 9l9-5 9 5-9 5z" /><path d="M7 11.5V16c0 1.5 2.2 3 5 3s5-1.5 5-3v-4.5" /></svg></span>
              <div><b>University &amp; course search</b>Search the university and course catalogue and plan applications with your counsellor.</div>
            </li>
            <li>
              <span className="svc-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></svg></span>
              <div><b>Application &amp; document tracking</b>Upload transcripts and SOPs, see when they are verified, and follow every deadline.</div>
            </li>
          </ul>
        </div>
      </section>
      <main className="auth-main" id="main">{children}</main>
    </div>
  );
}
