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

export type EvaluationResult = {
  id: number;
  run_id: number;
  test_case_id: number;
  generated_transcript: string;
  generated_file_path: string | null;
  wer: number | null;
  cer: number | null;
  quality_label: string | null;
  error_summary: string | null;
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

export type ReleaseStatus = "pass" | "warn" | "fail";

export type ReleaseSeverity =
  | "none"
  | "low"
  | "medium"
  | "high"
  | "critical";

export type ReleaseCheck = {
  metric: string;
  label: string;
  observed_value: number;
  warn_threshold: number;
  fail_threshold: number;
  status: ReleaseStatus;
  message: string;
};

export type ReleaseReport = {
  id: number;
  project_id: number;
  comparison_id: number;
  policy_id: number | null;
  status: ReleaseStatus;
  severity: ReleaseSeverity;
  headline: string;
  summary: string;
  recommendation: string;
  policy_snapshot: Record<string, unknown>;
  checks: ReleaseCheck[];
  created_at: string;
  updated_at: string;
};


export type ProjectWorkflowSummary = {
  project_id: number;
  dataset_count: number;
  test_case_count: number;
  run_count: number;
  evaluated_run_count: number;
  result_count: number;
  comparison_count: number;
  debug_case_count: number;
  open_debug_case_count: number;
  latest_run: EvaluationRun | null;
  latest_comparison: RunComparison | null;
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
  test_case_id: number | null;
  baseline_result_id: number | null;
  current_result_id: number | null;
  summary: string | null;
  engineer_notes: string | null;
  ai_suggestion: string | null;
  created_at: string;
};

export type DebugCaseDetail = {
  debug_case: DebugCase;
  test_case: TestCase | null;
  baseline_run: EvaluationRun | null;
  current_run: EvaluationRun | null;
  baseline_result: EvaluationResult | null;
  current_result: EvaluationResult | null;
};

export type TranscribeAndEvaluateResponse = {
  result: EvaluationResult;
  provider: string;
  model_name: string;
  generated_transcript: string;
};

export type StructuredTranscriptDiffToken = {
  operation: "match" | "insertion" | "deletion" | "substitution";
  reference_word: string | null;
  generated_word: string | null;
  display_text: string;
};

export type StructuredTranscriptDiff = {
  result_id: number;
  test_case_id: number;
  reference_transcript: string;
  generated_transcript: string;
  wer: number | null;
  cer: number | null;
  substitutions: number;
  insertions: number;
  deletions: number;
  matches: number;
  tokens: StructuredTranscriptDiffToken[];
};

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, options);

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


export async function getProjectWorkflowSummary(projectId: number) {
  return fetchJson<ProjectWorkflowSummary>(
    `/projects/${projectId}/workflow-summary`,
  );
}

export async function createProjectDataset(
  projectId: number,
  dataset: { name: string; description: string | null },
) {
  return fetchJson<Dataset>(`/projects/${projectId}/datasets`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(dataset),
  });
}

export async function getProjectDatasets(projectId: number) {
  return fetchJson<Dataset[]>(`/projects/${projectId}/datasets`);
}

export async function getDatasetTestCases(datasetId: number) {
  return fetchJson<TestCase[]>(`/datasets/${datasetId}/test-cases`);
}

export async function createDatasetTestCase(
  datasetId: number,
  testCase: { title: string; audioFile: File; referenceFile: File },
) {
  const formData = new FormData();
  formData.append("title", testCase.title);
  formData.append("audio_file", testCase.audioFile);
  formData.append("reference_file", testCase.referenceFile);

  return fetchJson<TestCase>(`/datasets/${datasetId}/test-cases`, {
    method: "POST",
    body: formData,
  });
}

export async function getProjectRuns(projectId: number) {
  return fetchJson<EvaluationRun[]>(`/projects/${projectId}/runs`);
}

export async function createProjectRun(
  projectId: number,
  run: { run_name: string; model_name: string },
) {
  return fetchJson<EvaluationRun>(`/projects/${projectId}/runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(run),
  });
}

export async function evaluateTestCaseForRun(
  runId: number,
  testCaseId: number,
  generatedFile: File,
) {
  const formData = new FormData();
  formData.append("generated_file", generatedFile);

  return fetchJson<EvaluationResult>(
    `/runs/${runId}/test-cases/${testCaseId}/evaluate`,
    {
      method: "POST",
      body: formData,
    },
  );
}

export async function getProjectComparisons(projectId: number) {
  return fetchJson<RunComparison[]>(`/projects/${projectId}/comparisons`);
}

export async function compareRuns(runIds: {
  baseline_run_id: number;
  current_run_id: number;
}) {
  return fetchJson<RunComparison>("/runs/compare", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(runIds),
  });
}

export async function createReleaseReport(comparisonId: number) {
  return fetchJson<ReleaseReport>(
    `/comparisons/${comparisonId}/release-report`,
    {
      method: "POST",
    },
  );
}

export async function getReleaseReport(comparisonId: number) {
  return fetchJson<ReleaseReport>(
    `/comparisons/${comparisonId}/release-report`,
  );
}

export async function createDebugCaseFromComparison(comparisonId: number) {
  return fetchJson<DebugCase>(`/comparisons/${comparisonId}/debug-case`, {
    method: "POST",
  });
}

export async function getLatestComparison() {
  return fetchJson<RunComparison>("/comparisons/1");
}

export async function getProjectDebugCases(projectId: number) {
  return fetchJson<DebugCase[]>(`/projects/${projectId}/debug-cases`);
}


export async function getDebugCaseDetails(debugCaseId: number) {
  return fetchJson<DebugCaseDetail>(`/debug-cases/${debugCaseId}/details`);
}


export async function getResultTranscriptDiff(resultId: number) {
  return fetchJson<StructuredTranscriptDiff>(
    `/results/${resultId}/transcript-diff`,
  );
}


export async function transcribeAndEvaluateTestCaseForRun(
  runId: number,
  testCaseId: number,
) {
  return fetchJson<TranscribeAndEvaluateResponse>(
    `/runs/${runId}/test-cases/${testCaseId}/transcribe-and-evaluate`,
    {
      method: "POST",
    },
  );
}
