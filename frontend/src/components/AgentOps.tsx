import { useMemo } from "react";
import type { AgentInfo, Answer, Narration } from "../types";

const CHAIN = ["stats", "tactics", "narrator", "persona"];

interface Step {
  agent: string;
  path: string;
  status: string;
  ms: number;
}

interface AgentTotals {
  runs: number;
  llm: number;
  fallbacks: number;
  ms: number;
}

/** The trace entries that record a finished agent step (the others note a model error inside a step). */
function steps(n: Narration): Step[] {
  return n.trace
    .filter((s) => s.path !== undefined)
    .map((s) => ({ agent: s.agent, path: s.path ?? "", status: s.status ?? "ok", ms: s.ms ?? 0 }));
}

function pathLabel(path: string): string {
  if (path === "llm") return "LLM";
  if (path === "deterministic") return "rules";
  return path;
}

/**
 * The multi-agent team at work, live: the last narration's run through the agent chain (path taken and
 * latency per agent), running totals per agent, and the tools the Ask agent called for the last question.
 */
export function AgentOps({ agents, narrations, answers }: { agents: AgentInfo[]; narrations: Narration[]; answers: Answer[] }) {
  const latest = narrations[0];
  const last = latest ? steps(latest) : [];
  const total = last.reduce((sum, s) => sum + s.ms, 0);

  const totals = useMemo(() => {
    const out: Record<string, AgentTotals> = {};
    for (const n of narrations) {
      for (const s of steps(n)) {
        const t = (out[s.agent] ??= { runs: 0, llm: 0, fallbacks: 0, ms: 0 });
        if (s.path === "skipped") continue;
        t.runs += 1;
        t.ms += s.ms;
        if (s.path === "llm") t.llm += 1;
        if (s.status !== "ok") t.fallbacks += 1;
      }
    }
    return out;
  }, [narrations]);

  const fallbacks = Object.values(totals).reduce((sum, t) => sum + t.fallbacks, 0);
  const lastAnswer = answers[0];
  const roles = Object.fromEntries(agents.map((a) => [a.name, a.role]));

  return (
    <div className="panel agent-ops">
      <h3>
        Agent team · live
        <span className="ops-sum">
          {narrations.length} lines · {fallbacks} fallback{fallbacks === 1 ? "" : "s"}
        </span>
      </h3>

      {latest ? (
        <div className="ops-run" key={`${latest.t}-${latest.kind}`}>
          <div className="ops-run-head">
            <span className="muted">Last line</span> <b>{latest.clock}</b> <span className="ops-kind">{latest.kind.replace(/_/g, " ")}</span>
            <span className="muted ops-total">{Math.round(total)} ms</span>
          </div>
          <div className="ops-chain">
            {CHAIN.map((name, i) => {
              const s = last.find((x) => x.agent === name);
              return (
                <div key={name} className="ops-step-wrap">
                  {i > 0 && <span className="ops-arrow">→</span>}
                  <div
                    className={`ops-step path-${s?.path ?? "none"} ${s && s.status !== "ok" ? "fallback" : ""}`}
                    style={{ animationDelay: `${i * 0.18}s` }}
                    title={`${roles[name] ?? ""}${s ? ` · ${s.status}` : ""}`}
                  >
                    <b>{name}</b>
                    <span>{s ? pathLabel(s.path) : "–"}</span>
                    <span className="ops-ms">{s && s.path !== "skipped" ? `${Math.round(s.ms)} ms` : ""}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <p className="muted">Waiting for the first moment. Each line runs stats → tactics → narrator → persona.</p>
      )}

      <table className="ops-table">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Runs</th>
            <th>LLM</th>
            <th>Avg</th>
            <th>Fallback</th>
          </tr>
        </thead>
        <tbody>
          {CHAIN.map((name) => {
            const t = totals[name];
            return (
              <tr key={name} title={roles[name]}>
                <td>{name}</td>
                <td>{t?.runs ?? 0}</td>
                <td>{t && t.runs ? `${Math.round((100 * t.llm) / t.runs)}%` : "–"}</td>
                <td>{t && t.runs ? `${Math.round(t.ms / t.runs)} ms` : "–"}</td>
                <td className={t?.fallbacks ? "warn" : ""}>{t?.fallbacks ?? 0}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="ops-ask" title={roles.ask}>
        <b>ask</b>{" "}
        {lastAnswer ? (
          <>
            <span className="muted">called</span>{" "}
            {lastAnswer.tools.length ? lastAnswer.tools.map((c, i) => <code key={i}>{c.tool}</code>) : <span className="muted">no tools</span>}{" "}
            <span className="muted">· {lastAnswer.ms} ms</span>
          </>
        ) : (
          <span className="muted">function calling over 6 live-data tools, waiting for a question</span>
        )}
      </div>
      <div className="ops-ask muted">
        <b>recap</b> writes the half-time and full-time report on demand
      </div>
    </div>
  );
}
