const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type Project = {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
};

export type Dataset = {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  created_at: string;
};

export type TestCase = {
  id: number;
  dataset_id: number;
  title: string;
  audio_file_path: string | null;
  reference_file_path: string | null;
  reference_transcript: string;
  created_at: string;
};

export type EvaluationRun = {
  id: number;
  project_id: number;
  run_name: string;
  model_name: string;
  status: string;
  audio_file_path: string | null;
  reference_transcript: string | null;
  generated_transcript: string | null;
  wer: number | null;
  cer: number | null;
  quality_label: string | null;
  error_summary: string | null;
  latency_seconds: number | null;
  created_at: string;
};

export type RunComparison = {
  id: number;
  baseline_run_id: number;
  current_run_id: number;
  baseline_average_wer: number | null;
  current_average_wer: number | null;
  wer_delta: number | null;
  baseline_average_cer: number | null;
  current_average_cer: number | null;
  cer_delta: number | null;
  comparison_status: string;
  summary: string | null;
  created_at: string;
};

export type DebugCase = {
  id: number;
  project_id: number;
  title: string;
  status: string;
  severity: string;
  failure_type: string;
  baseline_run_id: number | null;
  current_run_id: number | null;
  summary: string | null;
  engineer_notes: string | null;
  ai_suggestion: string | null;
  created_at: string;
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export async function getProjects() {
  return fetchJson<Project[]>("/projects");
}

export async function getProject(projectId: number) {
  return fetchJson<Project>(`/projects/${projectId}`);
}

export async function getProjectDatasets(projectId: number) {
  return fetchJson<Dataset[]>(`/projects/${projectId}/datasets`);
}

export async function getDatasetTestCases(datasetId: number) {
  return fetchJson<TestCase[]>(`/datasets/${datasetId}/test-cases`);
}

export async function getProjectRuns(projectId: number) {
  return fetchJson<EvaluationRun[]>(`/projects/${projectId}/runs`);
}

export async function getProjectComparisons(projectId: number) {
  return fetchJson<RunComparison[]>(`/projects/${projectId}/comparisons`);
}

export async function getLatestComparison() {
  return fetchJson<RunComparison>("/comparisons/1");
}

export async function getProjectDebugCases(projectId: number) {
  return fetchJson<DebugCase[]>(`/projects/${projectId}/debug-cases`);
}
