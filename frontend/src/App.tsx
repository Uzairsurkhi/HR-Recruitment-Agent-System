import { useCallback, useEffect, useRef, useState } from "react";

type Role = {
  id: string;
  title: string;
  headcount_target: number;
  email_template_prepared: boolean;
  created_at: string;
};

type Candidate = {
  id: string;
  role_id: string;
  full_name: string;
  email: string | null;
  ats_score: number | null;
  stage: string;
  technical_total_score: number | null;
  created_at: string;
};

type Summary = {
  roles: Role[];
  candidates: Candidate[];
  stage_counts: Record<string, number>;
};

const api = (path: string, init?: RequestInit) => fetch(path, init);

const wsUrl = (path: string) => {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
};

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [roleFilter, setRoleFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");

  const load = useCallback(async () => {
    setErr(null);
    const q = new URLSearchParams();
    if (roleFilter) q.set("role_id", roleFilter);
    if (stageFilter) q.set("stage", stageFilter);
    const res = await api(`/api/dashboard/summary?${q.toString()}`);
    if (!res.ok) {
      setErr(await res.text());
      return;
    }
    setSummary(await res.json());
  }, [roleFilter, stageFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="app">
      <header>
        <h1>HR Recruitment Agent</h1>
        <p>Dashboard, resume pipeline, technical interview (30s timer), and grounded HR chatbot.</p>
      </header>

      {err && (
        <p style={{ color: "var(--danger)" }}>
          {err}
        </p>
      )}

      <div className="grid grid-2">
        <FiltersPanel
          summary={summary}
          roleFilter={roleFilter}
          stageFilter={stageFilter}
          onRoleFilter={setRoleFilter}
          onStageFilter={setStageFilter}
          onRefresh={load}
        />
        <CreateRolePanel onCreated={load} />
      </div>

      <div style={{ marginTop: "1rem" }} className="grid grid-2">
        <UploadPanel roles={summary?.roles ?? []} onUploaded={load} />
        <StageCounts summary={summary} />
      </div>

      <div style={{ marginTop: "1rem" }}>
        <CandidatesTable candidates={summary?.candidates ?? []} roles={summary?.roles ?? []} />
      </div>

      <div style={{ marginTop: "1rem" }}>
        <TechnicalInterviewPanel onComplete={load} />
      </div>

      <div style={{ marginTop: "1rem" }} className="grid grid-2">
        <ScreeningPanel onDone={load} />
        <SchedulingPanel onDone={load} />
      </div>

      <div style={{ marginTop: "1rem" }}>
        <ChatbotPanel />
      </div>
    </div>
  );
}

function FiltersPanel({
  summary,
  roleFilter,
  stageFilter,
  onRoleFilter,
  onStageFilter,
  onRefresh,
}: {
  summary: Summary | null;
  roleFilter: string;
  stageFilter: string;
  onRoleFilter: (v: string) => void;
  onStageFilter: (v: string) => void;
  onRefresh: () => void;
}) {
  const stages = summary ? Object.keys(summary.stage_counts).sort() : [];
  return (
    <div className="panel">
      <h2>Filters</h2>
      <div className="row">
        <div>
          <label>Role</label>
          <select value={roleFilter} onChange={(e) => onRoleFilter(e.target.value)}>
            <option value="">All roles</option>
            {(summary?.roles ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label>Stage</label>
          <select value={stageFilter} onChange={(e) => onStageFilter(e.target.value)}>
            <option value="">All stages</option>
            {stages.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div style={{ flex: 0 }}>
          <button type="button" className="secondary" onClick={() => void onRefresh()}>
            Refresh
          </button>
        </div>
      </div>
    </div>
  );
}

function CreateRolePanel({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [jd, setJd] = useState("");
  const [hc, setHc] = useState(1);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await api("/api/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          job_description: jd,
          headcount_target: hc,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setTitle("");
      setJd("");
      setHc(1);
      onCreated();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2>New role posting</h2>
      <form onSubmit={(e) => void submit(e)}>
        <label>Title</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} required minLength={2} />
        <label style={{ marginTop: "0.5rem" }}>Job description</label>
        <textarea value={jd} onChange={(e) => setJd(e.target.value)} required minLength={20} />
        <label style={{ marginTop: "0.5rem" }}>Headcount</label>
        <input
          type="number"
          min={1}
          value={hc}
          onChange={(e) => setHc(Number(e.target.value))}
        />
        <div style={{ marginTop: "0.75rem" }}>
          <button type="submit" disabled={busy}>
            Create role
          </button>
        </div>
      </form>
    </div>
  );
}

function UploadPanel({ roles, onUploaded }: { roles: Role[]; onUploaded: () => void }) {
  const [roleId, setRoleId] = useState("");
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !roleId) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("role_id", roleId);
      fd.append("full_name", name);
      fd.append("experience_level", "mid");
      const res = await api("/api/candidates/upload", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      setFile(null);
      setName("");
      onUploaded();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2>Upload resume (ATS)</h2>
      <form onSubmit={(e) => void submit(e)}>
        <label>Role</label>
        <select value={roleId} onChange={(e) => setRoleId(e.target.value)} required>
          <option value="">Select…</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title}
            </option>
          ))}
        </select>
        <label style={{ marginTop: "0.5rem" }}>Candidate name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} required />
        <label style={{ marginTop: "0.5rem" }}>Resume file (.pdf, .txt, .docx)</label>
        <input
          type="file"
          accept=".pdf,.txt,.docx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          required
        />
        <div style={{ marginTop: "0.75rem" }}>
          <button type="submit" disabled={busy}>
            Upload &amp; score
          </button>
        </div>
      </form>
    </div>
  );
}

function StageCounts({ summary }: { summary: Summary | null }) {
  if (!summary) return <div className="panel"><h2>Pipeline stages</h2><p style={{ color: "var(--muted)" }}>Loading…</p></div>;
  return (
    <div className="panel">
      <h2>Counts by stage</h2>
      <table>
        <tbody>
          {Object.entries(summary.stage_counts).map(([k, v]) => (
            <tr key={k}>
              <td>
                <span className="badge">{k}</span>
              </td>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CandidatesTable({ candidates, roles }: { candidates: Candidate[]; roles: Role[] }) {
  const roleTitle = (id: string) => roles.find((r) => r.id === id)?.title ?? id.slice(0, 8);
  return (
    <div className="panel">
      <h2>Candidates</h2>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
              <th>Stage</th>
              <th>ATS</th>
              <th>Tech</th>
              <th>Email</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id}>
                <td>{c.full_name}</td>
                <td>{roleTitle(c.role_id)}</td>
                <td>
                  <span className="badge">{c.stage}</span>
                </td>
                <td>{c.ats_score != null ? c.ats_score.toFixed(1) : "—"}</td>
                <td>{c.technical_total_score != null ? c.technical_total_score.toFixed(1) : "—"}</td>
                <td style={{ fontSize: "0.8rem" }}>{c.email ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TechnicalInterviewPanel({ onComplete }: { onComplete: () => void }) {
  const [candidateId, setCandidateId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [level, setLevel] = useState("mid");
  const [log, setLog] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [busy, setBusy] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<number | null>(null);

  function stopTimer() {
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = null;
  }

  async function startRest() {
    if (!candidateId) return;
    setBusy(true);
    try {
      const res = await api(
        `/api/candidates/${encodeURIComponent(candidateId)}/technical/start?experience_level=${encodeURIComponent(level)}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSessionId(data.session_id);
      setLog((l) => [...l, `Session ${data.session_id} — connect WebSocket and send start.`]);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  }

  function connectWs() {
    wsRef.current?.close();
    const ws = new WebSocket(wsUrl("/ws/interview"));
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data as string) as Record<string, unknown>;
      if (msg.type === "question") {
        setQuestion(String(msg.text ?? ""));
        setAnswer("");
        const sec = Number(msg.answer_seconds ?? 30);
        setSecondsLeft(sec);
        stopTimer();
        timerRef.current = window.setInterval(() => {
          setSecondsLeft((s) => {
            if (s <= 1) {
              stopTimer();
              return 0;
            }
            return s - 1;
          });
        }, 1000);
      } else if (msg.type === "complete") {
        stopTimer();
        setLog((l) => [...l, "Interview complete."]);
        setQuestion("");
        onComplete();
      } else if (msg.type === "error") {
        setLog((l) => [...l, `Error: ${String(msg.message)}`]);
      }
    };
    ws.onopen = () => {
      setLog((l) => [...l, "WebSocket connected."]);
      ws.send(
        JSON.stringify({
          type: "start",
          session_id: sessionId,
          candidate_id: candidateId,
          experience_level: level,
        })
      );
    };
  }

  function sendAnswer() {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert("WebSocket not ready");
      return;
    }
    ws.send(
      JSON.stringify({
        type: "answer",
        text: answer,
        session_id: sessionId,
        candidate_id: candidateId,
        experience_level: level,
      })
    );
  }

  return (
    <div className="panel">
      <h2>Technical interview (WebSocket + 30s)</h2>
      <label>Candidate ID (must be in technical_interview stage)</label>
      <input value={candidateId} onChange={(e) => setCandidateId(e.target.value)} placeholder="uuid" />
      <div className="row" style={{ marginTop: "0.5rem" }}>
        <div>
          <label>Level</label>
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="junior">Junior</option>
            <option value="mid">Mid</option>
            <option value="senior">Senior</option>
          </select>
        </div>
      </div>
      <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" disabled={busy} onClick={() => void startRest()}>
          1. Start session (REST)
        </button>
        <button type="button" disabled={!sessionId} onClick={() => connectWs()}>
          2. Connect &amp; first question
        </button>
      </div>
      {question && (
        <div style={{ marginTop: "1rem" }}>
          <p>
            <strong>Question</strong>{" "}
            <span className="timer">{secondsLeft}s</span>
          </p>
          <p>{question}</p>
          <label>Answer (paste disabled)</label>
          <textarea
            className="no-paste"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onPaste={(e) => e.preventDefault()}
          />
          <div style={{ marginTop: "0.5rem" }}>
            <button type="button" onClick={() => sendAnswer()}>
              Submit answer
            </button>
          </div>
        </div>
      )}
      <div style={{ marginTop: "0.75rem", fontSize: "0.8rem", color: "var(--muted)" }}>
        {log.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    </div>
  );
}

function ScreeningPanel({ onDone }: { onDone: () => void }) {
  const [cid, setCid] = useState("");
  const [questions, setQuestions] = useState<{ id: string; text: string }[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [join, setJoin] = useState("");

  async function start() {
    const res = await api(`/api/candidates/${encodeURIComponent(cid)}/screening/start`, {
      method: "POST",
    });
    if (!res.ok) {
      alert(await res.text());
      return;
    }
    const data = await res.json();
    setQuestions(data.questions ?? []);
  }

  async function submit() {
    const res = await api(`/api/candidates/${encodeURIComponent(cid)}/screening/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        responses: answers,
        notice_period: notice,
        joining_earliest: join,
      }),
    });
    if (!res.ok) {
      alert(await res.text());
      return;
    }
    onDone();
    alert("Screening saved.");
  }

  return (
    <div className="panel">
      <h2>HR screening</h2>
      <label>Candidate ID (hr_screening)</label>
      <input value={cid} onChange={(e) => setCid(e.target.value)} />
      <div style={{ marginTop: "0.5rem" }}>
        <button type="button" className="secondary" onClick={() => void start()}>
          Load questions
        </button>
      </div>
      {questions.map((q) => (
        <div key={q.id} style={{ marginTop: "0.75rem" }}>
          <label>{q.text}</label>
          <textarea
            value={answers[q.id] ?? ""}
            onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
          />
        </div>
      ))}
      <label style={{ marginTop: "0.75rem" }}>Notice period</label>
      <input value={notice} onChange={(e) => setNotice(e.target.value)} />
      <label style={{ marginTop: "0.5rem" }}>Earliest joining</label>
      <input value={join} onChange={(e) => setJoin(e.target.value)} />
      {questions.length > 0 && (
        <div style={{ marginTop: "0.75rem" }}>
          <button type="button" onClick={() => void submit()}>
            Submit screening
          </button>
        </div>
      )}
    </div>
  );
}

function SchedulingPanel({ onDone }: { onDone: () => void }) {
  const [cid, setCid] = useState("");
  const [note, setNote] = useState("");

  async function submit() {
    const res = await api(`/api/candidates/${encodeURIComponent(cid)}/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ availability_note: note }),
    });
    if (!res.ok) {
      alert(await res.text());
      return;
    }
    const data = await res.json();
    onDone();
    alert(`Scheduled. Meeting: ${data.meeting_link}`);
  }

  return (
    <div className="panel">
      <h2>Scheduling &amp; email</h2>
      <label>Candidate ID (scheduling)</label>
      <input value={cid} onChange={(e) => setCid(e.target.value)} />
      <label style={{ marginTop: "0.5rem" }}>Availability</label>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} required minLength={3} />
      <div style={{ marginTop: "0.75rem" }}>
        <button type="button" onClick={() => void submit()}>
          Confirm &amp; send emails
        </button>
      </div>
    </div>
  );
}

function ChatbotPanel() {
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string }[]>([]);
  const [input, setInput] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<string | null>(null);

  function ensureWs(): WebSocket {
    let ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) return ws;
    ws = new WebSocket(wsUrl("/ws/hr-chat"));
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data as string) as { type?: string; text?: string };
      if (msg.type === "message") {
        setMessages((m) => [...m, { role: "bot", text: msg.text ?? "" }]);
      }
    };
    return ws;
  }

  function send() {
    const text = input.trim();
    if (!text) return;
    const ws = ensureWs();
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    const payload = JSON.stringify({ message: text });
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(payload);
    } else {
      pendingRef.current = payload;
      ws.onopen = () => {
        const p = pendingRef.current;
        pendingRef.current = null;
        if (p) ws.send(p);
      };
    }
  }

  return (
    <div className="panel">
      <h2>HR chatbot (WebSocket, DB-grounded)</h2>
      <p style={{ fontSize: "0.85rem", color: "var(--muted)", marginTop: 0 }}>
        Try: “How many candidates in technical_interview?” or “set stage &lt;id&gt; to scheduling” or “create role
        title: X jd: …”
      </p>
      <button type="button" className="secondary" onClick={() => ensureWs()}>
        Connect
      </button>
      <div className="chat-log">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role === "user" ? "hr" : "bot"}`}>
            <strong>{m.role === "user" ? "You" : "Agent"}:</strong> {m.text}
          </div>
        ))}
      </div>
      <div className="row">
        <div style={{ flex: 3 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Message…"
          />
        </div>
        <div style={{ flex: 0 }}>
          <button type="button" onClick={() => send()}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
