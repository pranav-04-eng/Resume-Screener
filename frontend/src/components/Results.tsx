import { useEffect, useState } from "react";
import { getJob, type JobResults } from "../api";

const TERMINAL = new Set(["COMPLETED", "FAILED"]);

export function Results({ jobId, onReset }: { jobId: string; onReset: () => void }) {
  const [job, setJob] = useState<JobResults | null>(null);
  const [error, setError] = useState("");

  // Poll until the job reaches a terminal state.
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const data = await getJob(jobId);
        if (!active) return;
        setJob(data);
        if (!TERMINAL.has(data.status)) timer = setTimeout(poll, 2000);
      } catch (err) {
        if (active) setError(String(err));
      }
    }
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [jobId]);

  if (error) return <div className="card error">{error}</div>;
  if (!job) return <div className="card">Loading…</div>;

  const done = job.processed_resumes + job.failed_resumes;
  return (
    <div className="card">
      <div className="results-head">
        <div>
          <h2>{job.title}</h2>
          <span className={`badge badge-${job.status.toLowerCase()}`}>{job.status}</span>
          <span className="hint">
            {done}/{job.total_resumes} processed
            {job.failed_resumes > 0 && ` · ${job.failed_resumes} failed`}
          </span>
        </div>
        <button onClick={onReset}>New job</button>
      </div>

      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Candidate</th>
            <th>Score</th>
            <th>Summary</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {job.candidates.map((c) => (
            <tr key={c.resume_id}>
              <td>{c.rank ?? "—"}</td>
              <td>
                <strong>{c.extracted?.name ?? c.file_name}</strong>
                <div className="hint">{c.file_name}</div>
              </td>
              <td>{c.score != null ? c.score.toFixed(0) : "—"}</td>
              <td className="summary">
                {c.summary ?? (c.status === "FAILED" ? c.error : "…")}
                {c.strengths.length > 0 && (
                  <div className="tags">
                    {c.strengths.slice(0, 4).map((s) => (
                      <span key={s} className="tag">{s}</span>
                    ))}
                  </div>
                )}
              </td>
              <td>
                <span className={`badge badge-${c.status.toLowerCase()}`}>{c.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
