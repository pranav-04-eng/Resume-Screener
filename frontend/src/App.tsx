import { useState } from "react";
import { CreateJob } from "./components/CreateJob";
import { Results } from "./components/Results";

export function App() {
  const [jobId, setJobId] = useState<string | null>(null);

  return (
    <div className="container">
      <header>
        <h1>Resume Screener</h1>
        <p className="sub">Upload a job description and resumes — get ranked candidates.</p>
      </header>

      {jobId ? (
        <Results jobId={jobId} onReset={() => setJobId(null)} />
      ) : (
        <CreateJob onCreated={setJobId} />
      )}
    </div>
  );
}
