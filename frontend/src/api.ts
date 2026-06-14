// API client + types mirroring screener_common.models.

const INTAKE = import.meta.env.VITE_INTAKE_URL ?? "http://localhost:8001";
const RESULTS = import.meta.env.VITE_RESULTS_URL ?? "http://localhost:8002";

export type JobStatus = "CREATED" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
export type CandidateStatus = "PENDING" | "PROCESSING" | "SCORED" | "FAILED";

export interface PresignedTarget {
  upload_url: string;
  key: string;
  resume_id?: string;
  file_name: string;
}

export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
  jd_upload: PresignedTarget;
  resume_uploads: PresignedTarget[];
}

export interface ExtractedFields {
  name?: string;
  email?: string;
  years_experience?: number;
  current_title?: string;
  skills: string[];
}

export interface CandidateResult {
  resume_id: string;
  file_name: string;
  status: CandidateStatus;
  rank?: number;
  score?: number;
  summary?: string;
  strengths: string[];
  gaps: string[];
  extracted?: ExtractedFields;
  error?: string;
}

export interface JobResults {
  job_id: string;
  title: string;
  status: JobStatus;
  created_at: string;
  total_resumes: number;
  processed_resumes: number;
  failed_resumes: number;
  candidates: CandidateResult[];
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export async function createJob(input: {
  title: string;
  jdFile: File;
  resumeFiles: File[];
}): Promise<CreateJobResponse> {
  const body = {
    title: input.title,
    jd_file_name: input.jdFile.name,
    jd_content_type: input.jdFile.type || "application/octet-stream",
    resumes: input.resumeFiles.map((f) => ({
      file_name: f.name,
      content_type: f.type || "application/octet-stream",
    })),
  };
  const res = await fetch(`${INTAKE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<CreateJobResponse>(res);
}

// Upload a file straight to S3 using the pre-signed PUT URL.
export async function uploadToS3(target: PresignedTarget, file: File): Promise<void> {
  const res = await fetch(target.upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!res.ok) throw new Error(`upload failed for ${file.name}: ${res.status}`);
}

export async function submitJob(jobId: string): Promise<void> {
  await json(await fetch(`${INTAKE}/jobs/${jobId}/submit`, { method: "POST" }));
}

export async function getJob(jobId: string): Promise<JobResults> {
  return json<JobResults>(await fetch(`${RESULTS}/jobs/${jobId}`));
}
