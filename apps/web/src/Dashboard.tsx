import { useEffect, useState } from "react";

interface Counts {
  success: number;
  failure: number;
}

interface Status {
  ci: Counts;
  deploy: Counts;
  open_autotriage_issues: number;
}

interface Agent {
  name: string;
  purpose: string;
  trigger: string;
  module: string;
  workflow_file?: string;
}

interface AgentsResponse {
  count: number;
  agents: Agent[];
}

type StatusState =
  | { kind: "loading" }
  | { kind: "ok"; data: Status }
  | { kind: "error"; status: number };

type AgentsState =
  | { kind: "loading" }
  | { kind: "ok"; data: Agent[] }
  | { kind: "error"; status: number };

const cardStyle: React.CSSProperties = {
  border: "1px solid #2a2a2a",
  borderRadius: 8,
  padding: 16,
  margin: "16px 0",
  background: "#0f0f10",
  color: "#e5e5e5",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  maxWidth: 480,
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  padding: "6px 0",
  borderBottom: "1px solid #1f1f20",
};

const labelStyle: React.CSSProperties = { color: "#a1a1aa" };
const okStyle: React.CSSProperties = { color: "#10b981", fontWeight: 600 };
const failStyle: React.CSSProperties = { color: "#f43f5e", fontWeight: 600 };
const dimStyle: React.CSSProperties = { color: "#71717a" };

function Row({ label, ok, fail }: { label: string; ok: number; fail: number }) {
  return (
    <div style={rowStyle}>
      <span style={labelStyle}>{label}</span>
      <span>
        <span style={okStyle}>{ok}</span>
        <span style={dimStyle}> success / </span>
        <span style={fail > 0 ? failStyle : dimStyle}>{fail}</span>
        <span style={dimStyle}> failure</span>
      </span>
    </div>
  );
}

function StatusCard({ state }: { state: StatusState }) {
  if (state.kind === "loading") {
    return (
      <section style={cardStyle}>
        <h2 style={{ margin: "0 0 8px" }}>Harness status</h2>
        <p style={dimStyle}>Loading…</p>
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section style={cardStyle}>
        <h2 style={{ margin: "0 0 8px" }}>Harness status</h2>
        <p style={failStyle}>Status unavailable (HTTP {state.status})</p>
      </section>
    );
  }
  const { data } = state;
  const issuesStyle = data.open_autotriage_issues > 0 ? failStyle : okStyle;
  return (
    <section style={cardStyle}>
      <h2 style={{ margin: "0 0 8px" }}>Harness status</h2>
      <Row label="CI (last 20)" ok={data.ci.success} fail={data.ci.failure} />
      <Row label="Deploy (last 20)" ok={data.deploy.success} fail={data.deploy.failure} />
      <div style={rowStyle}>
        <span style={labelStyle}>Open autotriage issues</span>
        <span style={issuesStyle}>{data.open_autotriage_issues}</span>
      </div>
    </section>
  );
}

function AgentsCard({ state }: { state: AgentsState }) {
  if (state.kind === "loading") {
    return (
      <section style={cardStyle}>
        <h2 style={{ margin: "0 0 8px" }}>Agents</h2>
        <p style={dimStyle}>Loading…</p>
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section style={cardStyle}>
        <h2 style={{ margin: "0 0 8px" }}>Agents</h2>
        <p style={failStyle}>Agents unavailable (HTTP {state.status})</p>
      </section>
    );
  }
  return (
    <section style={cardStyle}>
      <h2 style={{ margin: "0 0 8px" }}>Agents ({state.data.length})</h2>
      {state.data.map((a) => (
        <div key={a.name} style={rowStyle}>
          <span style={okStyle}>{a.name}</span>
          <span style={dimStyle}>{a.purpose}</span>
        </div>
      ))}
    </section>
  );
}

export function Dashboard() {
  const [status, setStatus] = useState<StatusState>({ kind: "loading" });
  const [agents, setAgents] = useState<AgentsState>({ kind: "loading" });

  useEffect(() => {
    fetch("/api/status")
      .then(async (resp) => {
        if (!resp.ok) {
          setStatus({ kind: "error", status: resp.status });
          return;
        }
        const data = (await resp.json()) as Status;
        setStatus({ kind: "ok", data });
      })
      .catch(() => setStatus({ kind: "error", status: 0 }));

    fetch("/api/agents")
      .then(async (resp) => {
        if (!resp.ok) {
          setAgents({ kind: "error", status: resp.status });
          return;
        }
        const data = (await resp.json()) as AgentsResponse;
        setAgents({ kind: "ok", data: data.agents });
      })
      .catch(() => setAgents({ kind: "error", status: 0 }));
  }, []);

  return (
    <>
      <StatusCard state={status} />
      <AgentsCard state={agents} />
    </>
  );
}
