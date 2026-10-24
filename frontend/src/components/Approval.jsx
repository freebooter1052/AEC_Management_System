/* The student's sign-off on a finished SOP or recommendation letter: approve it, or send it back with a note. */
import { useState } from "react";
import { useToast } from "./Toast";
import { Field } from "./ui";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { saveErrorMessage } from "../lib/form";
import { useSubmit } from "../lib/useSubmit";

/**
 * `approval` is the stored decision (or null), `current` is false when the text changed after it, `url` is the
 * decision endpoint and `onDone(result)` receives the updated record.
 */
export default function ApprovalBox({ approval, current = true, url, noun, intro, onDone }) {
  const toast = useToast();
  const [busy, run] = useSubmit();
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const approved = approval?.decision === "Approved" && current;

  const decide = (decision) => run(async () => {
    setError("");
    if (decision !== "Approved" && !note.trim()) { setError("Tell your counsellor what to change."); return; }
    try {
      onDone(await api(url, { method: "POST", body: { decision, note: note.trim() } }));
      setNote("");
      toast(decision === "Approved" ? `You approved this ${noun}` : "Sent back to your counsellor", decision === "Approved" ? "success" : "info");
    } catch (err) { toast(saveErrorMessage(err), "error"); }
  });

  if (approved) {
    return (
      <div className="alert alert-success" role="status">
        <b>You approved this {noun}</b> on {formatDate(approval.at)}. Your counsellor will finalise it.
      </div>
    );
  }
  const sentBack = approval?.decision === "Changes requested" && current;
  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <h3>Is this {noun} OK?</h3>
      <p className="small">{intro}</p>
      {sentBack && <p className="small muted">You asked for changes on {formatDate(approval.at)}: “{approval.note}”. You can still approve it once it is updated.</p>}
      <Field label="Changes needed (only if it is not OK)" error={error}>
        <textarea rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder={`What should your counsellor change in this ${noun}?`} />
      </Field>
      <div className="toolbar">
        <button type="button" className="btn btn-primary" onClick={() => decide("Approved")} disabled={busy}>{busy ? "Saving…" : `Approve this ${noun}`}</button>
        <button type="button" className="btn btn-outline" onClick={() => decide("Changes requested")} disabled={busy}>Ask for changes</button>
      </div>
    </div>
  );
}
