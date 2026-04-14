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

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: Status }
  | { kind: "error"; status: number };

export function Dashboard() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    fetch("/api/status")
      .then(async (resp) => {
        if (!resp.ok) {
          setState({ kind: "error", status: resp.status });
          return;
        }
        const data = (await resp.json()) as Status;
        setState({ kind: "ok", data });
      })
      .catch(() => setState({ kind: "error", status: 0 }));
  }, []);

  if (state.kind === "loading") {
    return <section><p>Loading status…</p></section>;
  }
  if (state.kind === "error") {
    return <section><p>Status unavailable (HTTP {state.status})</p></section>;
  }
  const { data } = state;
  return (
    <section>
      <h2>Harness status</h2>
      <ul>
        <li>CI: {data.ci.success} success, {data.ci.failure} failure</li>
        <li>Deploys: {data.deploy.success} success, {data.deploy.failure} failure</li>
        <li>Open autotriage issues: {data.open_autotriage_issues}</li>
      </ul>
    </section>
  );
}
