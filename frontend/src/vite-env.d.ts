/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_INTAKE_URL?: string;
  readonly VITE_RESULTS_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
