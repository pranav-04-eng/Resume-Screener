import { useState } from "react";
import { createJob, submitJob, uploadToS3 } from "../api";

export function CreateJob({ onCreated }: { onCreated: (jobId: string) => void }) {
  const [title, setTitle] = useState("");
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [resumes, setResumes] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState("");
  const [error, setError] = useState("");

  const canSubmit = title.trim() && jdFile && resumes.length > 0 && !busy;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!jdFile) return;
    setBusy(true);
    setError("");
    try {
      setStep("Creating job…");
      const job = await createJob({ title, jdFile, resumeFiles: resumes });

      setStep("Uploading job description…");
      await uploadToS3(job.jd_upload, jdFile);

      // Match each presigned target to its file by name, then upload.
      setStep(`Uploading ${resumes.length} resume(s)…`);
      await Promise.all(
        job.resume_uploads.map((target) => {
          const file = resumes.find((f) => f.name === target.file_name);
          if (!file) throw new Error(`missing file ${target.file_name}`);
          return uploadToS3(target, file);
        })
      );

      setStep("Submitting for scoring…");
      await submitJob(job.job_id);
      onCreated(job.job_id);
    } catch (err) {
      setError(String(err));
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <label>
        Job title
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Senior Backend Engineer"
        />
      </label>

      <label>
        Job description file
        <input type="file" onChange={(e) => setJdFile(e.target.files?.[0] ?? null)} />
      </label>

      <label>
        Resumes (select multiple)
        <input
          type="file"
          multiple
          onChange={(e) => setResumes(Array.from(e.target.files ?? []))}
        />
      </label>
      {resumes.length > 0 && <p className="hint">{resumes.length} resume(s) selected</p>}

      <button type="submit" disabled={!canSubmit}>
        {busy ? step : "Score candidates"}
      </button>

      {error && <p className="error">{error}</p>}
    </form>
  );
}
