const API_BASE_URL = "http://127.0.0.1:8000";

export type Project = {
  id: number;
  name: string;
  description: string | null;
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

export async function getLatestComparison() {
  return fetchJson<RunComparison>("/comparisons/1");
}

export async function getProjectDebugCases(projectId: number) {
  return fetchJson<DebugCase[]>(`/projects/${projectId}/debug-cases`);
}