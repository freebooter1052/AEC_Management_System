/* One SOP, referee brief or referee starting draft: guided interview, editor with AI help, versions and comments. */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import AppShell, { ROLE_LABEL } from "../components/Shell";
import ApprovalBox from "../components/Approval";
import { ConfirmDialog } from "../components/Dialog";
import { useAuth } from "../components/auth";
import { useToast } from "../components/Toast";
import { ErrorAlert, Field, Loading, recordError } from "../components/ui";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { saveErrorMessage } from "../lib/form";
import { timeAgo } from "../lib/notifications";
import { useLoad } from "../lib/useLoad";
import { useSubmit } from "../lib/useSubmit";
import { useUnsavedChanges } from "../lib/useUnsavedChanges";
import {
  aiBlockReason, answeredCount, draftFilename, kindLabel, limitState, placeholderCount, REVISE_PRESETS, sopStep, statementStatus,
  versionSource, wordCount,
} from "../lib/writing";

const STEPS = ["Interview", "Draft", "Review & share", "Final"];

function Steps({ step }) {
  return (
    <ol className="stepper">
      {STEPS.map((s, i) => <li key={s} className={i + 1 < step ? "done" : i + 1 === step ? (step === 4 ? "done" : "current") : ""} aria-current={i + 1 === step ? "step" : undefined}>{s}</li>)}
    </ol>
  );
}

function WordMeter({ text, limit }) {
  const info = limitState(wordCount(text), limit);
  const gaps = placeholderCount(text);
  return (
    <div className="writing-meter" aria-live="polite">
      <div className={`writing-meter-bar is-${info.state}`}><span style={{ width: `${Math.min(100, info.pct)}%` }} /></div>
      <div className="small"><span className={info.state === "over" ? "writing-over" : "muted"}>{info.text}</span>
        {gaps > 0 && <span className="writing-gaps"> · {gaps} [ADD: …] gap{gaps === 1 ? "" : "s"} to fill in</span>}</div>
    </div>
  );
}

function copyText(text, toast) {
  navigator.clipboard?.writeText(text).then(() => toast("Copied to the clipboard"), () => toast("Could not copy. Select the text and copy it instead.", "warning"));
}

function downloadText(text, title) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: draftFilename(title) });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function Interview({ st, questions, answers, setAnswers, editable, onSave, busy, dirty }) {
  const done = answeredCount(questions, answers);
  return (
    <details className="card writing-interview" open={!wordCount(st.content)}>
      <summary>
        <h3 style={{ display: "inline" }}>1. Interview answers</h3>
        <span className="small muted"> · {done} of {questions.length} answered{dirty ? " · unsaved" : ""}</span>
      </summary>
      <p className="small muted">Fill these in with the student, in their own words. The assistant writes only from these answers and the student's profile, and leaves [ADD: …] gaps for anything missing.</p>
      {questions.map((q) => (
        <Field key={q.key} label={<>{q.question}{q.required && <span className="writing-req"> (needed for an AI draft)</span>}</>} hint={q.hint}>
          <textarea rows={3} maxLength={2000} readOnly={!editable} value={answers[q.key] || ""} onChange={(e) => setAnswers({ ...answers, [q.key]: e.target.value })} />
        </Field>
      ))}
      {editable && <div className="toolbar"><button type="button" className="btn btn-outline" onClick={onSave} disabled={busy || !dirty}>{busy ? "Saving…" : "Save answers"}</button></div>}
    </details>
  );
}

function Feedback({ fb, current }) {
  if (!fb) return <p className="small muted" style={{ margin: 0 }}>Ask for a review to see strengths, what to improve and what an admissions officer would miss. The text is not changed.</p>;
  const list = (title, items, cls) => items?.length ? <><h4 className={cls}>{title}</h4><ul className="writing-fb">{items.map((x, i) => <li key={i}>{x}</li>)}</ul></> : null;
  return (
    <div>
      {fb.version && current && fb.version !== current && <p className="small muted">This review is of version {fb.version}; the text has changed since.</p>}
      {fb.summary && <p style={{ marginTop: 0 }}>{fb.summary}</p>}
      {list("Strengths", fb.strengths, "writing-fb-ok")}
      {list("To improve", fb.improvements, "writing-fb-warn")}
      {list("Missing facts", fb.missing, "writing-fb-info")}
      <p className="small muted" style={{ margin: 0 }}>Reviewed {timeAgo(fb.at)}</p>
    </div>
  );
}

function Comments({ st, user, onAdd, busy }) {
  const [text, setText] = useState("");
  const canComment = user.role !== "admin" && (user.role !== "student" || ["Shared", "Final"].includes(st.status));
  const send = async () => { if (text.trim() && await onAdd(text.trim())) setText(""); };
  return (
    <div className="card">
      <h3>Comments</h3>
      {st.comments.length === 0 && <p className="small muted">{user.role === "student" ? "Tell your counsellor what to change — a fact to add, a sentence that doesn't sound like you." : st.kind === "sop" ? "The student can comment once you share the draft." : "Notes for yourself."}</p>}
      <ul className="writing-comments">
        {st.comments.map((c) => (
          <li key={c.id} className={c.by_role === "student" ? "is-student" : ""}>
            <div className="small"><b>{c.by_name || ROLE_LABEL[c.by_role]}</b> <span className="muted">{timeAgo(c.at)}</span></div>
            <p>{c.text}</p>
          </li>
        ))}
      </ul>
      {canComment && (
        <form noValidate onSubmit={(e) => { e.preventDefault(); send(); }}>
          <Field label="Add a comment"><textarea rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} /></Field>
          <button type="submit" className="btn btn-outline btn-sm" disabled={busy || !text.trim()}>{busy ? "Sending…" : "Send"}</button>
        </form>
      )}
    </div>
  );
}

function Versions({ st, editable, onRestore, busy }) {
  const versions = (st.versions || []).slice().reverse();
  if (!versions.length) return null;
  const current = versions[0].n;
  return (
    <details className="card">
      <summary><h3 style={{ display: "inline" }}>Versions</h3> <span className="small muted">· {versions.length} kept</span></summary>
      <ul className="timeline">
        {versions.map((v) => (
          <li key={v.n}>
            <div className="when">{formatDateTime(v.at)}</div>
            <div className="what">Version {v.n} · {versionSource(v.source)}{v.n === current ? " (current)" : ""}</div>
            <div className="note">{v.note ? `${v.note} · ` : ""}{v.word_count} words
              {editable && v.n !== current && <> · <button type="button" className="link-btn" onClick={() => onRestore(v.n)} disabled={busy}>Restore</button></>}</div>
          </li>
        ))}
      </ul>
    </details>
  );
}

function Editor({ initial, user }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [st, setSt] = useState(initial.statement);
  const ws = initial.workspace;
  const [text, setText] = useState(st.content || "");
  const [answers, setAnswers] = useState(st.answers || {});
  const [instruction, setInstruction] = useState("");
  const [confirm, setConfirm] = useState(null); // {kind: "redraft" | "delete" | "final"}
  const [busy, run] = useSubmit();
  const [aiBusy, setAiBusy] = useState("");
  const editable = ws.can_edit && st.status !== "Final";
  const isSop = st.kind === "sop";
  const questions = ws.questions;
  const textDirty = editable && text !== (st.content || "");
  const answersDirty = editable && JSON.stringify(answers) !== JSON.stringify(st.answers || {});
  const guard = useUnsavedChanges(textDirty || answersDirty);
  const blocked = aiBlockReason({ consent: ws.consent, aiAvailable: ws.ai_available, canEdit: ws.can_edit });
  const status = statementStatus(st.status);
  const path = `/writing/statements/${encodeURIComponent(st.id)}/`;

  const apply = (updated) => { setSt(updated); setText(updated.content || ""); if (updated.answers) setAnswers(updated.answers); };
  const fail = (err) => {
    if (err.status === 409) toast("This draft changed in another window. Reload the page to get the latest version.", "warning");
    else toast(saveErrorMessage(err), "error");
  };

  /* Save unsaved edits first, so an AI action always works on what is on screen. */
  const saveEdits = async () => {
    if (!textDirty && !answersDirty) return st;
    const body = { rev: st.rev };
    if (textDirty) body.content = text;
    if (answersDirty) body.answers = answers;
    const updated = await api(path, { method: "PATCH", body });
    apply(updated);
    return updated;
  };

  const save = (message = "Saved") => run(async () => {
    try { await saveEdits(); toast(message); return true; } catch (err) { fail(err); return false; }
  });

  const ai = (action, body, label, done) => run(async () => {
    setAiBusy(label);
    try {
      await saveEdits();
      apply(await api(`${path}${action}/`, { method: "POST", body }));
      toast(done);
    } catch (err) { fail(err); } finally { setAiBusy(""); }
  });

  const draft = () => ai("generate", {}, "Writing the first draft…", "First draft ready. Read it through and fill in any [ADD: …] gaps.");
  const improve = (how) => ai("revise", { instruction: how }, `Working on it: ${how.toLowerCase()}…`, "Draft improved. The previous version is kept under Versions.");
  const review = () => ai("review", {}, "Reviewing the draft…", "Feedback ready");
  const prepareAgain = () => run(async () => {
    setAiBusy("Preparing again…");
    try {
      await saveEdits();
      apply(await api(`/writing/references/${encodeURIComponent(st.reference_id)}/prepare/`, { method: "POST", body: { kind: st.kind } }));
      toast("New version ready");
    } catch (err) { fail(err); } finally { setAiBusy(""); }
  });

  const setStatus = (to) => run(async () => {
    try {
      await saveEdits();
      apply(await api(`${path}status/`, { method: "POST", body: { status: to } }));
      setConfirm(null);
      toast(to === "Shared" ? "Shared — the student has been notified" : to === "Final" ? "Marked as final" : "Back to draft");
    } catch (err) { fail(err); }
  });

  const restore = (n) => run(async () => {
    try { apply(await api(`${path}restore/`, { method: "POST", body: { version: n } })); toast(`Version ${n} restored as the current text`); } catch (err) { fail(err); }
  });

  const comment = async (body) => {
    let ok = false;
    await run(async () => {
      try { apply(await api(`${path}comments/`, { method: "POST", body: { text: body } })); toast("Comment sent"); ok = true; } catch (err) { fail(err); }
    });
    return ok;
  };

  const remove = () => run(async () => {
    try { await api(path, { method: "DELETE" }); toast("Deleted"); navigate(back); } catch (err) { fail(err); }
  });

  useEffect(() => {
    const onKey = (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "s" && editable) { e.preventDefault(); save(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const step = isSop ? sopStep({ ...st, content: text, answers }, questions) : null;
  const busyAll = busy || !!aiBusy;
  const back = user.role === "student" ? "/writing/" : `/writing/?student_id=${encodeURIComponent(st.student_id)}${isSop ? "" : "&tab=lor"}`;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="page-eyebrow">{kindLabel(st.kind)} · {st.student_name}</p>
          <h1>{st.title}</h1>
          <p className="muted">{status.help}</p>
        </div>
        <div className="toolbar">
          {st.ai_assisted && <span className="badge badge-brand" title="Parts of this text were written with the AI assistant">AI-assisted</span>}
          <span className={status.className}>{status.label}</span>
          {ws.can_edit && isSop && st.status === "Draft" && <button type="button" className="btn btn-primary" onClick={() => setStatus("Shared")} disabled={busyAll || !wordCount(text)}>Share with student</button>}
          {ws.can_edit && st.status !== "Final" && (isSop ? st.status === "Shared" : true) && <button type="button" className="btn btn-outline" onClick={() => setConfirm({ kind: "final" })} disabled={busyAll || !wordCount(text) || (isSop && !st.approved)} title={isSop && !st.approved ? "The student has to approve this version first" : undefined}>Mark as final</button>}
          {ws.can_edit && st.status !== "Draft" && <button type="button" className="btn btn-outline" onClick={() => setStatus("Draft")} disabled={busyAll}>Back to draft</button>}
        </div>
      </div>

      {isSop && <div className="card" style={{ marginBottom: "1rem" }}><Steps step={step} /></div>}
      {isSop && st.status === "Shared" && user.role === "student" && (
        <ApprovalBox approval={st.student_approval} current={st.approved || st.student_approval?.decision === "Changes requested"} noun="SOP"
          url={`${path}decision/`} onDone={apply}
          intro="Read the draft below. If it is correct and sounds like you, approve it. If not, say what to change and your counsellor will update it." />
      )}
      {isSop && ws.can_edit && st.status === "Shared" && (
        st.approved ? <div className="alert alert-success" role="status">The student approved this version on {formatDateTime(st.student_approval.at)}. You can mark it as final.</div>
        : st.student_approval?.decision === "Changes requested" ? <div className="alert alert-warn" role="status">The student asked for changes: “{st.student_approval.note}”. Update the text and the student can approve again.</div>
        : <div className="alert alert-info" role="status">Waiting for the student to approve this draft.</div>
      )}
      {ws.can_edit && blocked && <div className="alert alert-info">{blocked}{!ws.consent.granted && ws.ai_available && <> <Link to={back}>Ask the student from the SOP &amp; LOR page.</Link></>}</div>}
      {st.ai_assisted && user.role === "student" && <div className="alert alert-info">Parts of this draft were written with an AI assistant. Make sure every sentence is true and sounds like you — some universities ask you to declare AI help.</div>}

      <div className="layout-2">
        <div className="stack">
          {isSop && ws.can_edit && <Interview st={st} questions={questions} answers={answers} setAnswers={setAnswers} editable={editable} busy={busyAll} dirty={answersDirty} onSave={() => save("Answers saved")} />}

          <div className="card">
            <div className="card-head">
              <h3>{isSop && ws.can_edit ? "2. Statement" : "Text"}</h3>
              <div className="toolbar">
                <button type="button" className="btn btn-outline btn-sm" onClick={() => copyText(text, toast)} disabled={!text}>Copy</button>
                <button type="button" className="btn btn-outline btn-sm" onClick={() => downloadText(text, st.title)} disabled={!text}>Download .txt</button>
              </div>
            </div>
            {editable && isSop && (
              <div className="writing-ai-bar">
                <button type="button" className="btn btn-primary btn-sm" disabled={busyAll || !!blocked} title={blocked || undefined}
                  onClick={() => (wordCount(text) ? setConfirm({ kind: "redraft" }) : draft())}>
                  ✨ {wordCount(text) ? "Write a new draft from the answers" : "Write first draft with AI"}
                </button>
                {!wordCount(text) && !blocked && <span className="small muted">Or just start typing below.</span>}
              </div>
            )}
            {editable && !isSop && st.reference_id && (
              <div className="writing-ai-bar">
                <button type="button" className="btn btn-outline btn-sm" disabled={busyAll || !!blocked} title={blocked || undefined} onClick={prepareAgain}>✨ Prepare again from the referee details</button>
              </div>
            )}
            {aiBusy && <div className="alert alert-info writing-working" role="status"><span className="writing-spinner" aria-hidden="true" />{aiBusy} This usually takes 10–30 seconds.</div>}
            {editable
              ? <textarea className="writing-text" aria-label="Statement text" value={text} onChange={(e) => setText(e.target.value)} disabled={!!aiBusy}
                  placeholder={isSop ? "Start writing, or answer the interview questions and let the assistant write a first draft." : "The brief appears here."} />
              : <div className="writing-read">{text ? text.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>) : <p className="muted">No text yet.</p>}</div>}
            <WordMeter text={text} limit={st.word_limit} />
            {editable && (
              <div className="toolbar" style={{ marginTop: ".8rem" }}>
                <button type="button" className="btn btn-primary" onClick={() => save()} disabled={busyAll || !textDirty}>{busy && !aiBusy ? "Saving…" : textDirty ? "Save changes" : "Saved"}</button>
                {textDirty && <span className="small muted">Ctrl+S saves</span>}
              </div>
            )}
          </div>

          {editable && isSop && wordCount(text) > 0 && (
            <div className="card">
              <h3>Improve with AI</h3>
              <p className="small muted">Pick a quick fix or describe what you want. Each change is saved as a new version, so you can always go back.</p>
              <div className="writing-presets">
                {REVISE_PRESETS.map((p) => <button key={p} type="button" className="chip-btn" onClick={() => improve(p)} disabled={busyAll || !!blocked}>{p}</button>)}
              </div>
              <form noValidate className="writing-custom" onSubmit={(e) => { e.preventDefault(); if (instruction.trim()) { improve(instruction.trim()); setInstruction(""); } }}>
                <Field label="Or tell the assistant what to change"><input maxLength={300} placeholder="e.g. Mention the hackathon win in the second paragraph" value={instruction} onChange={(e) => setInstruction(e.target.value)} /></Field>
                <button type="submit" className="btn btn-outline" disabled={busyAll || !!blocked || !instruction.trim()}>Improve</button>
              </form>
            </div>
          )}
        </div>

        <div className="stack">
          {ws.can_edit && (
            <div className="card">
              <div className="card-head"><h3>AI review</h3>
                <button type="button" className="btn btn-outline btn-sm" onClick={review} disabled={busyAll || !!blocked || wordCount(text) < 50} title={wordCount(text) < 50 ? "Write at least 50 words first" : blocked || undefined}>{st.feedback ? "Review again" : "Get feedback"}</button></div>
              <Feedback fb={st.feedback} current={st.versions?.at(-1)?.n} />
            </div>
          )}
          <Comments st={st} user={user} onAdd={comment} busy={busy} />
          {ws.can_edit && <Versions st={st} editable={editable} onRestore={restore} busy={busyAll} />}
          {ws.can_edit && (
            <div className="card">
              <h3>Details</h3>
              <dl className="facts">
                <dt>Word limit</dt><dd>{st.word_limit?.toLocaleString()} words</dd>
                <dt>Student</dt><dd><Link to={`/students/${encodeURIComponent(st.student_id)}/`}>{st.student_name}</Link></dd>
                {st.application_id && <><dt>Application</dt><dd><Link to={`/applications/${encodeURIComponent(st.application_id)}/`}>Open application</Link></dd></>}
              </dl>
              <button type="button" className="btn btn-danger btn-sm" onClick={() => setConfirm({ kind: "delete" })} disabled={busyAll}>Delete</button>
            </div>
          )}
          {user.role === "student" && st.status === "Final" && (
            <div className="card"><h3>Next step</h3><p className="small">Download this SOP, make any last personal touches, and upload it as your SOP under <Link to="/documents/">Documents</Link>.</p></div>
          )}
        </div>
      </div>

      {confirm?.kind === "redraft" && (
        <ConfirmDialog title="Write a new draft?" confirmLabel="Write new draft" busyLabel="Working…" busy={busyAll}
          onConfirm={() => { setConfirm(null); draft(); }} onCancel={() => setConfirm(null)}>
          <p>The assistant will write a fresh draft from the interview answers. The current text is kept under Versions, so nothing is lost.</p>
        </ConfirmDialog>
      )}
      {confirm?.kind === "final" && (
        <ConfirmDialog title="Mark as final?" confirmLabel="Mark as final" busyLabel="Saving…" busy={busy}
          onConfirm={() => setStatus("Final")} onCancel={() => setConfirm(null)}>
          {placeholderCount(text) > 0
            ? <p><b>There {placeholderCount(text) === 1 ? "is 1 gap" : `are ${placeholderCount(text)} gaps`} ([ADD: …]) still in the text.</b> Fill them in first, or mark it final anyway.</p>
            : <p>The text will be locked. You can move it back to draft later if something needs changing.</p>}
        </ConfirmDialog>
      )}
      {confirm?.kind === "delete" && (
        <ConfirmDialog title="Delete this draft?" danger confirmLabel="Delete" busyLabel="Deleting…" busy={busy}
          onConfirm={remove} onCancel={() => setConfirm(null)}>
          <p><b>{st.title}</b>, its versions and comments will be deleted. This cannot be undone.</p>
        </ConfirmDialog>
      )}
      {guard.pending && (
        <ConfirmDialog title="Save your changes before leaving?" confirmLabel="Save and leave" busyLabel="Saving…" cancelLabel="Stay on this page" busy={busy}
          onConfirm={async () => { if (await save()) guard.leave(); }} onCancel={guard.stay}
          extraAction={{ label: "Leave without saving", onClick: guard.leave }}>
          <p>You have unsaved changes to this draft. If you leave now, they will be lost.</p>
        </ConfirmDialog>
      )}
    </>
  );
}

export default function Statement() {
  const { statementId } = useParams();
  const { user } = useAuth();
  const { data, error, reload } = useLoad(async () => {
    const statement = await api(`/writing/statements/${encodeURIComponent(statementId)}/`);
    const workspace = await api("/writing/", { query: { student_id: user.role === "student" ? "" : statement.student_id } });
    return { statement, workspace };
  }, [statementId]);
  const title = data?.statement.title || "Draft";
  const back = user.role === "student" ? "/writing/" : data ? `/writing/?student_id=${encodeURIComponent(data.statement.student_id)}` : "/writing/";

  return (
    <AppShell title={title} crumb={<><Link to={back}>SOP &amp; LOR</Link> / {data?.statement.student_name || "Draft"}</>}>
      {error ? (
        <>
          <div className="page-head"><div><h1>Draft</h1></div></div>
          <ErrorAlert error={error} onRetry={error.status === 403 || error.status === 404 ? undefined : reload}>
            {error.status === 403 && user.role === "student" ? "Your counsellor has not shared this draft with you yet." : recordError(error, "draft")}
          </ErrorAlert>
          <p><Link to={back}>Back to SOP &amp; LOR</Link></p>
        </>
      ) : !data ? <Loading text="Loading draft…" /> : <Editor initial={data} user={user} />}
    </AppShell>
  );
}
