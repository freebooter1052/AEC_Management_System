/* Shared document widgets (rows, upload drawer, review drawer) for the Documents and Application pages. */
import { useState } from "react";
import Drawer from "./Drawer";
import { useToast } from "./Toast";
import { DocStatusBadge, Field } from "./ui";
import { api, download } from "../lib/api";
import { fieldErrors } from "../lib/form";
import { formatDate, formatDateTime } from "../lib/format";

// Mirrors apps/documents/services.py - the API enforces these; the UI only offers valid choices.
export const UPLOADABLE = ["Required", "Uploaded", "Rejected", "Expired"];
export const REVIEW = { Uploaded: ["Under Review", "Verified", "Rejected"], "Under Review": ["Verified", "Rejected"], Verified: ["Expired"] };
const NEEDS_REMARKS = ["Rejected", "Expired"];
const EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"];
const MAX_BYTES = 5 * 1024 * 1024;

export const isStaff = (user) => user?.role === "counsellor" || user?.role === "admin";
const label = (d) => d.title || d.document_type;

function FileCell({ d }) {
  const toast = useToast();
  if (d.has_file) {
    return (
      <>
        <button className="btn btn-outline btn-sm" title="Download"
          onClick={() => download(`/documents/${encodeURIComponent(d.id)}/file/`, d.filename).catch((e) => toast(e.message, "error"))}>⭳ {d.filename}</button>
        <div className="small muted">Uploaded {formatDate(d.uploaded_at)}</div>
      </>
    );
  }
  if (d.reference_url) {
    return <><a href={d.reference_url} target="_blank" rel="noopener noreferrer">{d.filename || "Open link"} ↗</a><div className="small muted">Linked {formatDate(d.uploaded_at)}</div></>;
  }
  if (d.filename) return <><span>{d.filename}</span><div className="small muted">Recorded {formatDate(d.uploaded_at)} · no stored copy</div></>;
  return <span className="small muted">Not uploaded yet</span>;
}

/** One checklist row. `showStudent` adds the student's name (staff queues). */
export function DocRow({ d, user, showStudent = false, actions }) {
  const sub = [showStudent ? d.student_name : "", d.title ? d.document_type : "", d.application_label || (showStudent ? "General document" : "")].filter(Boolean).join(" · ");
  const reviewed = d.verified_by_name && ["Verified", "Rejected"].includes(d.status);
  return (
    <div className="doc-row">
      <div><div className="name">{label(d)}</div>{sub && <div className="small muted">{sub}</div>}</div>
      <div><DocStatusBadge status={d.status} />{reviewed && <div className="small muted">{d.status} by {d.verified_by_name} · {formatDate(d.verified_at)}</div>}</div>
      <div><FileCell d={d} /></div>
      <div className="actions">
        {UPLOADABLE.includes(d.status) && (
          <button className={`btn ${d.status === "Uploaded" ? "btn-outline" : "btn-primary"} btn-sm`} onClick={() => actions.upload(d)}>{d.status === "Required" ? "Upload" : "Replace"}</button>
        )}
        {isStaff(user) && REVIEW[d.status] && <button className="btn btn-primary btn-sm" onClick={() => actions.review(d)}>Review</button>}
      </div>
      {d.remarks && NEEDS_REMARKS.includes(d.status) && <div className="remark"><b>{d.status}:</b> {d.remarks}</div>}
    </div>
  );
}

function UploadDrawer({ doc, onClose, onDone }) {
  const toast = useToast();
  const [mode, setMode] = useState("file");
  const [file, setFile] = useState(null);
  const [chosen, setChosen] = useState({ text: "No file chosen.", bad: false });
  const [drag, setDrag] = useState(false);
  const [link, setLink] = useState({ reference_url: "", filename: "" });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);

  const choose = (f) => {
    const bad = !!f && (!EXTENSIONS.some((e) => f.name.toLowerCase().endsWith(e)) || f.size > MAX_BYTES);
    setChosen({ text: f ? `${f.name} · ${(f.size / 1024).toFixed(0)} KB${bad ? " — not accepted (type or size)" : ""}` : "No file chosen.", bad });
    setFile(f && !bad ? f : null);
  };

  async function save() {
    setBusy(true);
    try {
      let updated;
      if (mode === "file") {
        if (!file) { toast("Choose a PDF, image or Word file up to 5 MB.", "error"); return; }
        const data = new FormData();
        data.append("file", file);
        updated = await api(`/documents/${encodeURIComponent(doc.id)}/upload/`, { method: "POST", form: data });
      } else {
        updated = await api(`/documents/${encodeURIComponent(doc.id)}/upload/`, {
          method: "POST", body: { reference_url: link.reference_url.trim(), filename: link.filename.trim() } });
      }
      toast(`${label(doc)} uploaded — your counsellor will review it.`);
      onDone(updated);
    } catch (err) {
      if (err.status === 400) setErrors(fieldErrors(err.data));
      toast(err.message, "error");
    } finally { setBusy(false); }
  }

  return (
    <Drawer title={`${doc.status === "Required" ? "Upload" : "Replace"} ${label(doc)}`} onClose={onClose} footer={<>
      <button className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" onClick={save} disabled={busy}>Upload</button>
    </>}>
      {doc.remarks && NEEDS_REMARKS.includes(doc.status) && <div className="alert alert-error"><b>{doc.status}:</b> {doc.remarks}</div>}
      <p className="muted small">{doc.application_label || "General document"} · {doc.student_name}</p>
      <div className="section-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "file"} onClick={() => setMode("file")}>Upload a file</button>
        <button type="button" role="tab" aria-selected={mode === "link"} onClick={() => setMode("link")}>Link to a file</button>
      </div>
      <form noValidate onSubmit={(e) => { e.preventDefault(); save(); }}>
        <div hidden={mode !== "file"}>
          <label className={"dropzone" + (drag ? " drag" : "")}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files[0]); }}>
            <input type="file" accept={EXTENSIONS.join(",")} onChange={(e) => choose(e.target.files[0])} />
            <b>Choose a file</b> or drop it here<div className="small">PDF, image or Word · up to 5 MB</div>
          </label>
          <div className="field" style={{ marginTop: ".6rem" }}>
            <span className="hint" style={chosen.bad ? { color: "var(--err)" } : undefined}>{chosen.text}</span>
            {errors.file && <div className="error">{errors.file}</div>}
          </div>
        </div>
        <div hidden={mode !== "link"}>
          <Field label="Link (https://…)" error={errors.reference_url}>
            <input type="url" placeholder="https://drive.example.org/…" value={link.reference_url} onChange={(e) => setLink({ ...link, reference_url: e.target.value })} />
          </Field>
          <Field label="File name (optional)" error={errors.filename}>
            <input maxLength={120} value={link.filename} onChange={(e) => setLink({ ...link, filename: e.target.value })} />
          </Field>
        </div>
      </form>
    </Drawer>
  );
}

function ReviewDrawer({ doc, onClose, onDone }) {
  const toast = useToast();
  const choices = REVIEW[doc.status] || [];
  const [status, setStatus] = useState(choices[0] || "");
  const [remarks, setRemarks] = useState("");
  const [errors, setErrors] = useState({});
  const history = (doc.history || []).slice().reverse();

  async function save() {
    if (NEEDS_REMARKS.includes(status) && !remarks.trim()) {
      setErrors({ remarks: `Tell the student why the document is ${status.toLowerCase()}.` });
      return;
    }
    try {
      const updated = await api(`/documents/${encodeURIComponent(doc.id)}/verify/`, { method: "POST", body: { status, remarks: remarks.trim(), rev: doc.rev } });
      toast(`${label(doc)} marked ${status}.`);
      onDone(updated);
    } catch (err) {
      if (err.status === 400) setErrors(fieldErrors(err.data));
      toast(err.status === 409 ? "This document changed meanwhile. Reload and try again." : err.message, "error");
    }
  }

  return (
    <Drawer title={`Review ${label(doc)}`} onClose={onClose} footer={<>
      <button className="btn btn-outline" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" onClick={save}>Save decision</button>
    </>}>
      <dl className="facts">
        <dt>Student</dt><dd>{doc.student_name}</dd>
        <dt>For</dt><dd>{doc.application_label || "General document"}</dd>
        <dt>Status</dt><dd><DocStatusBadge status={doc.status} /></dd>
        <dt>File</dt><dd><FileCell d={doc} /></dd>
      </dl>
      <form noValidate style={{ marginTop: "1.2rem" }} onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Decision" error={errors.status}>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>{choices.map((c) => <option key={c}>{c}</option>)}</select>
        </Field>
        <Field label="Remarks for the student" error={errors.remarks}>
          <textarea maxLength={500} placeholder="Required when rejecting or expiring a document." value={remarks} onChange={(e) => setRemarks(e.target.value)} />
        </Field>
      </form>
      {history.length > 0 && <>
        <div className="label-sm">History</div>
        <ul className="timeline" style={{ marginTop: ".6rem" }}>
          {history.map((h, i) => (
            <li key={i}>
              <div className="when">{formatDateTime(h.at)}</div>
              <div className="what">{h.status}</div>
              <div className="note">{h.by_name || ""}{h.remarks ? ` — ${h.remarks}` : ""}</div>
            </li>
          ))}
        </ul>
      </>}
    </Drawer>
  );
}

/** Upload/review drawer state for a page: pass `actions` to each DocRow and render `drawers`. */
export function useDocActions(onChange) {
  const [open, setOpen] = useState(null);
  const close = () => setOpen(null);
  const done = (updated) => { setOpen(null); onChange?.(updated); };
  const actions = { upload: (d) => setOpen({ kind: "upload", d }), review: (d) => setOpen({ kind: "review", d }) };
  const drawers = open?.kind === "upload" ? <UploadDrawer doc={open.d} onClose={close} onDone={done} />
    : open?.kind === "review" ? <ReviewDrawer doc={open.d} onClose={close} onDone={done} />
    : null;
  return { actions, drawers };
}
