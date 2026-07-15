import { useEffect, useMemo, useState, type FormEvent } from "react";
import "./App.css";
import {
  compareRuns,
  createDebugCaseFromComparison,
  createDatasetTestCase,
  createProjectDataset,
  createProjectRun,
  evaluateTestCaseForRun,
  getDatasetTestCases,
  getDebugCaseDetails,
  getLatestComparison,
  getProject,
  getProjectComparisons,
  getProjectDatasets,
  getProjectDebugCases,
  getProjectRuns,
  getProjectWorkflowSummary,
  getProjects,
  getResultTranscriptDiff,
  transcribeAndEvaluateTestCaseForRun,
  type Dataset,
  type DebugCase,
  type DebugCaseDetail,
  type EvaluationResult,
  type EvaluationRun,
  type Project,
  type ProjectWorkflowSummary,
  type RunComparison,
  type StructuredTranscriptDiff,
  type TestCase,
} from "./api";

type MetricCard = {
  label: string;
  value: string;
  helper: string;
  status?: "good" | "warning" | "danger" | "neutral";
};

type TranscriptDiffToken = {
  value: string;
  type:
    | "same"
    | "reference"
    | "hypothesis"
    | "match"
    | "insertion"
    | "deletion"
    | "substitution";
};

type WorkspaceData = {
  datasets: Dataset[];
  testCasesByDataset: Record<number, TestCase[]>;
  runs: EvaluationRun[];
  comparisons: RunComparison[];
  debugCases: DebugCase[];
  workflowSummary: ProjectWorkflowSummary;
};

function formatMetric(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(3)}`;
}

function formatScore(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }

  return value.toFixed(3);
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function cleanLabel(value: string | null | undefined) {
  if (!value) return "Not available";

  return value.replaceAll("_", " ");
}

function getStatusLabel(status?: MetricCard["status"]) {
  if (status === "good") return "Good";
  if (status === "warning") return "Warning";
  if (status === "danger") return "Needs attention";
  return "Neutral";
}

function getMetricStatus(value: number | null | undefined): MetricCard["status"] {
  if (value === null || value === undefined) {
    return "neutral";
  }

  if (value >= 0.05) {
    return "danger";
  }

  if (value > 0) {
    return "warning";
  }

  if (value < 0) {
    return "good";
  }

  return "neutral";
}

function getComparisonStatus(status: string | undefined): MetricCard["status"] {
  if (status === "regression") return "danger";
  if (status === "improvement") return "good";
  return "neutral";
}

function getQualityStatus(label: string | null): MetricCard["status"] {
  if (label === "excellent" || label === "good") return "good";
  if (label === "needs_review") return "warning";
  if (label === "regression") return "danger";
  return "neutral";
}

function getSeverityStatus(severity: string | null | undefined): MetricCard["status"] {
  if (severity === "high" || severity === "critical") return "danger";
  if (severity === "medium") return "warning";
  if (severity === "low") return "good";
  return "neutral";
}

function splitTranscript(value: string | null | undefined) {
  return value?.trim().split(/\s+/).filter(Boolean) ?? [];
}

function getTranscriptDiff(
  reference: string | null | undefined,
  hypothesis: string | null | undefined,
): TranscriptDiffToken[] {
  const referenceWords = splitTranscript(reference);
  const hypothesisWords = splitTranscript(hypothesis);

  if (referenceWords.length === 0 && hypothesisWords.length === 0) {
    return [];
  }

  const table = Array.from({ length: referenceWords.length + 1 }, () =>
    Array(hypothesisWords.length + 1).fill(0),
  );

  for (let i = referenceWords.length - 1; i >= 0; i -= 1) {
    for (let j = hypothesisWords.length - 1; j >= 0; j -= 1) {
      if (referenceWords[i].toLowerCase() === hypothesisWords[j].toLowerCase()) {
        table[i][j] = table[i + 1][j + 1] + 1;
      } else {
        table[i][j] = Math.max(table[i + 1][j], table[i][j + 1]);
      }
    }
  }

  const tokens: TranscriptDiffToken[] = [];
  let i = 0;
  let j = 0;

  while (i < referenceWords.length || j < hypothesisWords.length) {
    if (
      i < referenceWords.length &&
      j < hypothesisWords.length &&
      referenceWords[i].toLowerCase() === hypothesisWords[j].toLowerCase()
    ) {
      tokens.push({ value: referenceWords[i], type: "same" });
      i += 1;
      j += 1;
      continue;
    }

    const deleteScore = i < referenceWords.length ? table[i + 1][j] : -1;
    const insertScore = j < hypothesisWords.length ? table[i][j + 1] : -1;

    if (j < hypothesisWords.length && insertScore >= deleteScore) {
      tokens.push({ value: hypothesisWords[j], type: "hypothesis" });
      j += 1;
    } else if (i < referenceWords.length) {
      tokens.push({ value: referenceWords[i], type: "reference" });
      i += 1;
    }
  }

  return tokens;
}

function getErrorCount(text: string, labels: string[]) {
  for (const label of labels) {
    const match = text.match(new RegExp(`${label}\\s*[=:]\\s*(\\d+)`, "i"));

    if (match) {
      return Number(match[1]);
    }
  }

  return 0;
}

function getDebugLabels(
  debugCase: DebugCase,
  currentRun: EvaluationRun | null | undefined,
) {
  const labels = new Set<string>();
  const failureType = cleanLabel(debugCase.failure_type);
  const errorText = currentRun?.error_summary?.toLowerCase() ?? "";

  if (failureType !== "Not available") {
    labels.add(failureType);
  }

  if (debugCase.failure_type === "regression") {
    labels.add("Regression");
  }

  if ((currentRun?.wer ?? 0) >= 0.15) {
    labels.add("High WER");
  }

  const insertionCount = getErrorCount(errorText, ["insertion", "insertions"]);
  const deletionCount = getErrorCount(errorText, ["deletion", "deletions"]);
  const substitutionCount = getErrorCount(errorText, [
    "substitution",
    "substitutions",
  ]);

  if (insertionCount > 0) {
    labels.add("Insertion");
  }

  if (deletionCount > 0) {
    labels.add("Deletion");
  }

  if (substitutionCount > 0) {
    labels.add("Substitution");
  }

  if (labels.size === 0) {
    labels.add("Needs review");
  }

  return Array.from(labels);
}

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [debugCases, setDebugCases] = useState<DebugCase[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [workspaceData, setWorkspaceData] = useState<WorkspaceData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isWorkspaceLoading, setIsWorkspaceLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [datasetDescription, setDatasetDescription] = useState("");
  const [datasetFormMessage, setDatasetFormMessage] = useState<string | null>(null);
  const [isCreatingDataset, setIsCreatingDataset] = useState(false);
  const [testCaseDatasetId, setTestCaseDatasetId] = useState<number | "">("");
  const [testCaseTitle, setTestCaseTitle] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [testCaseFormMessage, setTestCaseFormMessage] = useState<string | null>(null);
  const [isCreatingTestCase, setIsCreatingTestCase] = useState(false);
  const [runName, setRunName] = useState("");
  const [modelName, setModelName] = useState("");
  const [runFormMessage, setRunFormMessage] = useState<string | null>(null);
  const [isCreatingRun, setIsCreatingRun] = useState(false);
  const [evaluationRunId, setEvaluationRunId] = useState<number | "">("");
  const [evaluationTestCaseId, setEvaluationTestCaseId] = useState<number | "">("");
  const [generatedFile, setGeneratedFile] = useState<File | null>(null);
  const [evaluationMessage, setEvaluationMessage] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [transcriptionMessage, setTranscriptionMessage] = useState<string | null>(null);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [baselineRunId, setBaselineRunId] = useState<number | "">("");
  const [currentRunId, setCurrentRunId] = useState<number | "">("");
  const [comparisonMessage, setComparisonMessage] = useState<string | null>(null);
  const [isComparingRuns, setIsComparingRuns] = useState(false);
  const [debugCaseMessage, setDebugCaseMessage] = useState<string | null>(null);
  const [isCreatingDebugCase, setIsCreatingDebugCase] = useState(false);
  const [selectedDebugCaseId, setSelectedDebugCaseId] = useState<number | null>(
    null,
  );
  const [selectedDebugCaseDetails, setSelectedDebugCaseDetails] =
    useState<DebugCaseDetail | null>(null);
  const [isDebugDetailsLoading, setIsDebugDetailsLoading] = useState(false);
  const [debugDetailsError, setDebugDetailsError] = useState<string | null>(null);
  const [selectedTranscriptDiff, setSelectedTranscriptDiff] =
    useState<StructuredTranscriptDiff | null>(null);
  const [isTranscriptDiffLoading, setIsTranscriptDiffLoading] = useState(false);
  const [transcriptDiffError, setTranscriptDiffError] = useState<string | null>(
    null,
  );

  useEffect(() => {
    async function loadDashboardData() {
      try {
        setIsLoading(true);
        setErrorMessage(null);

        const projectData = await getProjects();
        setProjects(projectData);

        try {
          const latestComparison = await getLatestComparison();
          setComparison(latestComparison);
        } catch {
          setComparison(null);
        }

        const firstProjectId = projectData[0]?.id;
        if (firstProjectId) {
          const debugCaseData = await getProjectDebugCases(firstProjectId);
          setDebugCases(debugCaseData);
        } else {
          setDebugCases([]);
        }
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Unable to load Ovrin dashboard data.";

        setErrorMessage(message);
      } finally {
        setIsLoading(false);
      }
    }

    loadDashboardData();
  }, []);

  useEffect(() => {
    async function loadWorkspace(projectId: number) {
      try {
        setIsWorkspaceLoading(true);
        setWorkspaceError(null);

        const [
          project,
          datasets,
          runs,
          comparisons,
          projectDebugCases,
          workflowSummary,
        ] = await Promise.all([
          getProject(projectId),
          getProjectDatasets(projectId),
          getProjectRuns(projectId),
          getProjectComparisons(projectId),
          getProjectDebugCases(projectId),
          getProjectWorkflowSummary(projectId),
        ]);

        const testCaseEntries = await Promise.all(
          datasets.map(async (dataset) => {
            const testCases = await getDatasetTestCases(dataset.id);
            return [dataset.id, testCases] as const;
          }),
        );

        setSelectedProject(project);
        setWorkspaceData({
          datasets,
          runs,
          comparisons,
          debugCases: projectDebugCases,
          workflowSummary,
          testCasesByDataset: Object.fromEntries(testCaseEntries),
        });

        setTestCaseDatasetId((current) => current || datasets[0]?.id || "");
        setEvaluationRunId((current) => current || runs[0]?.id || "");

        const evaluatedRuns = runs.filter((run) => run.status === "evaluated");
        setBaselineRunId((current) => current || evaluatedRuns[1]?.id || "");
        setCurrentRunId((current) => current || evaluatedRuns[0]?.id || "");

        const firstTestCase = testCaseEntries[0]?.[1]?.[0];
        setEvaluationTestCaseId((current) => current || firstTestCase?.id || "");
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Unable to load project workspace.";

        setWorkspaceError(message);
      } finally {
        setIsWorkspaceLoading(false);
      }
    }

    if (selectedProjectId) {
      loadWorkspace(selectedProjectId);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    async function loadDebugCaseDetails(debugCaseId: number) {
      try {
        setIsDebugDetailsLoading(true);
        setDebugDetailsError(null);

        const details = await getDebugCaseDetails(debugCaseId);
        setSelectedDebugCaseDetails(details);
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Unable to load debug case details.";

        setDebugDetailsError(message);
        setSelectedDebugCaseDetails(null);
      } finally {
        setIsDebugDetailsLoading(false);
      }
    }

    if (selectedDebugCaseId) {
      loadDebugCaseDetails(selectedDebugCaseId);
    } else {
      setSelectedDebugCaseDetails(null);
      setDebugDetailsError(null);
      setIsDebugDetailsLoading(false);
    }
  }, [selectedDebugCaseId]);

  useEffect(() => {
    const currentResultId = selectedDebugCaseDetails?.current_result?.id;

    async function loadTranscriptDiff(resultId: number) {
      try {
        setIsTranscriptDiffLoading(true);
        setTranscriptDiffError(null);

        const transcriptDiff = await getResultTranscriptDiff(resultId);
        setSelectedTranscriptDiff(transcriptDiff);
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Unable to load structured transcript diff.";

        setTranscriptDiffError(message);
        setSelectedTranscriptDiff(null);
      } finally {
        setIsTranscriptDiffLoading(false);
      }
    }

    if (currentResultId) {
      loadTranscriptDiff(currentResultId);
    } else {
      setSelectedTranscriptDiff(null);
      setTranscriptDiffError(null);
      setIsTranscriptDiffLoading(false);
    }
  }, [selectedDebugCaseDetails?.current_result?.id]);

  const openDebugCases = debugCases.filter(
    (debugCase) => debugCase.status !== "closed",
  );

  const metrics: MetricCard[] = useMemo(
    () => [
      {
        label: "Projects",
        value: String(projects.length),
        helper:
          projects.length === 1
            ? "Active ASR evaluation workspace"
            : "Active ASR evaluation workspaces",
        status: "neutral",
      },
      {
        label: "Open debug cases",
        value: String(openDebugCases.length),
        helper:
          openDebugCases.length > 0
            ? "Regression needs review"
            : "No open regression cases",
        status: openDebugCases.length > 0 ? "danger" : "good",
      },
      {
        label: "Latest WER delta",
        value: formatMetric(comparison?.wer_delta),
        helper:
          comparison?.wer_delta && comparison.wer_delta > 0
            ? "Current run is worse than baseline"
            : "No WER regression detected",
        status: getMetricStatus(comparison?.wer_delta),
      },
      {
        label: "Latest CER delta",
        value: formatMetric(comparison?.cer_delta),
        helper:
          comparison?.cer_delta && comparison.cer_delta > 0
            ? "Character error rate increased"
            : "No CER regression detected",
        status: getMetricStatus(comparison?.cer_delta),
      },
    ],
    [comparison, openDebugCases.length, projects.length],
  );

  const workspaceTestCases = useMemo(() => {
    if (!workspaceData) return [];

    return Object.values(workspaceData.testCasesByDataset).flat();
  }, [workspaceData]);

  const workspaceMetrics: MetricCard[] = useMemo(() => {
    if (!workspaceData) return [];

    const summary = workspaceData.workflowSummary;
    const latestComparison =
      summary.latest_comparison ?? workspaceData.comparisons[0];

    return [
      {
        label: "Datasets",
        value: String(summary.dataset_count),
        helper: "Dataset groups inside this project",
        status: summary.dataset_count > 0 ? "good" : "neutral",
      },
      {
        label: "Test cases",
        value: String(summary.test_case_count),
        helper: "Reference samples ready for evaluation",
        status: summary.test_case_count > 0 ? "good" : "neutral",
      },
      {
        label: "Evaluated runs",
        value: `${summary.evaluated_run_count}/${summary.run_count}`,
        helper: "Runs with computed WER/CER results",
        status: summary.evaluated_run_count > 0 ? "good" : "neutral",
      },
      {
        label: "Results",
        value: String(summary.result_count),
        helper: "Stored test-case evaluation results",
        status: summary.result_count > 0 ? "good" : "neutral",
      },
      {
        label: "Open debug cases",
        value: String(summary.open_debug_case_count),
        helper:
          summary.open_debug_case_count > 0
            ? "Needs engineer review"
            : "No open cases",
        status: summary.open_debug_case_count > 0 ? "danger" : "good",
      },
      {
        label: "Latest WER delta",
        value: formatMetric(latestComparison?.wer_delta),
        helper: latestComparison
          ? cleanLabel(latestComparison.comparison_status)
          : "No run comparison yet",
        status: getMetricStatus(latestComparison?.wer_delta),
      },
    ];
  }, [workspaceData]);

  function closeWorkspace() {
    setSelectedProjectId(null);
    setSelectedProject(null);
    setWorkspaceData(null);
    setWorkspaceError(null);
    setDatasetName("");
    setDatasetDescription("");
    setDatasetFormMessage(null);
    setTestCaseDatasetId("");
    setTestCaseTitle("");
    setAudioFile(null);
    setReferenceFile(null);
    setTestCaseFormMessage(null);
    setRunName("");
    setModelName("");
    setRunFormMessage(null);
    setEvaluationRunId("");
    setEvaluationTestCaseId("");
    setGeneratedFile(null);
    setEvaluationMessage(null);
    setTranscriptionMessage(null);
    setBaselineRunId("");
    setCurrentRunId("");
    setComparisonMessage(null);
    setDebugCaseMessage(null);
    setSelectedDebugCaseId(null);
    setSelectedDebugCaseDetails(null);
    setDebugDetailsError(null);
    setSelectedTranscriptDiff(null);
    setTranscriptDiffError(null);
    setIsTranscriptDiffLoading(false);
  }

  async function handleCreateDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedProjectId || isCreatingDataset) {
      return;
    }

    const name = datasetName.trim();
    const description = datasetDescription.trim();

    if (!name) {
      setDatasetFormMessage("Dataset name is required.");
      return;
    }

    try {
      setIsCreatingDataset(true);
      setDatasetFormMessage(null);

      const newDataset = await createProjectDataset(selectedProjectId, {
        name,
        description: description || null,
      });

      setWorkspaceData((current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          datasets: [newDataset, ...current.datasets],
          testCasesByDataset: {
            [newDataset.id]: [],
            ...current.testCasesByDataset,
          },
        };
      });

      setDatasetName("");
      setDatasetDescription("");
      setTestCaseDatasetId((current) => current || newDataset.id);
      setDatasetFormMessage("Dataset created.");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to create dataset.";

      setDatasetFormMessage(message);
    } finally {
      setIsCreatingDataset(false);
    }
  }

  async function handleCreateTestCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!testCaseDatasetId || isCreatingTestCase) {
      return;
    }

    const title = testCaseTitle.trim();

    if (!title) {
      setTestCaseFormMessage("Test case title is required.");
      return;
    }

    if (!audioFile) {
      setTestCaseFormMessage("Audio file is required.");
      return;
    }

    if (!referenceFile) {
      setTestCaseFormMessage("Reference transcript file is required.");
      return;
    }

    try {
      setIsCreatingTestCase(true);
      setTestCaseFormMessage(null);

      const newTestCase = await createDatasetTestCase(testCaseDatasetId, {
        title,
        audioFile,
        referenceFile,
      });

      setWorkspaceData((current) => {
        if (!current) {
          return current;
        }

        const currentCases = current.testCasesByDataset[testCaseDatasetId] ?? [];

        return {
          ...current,
          testCasesByDataset: {
            ...current.testCasesByDataset,
            [testCaseDatasetId]: [newTestCase, ...currentCases],
          },
        };
      });

      setTestCaseTitle("");
      setAudioFile(null);
      setReferenceFile(null);
      setEvaluationTestCaseId((current) => current || newTestCase.id);
      setTestCaseFormMessage("Test case uploaded.");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to upload test case.";

      setTestCaseFormMessage(message);
    } finally {
      setIsCreatingTestCase(false);
    }
  }

  async function handleCreateRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedProjectId || isCreatingRun) {
      return;
    }

    const name = runName.trim();
    const model = modelName.trim();

    if (!name) {
      setRunFormMessage("Run name is required.");
      return;
    }

    try {
      setIsCreatingRun(true);
      setRunFormMessage(null);

      const newRun = await createProjectRun(selectedProjectId, {
        run_name: name,
        model_name: model || "not_configured",
      });

      setWorkspaceData((current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          runs: [newRun, ...current.runs],
        };
      });

      setRunName("");
      setModelName("");
      setEvaluationRunId((current) => current || newRun.id);
      setRunFormMessage("Run created.");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to create run.";

      setRunFormMessage(message);
    } finally {
      setIsCreatingRun(false);
    }
  }

  async function handleEvaluateTestCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!evaluationRunId || !evaluationTestCaseId || isEvaluating) {
      return;
    }

    if (!generatedFile) {
      setEvaluationMessage("Generated transcript file is required.");
      return;
    }

    try {
      setIsEvaluating(true);
      setEvaluationMessage(null);

      const result = await evaluateTestCaseForRun(
        evaluationRunId,
        evaluationTestCaseId,
        generatedFile,
      );

      setWorkspaceData((current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          runs: current.runs.map((run) =>
            run.id === result.run_id
              ? {
                  ...run,
                  status: "evaluated",
                  generated_transcript: result.generated_transcript,
                  wer: result.wer,
                  cer: result.cer,
                  quality_label: result.quality_label,
                  error_summary: result.error_summary,
                }
              : run,
          ),
        };
      });

      setGeneratedFile(null);
      setBaselineRunId((current) => current || result.run_id);
      setCurrentRunId((current) => current || result.run_id);
      setEvaluationMessage("Test case evaluated.");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to evaluate test case.";

      setEvaluationMessage(message);
    } finally {
      setIsEvaluating(false);
    }
  }

  async function handleTranscribeAndEvaluate() {
    if (!selectedProjectId) {
      setTranscriptionMessage("Open a project workspace first.");
      return;
    }

    if (!evaluationRunId || !evaluationTestCaseId) {
      setTranscriptionMessage("Select a run and test case first.");
      return;
    }

    try {
      setIsTranscribing(true);
      setTranscriptionMessage(null);

      const response = await transcribeAndEvaluateTestCaseForRun(
        evaluationRunId,
        evaluationTestCaseId,
      );

      setTranscriptionMessage(
        `ASR transcript evaluated with ${response.provider}.`,
      );

      // Workspace refresh will happen on the next dashboard/project reload.
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to transcribe audio.";

      setTranscriptionMessage(message);
    } finally {
      setIsTranscribing(false);
    }
  }

  async function handleCompareRuns(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!baselineRunId || !currentRunId || isComparingRuns) {
      return;
    }

    if (baselineRunId === currentRunId) {
      setComparisonMessage("Choose two different runs to compare.");
      return;
    }

    try {
      setIsComparingRuns(true);
      setComparisonMessage(null);

      const comparison = await compareRuns({
        baseline_run_id: baselineRunId,
        current_run_id: currentRunId,
      });

      setWorkspaceData((current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          comparisons: [comparison, ...current.comparisons],
        };
      });

      setComparisonMessage("Runs compared.");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to compare runs.";

      setComparisonMessage(message);
    } finally {
      setIsComparingRuns(false);
    }
  }

  async function handleCreateDebugCase(comparisonId: number) {
    if (isCreatingDebugCase) {
      return;
    }

    try {
      setIsCreatingDebugCase(true);
      setDebugCaseMessage(null);

      const debugCase = await createDebugCaseFromComparison(comparisonId);

      setWorkspaceData((current) => {
        if (!current) {
          return current;
        }

        const alreadyExists = current.debugCases.some(
          (item) => item.id === debugCase.id,
        );

        return {
          ...current,
          debugCases: alreadyExists
            ? current.debugCases.map((item) =>
                item.id === debugCase.id ? debugCase : item,
              )
            : [debugCase, ...current.debugCases],
        };
      });

      setSelectedDebugCaseId(debugCase.id);
      setDebugCaseMessage("Debug case ready.");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to create debug case.";

      setDebugCaseMessage(message);
    } finally {
      setIsCreatingDebugCase(false);
    }
  }

  function getDatasetName(datasetId: number) {
    const dataset = workspaceData?.datasets.find((item) => item.id === datasetId);
    return dataset?.name ?? `Dataset #${datasetId}`;
  }

  function renderDashboard() {
    return (
      <>
        <header className="page-header" id="dashboard">
          <div>
            <p className="eyebrow">Dashboard</p>
            <h2>ASR regression overview</h2>
            <p className="page-description">
              A focused engineering view for tracking speech model quality,
              regressions, and debugging work.
            </p>
          </div>

          <div className="header-actions">
            <a
              className="secondary-button button-link"
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noreferrer"
            >
              View API status
            </a>
            <button className="primary-button" type="button">
              New evaluation run
            </button>
          </div>
        </header>

        {isLoading && (
          <section className="state-banner" role="status" aria-live="polite">
            Loading Ovrin dashboard data from the backend API...
          </section>
        )}

        {errorMessage && (
          <section className="state-banner error" role="alert">
            <strong>Unable to load backend data.</strong>
            <span>{errorMessage}</span>
          </section>
        )}

        <section className="metrics-grid" aria-label="Project metrics">
          {metrics.map((metric) => (
            <article className="metric-card" key={metric.label}>
              <div className="metric-card-header">
                <p>{metric.label}</p>
                <span className={`status-pill ${metric.status}`}>
                  {getStatusLabel(metric.status)}
                </span>
              </div>
              <strong>{metric.value}</strong>
              <span>{metric.helper}</span>
            </article>
          ))}
        </section>

        <section className="dashboard-grid">
          <article className="panel" id="comparisons">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Latest comparison</p>
                <h3>Baseline vs current run</h3>
              </div>
              <span
                className={`status-pill ${getComparisonStatus(
                  comparison?.comparison_status,
                )}`}
              >
                {cleanLabel(comparison?.comparison_status ?? "No comparison")}
              </span>
            </div>

            {comparison ? (
              <>
                <dl className="comparison-list">
                  <div>
                    <dt>Baseline WER</dt>
                    <dd>{formatScore(comparison.baseline_average_wer)}</dd>
                  </div>
                  <div>
                    <dt>Current WER</dt>
                    <dd>{formatScore(comparison.current_average_wer)}</dd>
                  </div>
                  <div>
                    <dt>WER delta</dt>
                    <dd
                      className={
                        comparison.wer_delta && comparison.wer_delta > 0
                          ? "danger-text"
                          : undefined
                      }
                    >
                      {formatMetric(comparison.wer_delta)}
                    </dd>
                  </div>
                  <div>
                    <dt>CER delta</dt>
                    <dd
                      className={
                        comparison.cer_delta && comparison.cer_delta > 0
                          ? "warning-text"
                          : undefined
                      }
                    >
                      {formatMetric(comparison.cer_delta)}
                    </dd>
                  </div>
                </dl>

                <div className="insight-box">
                  <strong>Regression summary</strong>
                  <p>
                    {comparison.summary ??
                      "No comparison summary is available yet."}
                  </p>
                </div>
              </>
            ) : (
              <div className="empty-state">
                No comparison found yet. Create and evaluate two runs, then compare
                them from the backend API.
              </div>
            )}
          </article>

          <article className="panel" id="debug-cases">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Debug queue</p>
                <h3>Open regression cases</h3>
              </div>
              <span className="count-badge">{openDebugCases.length}</span>
            </div>

            {openDebugCases.length === 0 ? (
              <div className="empty-state">
                No open debug cases. New regression cases will appear here.
              </div>
            ) : (
              <div className="debug-case-list">
                {openDebugCases.map((debugCase) => (
                  <article className="debug-case-card" key={debugCase.id}>
                    <div className="debug-case-topline">
                      <span className={`severity-badge ${debugCase.severity}`}>
                        {debugCase.severity}
                      </span>
                      <span className="status-pill neutral">
                        {debugCase.status}
                      </span>
                    </div>

                    <h4>{debugCase.title}</h4>
                    <p>
                      {debugCase.summary ??
                        "No summary is available for this debug case yet."}
                    </p>

                    <button
                      className="text-button"
                      type="button"
                      onClick={() => {
                        setSelectedProjectId(debugCase.project_id);
                        setSelectedDebugCaseId(debugCase.id);
                      }}
                    >
                      Open debug workspace
                    </button>
                  </article>
                ))}
              </div>
            )}
          </article>
        </section>

        <section className="panel full-width-panel" id="projects">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Projects</p>
              <h3>Evaluation workspaces</h3>
            </div>
            <span className="count-badge">{projects.length}</span>
          </div>

          {projects.length === 0 ? (
            <div className="empty-state">
              No projects found. Create a project from the API to start
              organizing datasets, test cases, runs, and debug cases.
            </div>
          ) : (
            <div className="project-grid">
              {projects.map((project) => (
                <article className="project-card" key={project.id}>
                  <div className="project-card-header">
                    <div>
                      <p className="eyebrow">Project #{project.id}</p>
                      <h4>{project.name}</h4>
                    </div>
                    <span className="status-pill neutral">Active</span>
                  </div>

                  <p>
                    {project.description ??
                      "No project description provided yet."}
                  </p>

                  <dl className="project-meta">
                    <div>
                      <dt>Created</dt>
                      <dd>{formatDate(project.created_at)}</dd>
                    </div>
                    <div>
                      <dt>Purpose</dt>
                      <dd>ASR regression evaluation</dd>
                    </div>
                  </dl>

                  <button
                    className="text-button"
                    type="button"
                    onClick={() => setSelectedProjectId(project.id)}
                  >
                    Open project workspace
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="panel full-width-panel" id="runs">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Run pipeline</p>
              <h3>Current backend flow</h3>
            </div>
          </div>

          <ol className="pipeline-list" aria-label="Ovrin evaluation pipeline">
            <li>Project</li>
            <li>Dataset</li>
            <li>Test case</li>
            <li>Evaluation run</li>
            <li>Evaluation result</li>
            <li>Run comparison</li>
            <li>Debug case</li>
          </ol>
        </section>
      </>
    );
  }


  function renderDebugWorkspace() {
    const allCases = workspaceData?.debugCases ?? [];
    const openCases = allCases.filter(
      (debugCase) => debugCase.status !== "closed",
    );
    const workspaceSelectedCase =
      allCases.find((debugCase) => debugCase.id === selectedDebugCaseId) ??
      openCases[0] ??
      allCases[0];

    const selectedCase =
      selectedDebugCaseDetails?.debug_case ?? workspaceSelectedCase;

    const baselineRun =
      selectedDebugCaseDetails?.baseline_run ??
      workspaceData?.runs.find((run) => run.id === selectedCase?.baseline_run_id);

    const currentRun =
      selectedDebugCaseDetails?.current_run ??
      workspaceData?.runs.find((run) => run.id === selectedCase?.current_run_id);

    const testCase = selectedDebugCaseDetails?.test_case ?? null;
    const baselineResult = selectedDebugCaseDetails?.baseline_result ?? null;
    const currentResult = selectedDebugCaseDetails?.current_result ?? null;

    const referenceTranscript =
      testCase?.reference_transcript ??
      currentRun?.reference_transcript ??
      baselineRun?.reference_transcript;

    const generatedTranscript =
      currentResult?.generated_transcript ?? currentRun?.generated_transcript;

    const currentWer = currentResult?.wer ?? currentRun?.wer;
    const currentCer = currentResult?.cer ?? currentRun?.cer;
    const currentQuality = currentResult?.quality_label ?? currentRun?.quality_label;
    const currentErrorSummary =
      currentResult?.error_summary ?? currentRun?.error_summary;

    const labelSourceRun: EvaluationRun | null = currentRun
      ? {
          ...currentRun,
          reference_transcript:
            referenceTranscript ?? currentRun.reference_transcript,
          generated_transcript:
            generatedTranscript ?? currentRun.generated_transcript,
          wer: currentWer ?? currentRun.wer,
          cer: currentCer ?? currentRun.cer,
          quality_label: currentQuality ?? null,
          error_summary: currentErrorSummary ?? null,
        }
      : null;

    const structuredDiffTokens: TranscriptDiffToken[] | null =
      selectedTranscriptDiff?.tokens.map((token) => ({
        value: token.display_text,
        type: token.operation,
      })) ?? null;

    const diffTokens =
      structuredDiffTokens ?? getTranscriptDiff(referenceTranscript, generatedTranscript);

    const diffSummary = selectedTranscriptDiff
      ? [
          ["Matches", selectedTranscriptDiff.matches],
          ["Substitutions", selectedTranscriptDiff.substitutions],
          ["Insertions", selectedTranscriptDiff.insertions],
          ["Deletions", selectedTranscriptDiff.deletions],
        ]
      : [];

    const debugLabels = selectedCase
      ? getDebugLabels(selectedCase, labelSourceRun)
      : [];

    function renderRunInspectionCard(
      label: "Baseline run" | "Current run",
      run: EvaluationRun | null | undefined,
      result: EvaluationResult | null | undefined,
    ) {
      const wer = result?.wer ?? run?.wer;
      const cer = result?.cer ?? run?.cer;
      const qualityLabel = result?.quality_label ?? run?.quality_label ?? null;
      const createdAt = result?.created_at ?? run?.created_at;

      return (
        <article className="debug-run-card">
          <p className="eyebrow">{label}</p>

          {run || result ? (
            <>
              <div className="debug-run-card-title">
                <h4>{run?.run_name ?? `${label} result`}</h4>
                <span className="status-pill neutral">
                  {run?.status ?? "result"}
                </span>
              </div>

              <p>
                {run?.model_name ?? "Run metadata is not available for this result."}
              </p>

              <dl className="debug-meta-grid">
                <div>
                  <dt>WER</dt>
                  <dd>{formatScore(wer)}</dd>
                </div>
                <div>
                  <dt>CER</dt>
                  <dd>{formatScore(cer)}</dd>
                </div>
                <div>
                  <dt>Quality</dt>
                  <dd>{cleanLabel(qualityLabel)}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{createdAt ? formatDate(createdAt) : "—"}</dd>
                </div>
              </dl>
            </>
          ) : (
            <div className="empty-state">
              This debug case does not have a linked {label.toLowerCase()}.
            </div>
          )}
        </article>
      );
    }

    return (
      <>
        <header className="page-header">
          <div>
            <p className="eyebrow">Debug workspace</p>
            <h2>{selectedCase?.title ?? "No debug case selected"}</h2>
            <p className="page-description">
              Inspect the exact failing test case, compare linked results,
              review transcript differences, and decide the next engineering action.
            </p>
          </div>

          <div className="header-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => setSelectedDebugCaseId(null)}
            >
              Back to project
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={closeWorkspace}
            >
              Back to dashboard
            </button>
          </div>
        </header>

        {isWorkspaceLoading && (
          <section className="state-banner" role="status" aria-live="polite">
            Loading project workspace from the backend API...
          </section>
        )}

        {isDebugDetailsLoading && (
          <section className="state-banner" role="status" aria-live="polite">
            Loading result-level debug details...
          </section>
        )}

        {workspaceError && (
          <section className="state-banner error" role="alert">
            <strong>Unable to load project workspace.</strong>
            <span>{workspaceError}</span>
          </section>
        )}

        {debugDetailsError && (
          <section className="state-banner error" role="alert">
            <strong>Unable to load debug details.</strong>
            <span>{debugDetailsError}</span>
          </section>
        )}

        {isTranscriptDiffLoading && (
          <section className="state-banner" role="status" aria-live="polite">
            Loading structured transcript diff...
          </section>
        )}

        {transcriptDiffError && (
          <section className="state-banner error" role="alert">
            <strong>Unable to load structured transcript diff.</strong>
            <span>{transcriptDiffError}</span>
          </section>
        )}

        {!workspaceData ? (
          <section className="empty-state">
            Project workspace data is not loaded yet.
          </section>
        ) : !selectedCase ? (
          <section className="empty-state">
            No debug cases exist for this project yet. Create one from a
            regression comparison first.
          </section>
        ) : (
          <>
            <section className="debug-summary-grid" aria-label="Debug case metrics">
              <article className="metric-card">
                <div className="metric-card-header">
                  <p>Severity</p>
                  <span className={`status-pill ${getSeverityStatus(selectedCase.severity)}`}>
                    {getStatusLabel(getSeverityStatus(selectedCase.severity))}
                  </span>
                </div>
                <strong>{cleanLabel(selectedCase.severity)}</strong>
                <span>Priority for engineer review</span>
              </article>

              <article className="metric-card">
                <div className="metric-card-header">
                  <p>Failure type</p>
                  <span className="status-pill danger">Debug</span>
                </div>
                <strong>{cleanLabel(selectedCase.failure_type)}</strong>
                <span>Primary regression category</span>
              </article>

              <article className="metric-card">
                <div className="metric-card-header">
                  <p>Current WER</p>
                  <span className={`status-pill ${getQualityStatus(currentQuality ?? null)}`}>
                    {cleanLabel(currentQuality)}
                  </span>
                </div>
                <strong>{formatScore(currentWer)}</strong>
                <span>Word error rate for linked current result</span>
              </article>

              <article className="metric-card">
                <div className="metric-card-header">
                  <p>Status</p>
                  <span className="status-pill neutral">{selectedCase.status}</span>
                </div>
                <strong>{cleanLabel(selectedCase.status)}</strong>
                <span>Created {formatDate(selectedCase.created_at)}</span>
              </article>
            </section>

            <section className="debug-workspace-grid">
              <aside className="panel debug-case-browser" aria-label="Debug case list">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Case list</p>
                    <h3>Regression queue</h3>
                  </div>
                  <span className="count-badge">{openCases.length}</span>
                </div>

                {allCases.length === 0 ? (
                  <div className="empty-state">No debug cases found.</div>
                ) : (
                  <div className="debug-workspace-case-list">
                    {allCases.map((debugCase) => (
                      <button
                        className={`debug-workspace-case ${
                          debugCase.id === selectedCase.id ? "active" : ""
                        }`}
                        type="button"
                        key={debugCase.id}
                        onClick={() => setSelectedDebugCaseId(debugCase.id)}
                      >
                        <span className={`severity-badge ${debugCase.severity}`}>
                          {debugCase.severity}
                        </span>
                        <strong>{debugCase.title}</strong>
                        <span>{cleanLabel(debugCase.failure_type)}</span>
                      </button>
                    ))}
                  </div>
                )}
              </aside>

              <article className="panel debug-case-detail">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Case detail</p>
                    <h3>{selectedCase.title}</h3>
                  </div>
                  <span className="status-pill neutral">{selectedCase.status}</span>
                </div>

                <div className="debug-label-row" aria-label="Debug labels">
                  {debugLabels.map((label) => (
                    <span className="debug-label" key={label}>
                      {label}
                    </span>
                  ))}
                </div>

                <div className="insight-box">
                  <strong>Failure summary</strong>
                  <p>
                    {selectedCase.summary ??
                      "No summary is available for this debug case yet."}
                  </p>
                </div>

                <div className="insight-box debug-detail-spacer">
                  <strong>Failing test case</strong>
                  <p>
                    {testCase
                      ? `${testCase.title} — reference sample #${testCase.id}`
                      : "No result-level test case is linked yet."}
                  </p>
                </div>

                <div className="debug-run-grid">
                  {renderRunInspectionCard(
                    "Baseline run",
                    baselineRun,
                    baselineResult,
                  )}
                  {renderRunInspectionCard("Current run", currentRun, currentResult)}
                </div>

                <section className="transcript-grid" aria-label="Transcript comparison">
                  <article className="transcript-panel">
                    <div className="transcript-panel-header">
                      <h4>Reference transcript</h4>
                      <span>Expected test case transcript</span>
                    </div>
                    <p>
                      {referenceTranscript ??
                        "No reference transcript is available for this debug case."}
                    </p>
                  </article>

                  <article className="transcript-panel">
                    <div className="transcript-panel-header">
                      <h4>Generated transcript</h4>
                      <span>Current result output</span>
                    </div>
                    <p>
                      {generatedTranscript ??
                        "No generated transcript is available for this debug case."}
                    </p>
                  </article>
                </section>

                <section className="diff-panel" aria-label="Transcript difference view">
                  <div className="transcript-panel-header">
                    <h4>Difference view</h4>
                    <span>
                      {selectedTranscriptDiff
                        ? "Backend structured diff"
                        : "Frontend fallback diff"}
                    </span>
                  </div>

                  {diffSummary.length > 0 && (
                    <dl className="diff-summary-row" aria-label="Transcript diff counts">
                      {diffSummary.map(([label, value]) => (
                        <div key={label}>
                          <dt>{label}</dt>
                          <dd>{value}</dd>
                        </div>
                      ))}
                    </dl>
                  )}

                  {diffTokens.length === 0 ? (
                    <div className="empty-state">
                      No transcript text is available to generate a difference view.
                    </div>
                  ) : (
                    <div className="diff-token-list">
                      {diffTokens.map((token, index) => (
                        <span className={`diff-token ${token.type}`} key={`${token.value}-${index}`}>
                          {token.value}
                        </span>
                      ))}
                    </div>
                  )}
                </section>

                <section className="debug-notes-grid">
                  <div className="insight-box">
                    <strong>Error summary</strong>
                    <p>
                      {currentErrorSummary ??
                        selectedCase.engineer_notes ??
                        "No error summary is available yet."}
                    </p>
                  </div>

                  <div className="insight-box">
                    <strong>Suggested next action</strong>
                    <p>
                      {selectedCase.ai_suggestion ??
                        "Review the transcript mismatch, check whether the regression is caused by model output changes, audio quality, or reference data issues, then document the finding."}
                    </p>
                  </div>
                </section>
              </article>
            </section>
          </>
        )}
      </>
    );
  }

  function renderWorkspace() {
    const latestComparison = workspaceData?.comparisons[0];
    const openCases =
      workspaceData?.debugCases.filter((debugCase) => debugCase.status !== "closed") ??
      [];

    return (
      <>
        <header className="page-header">
          <div>
            <p className="eyebrow">Project workspace</p>
            <h2>{selectedProject?.name ?? "Loading project..."}</h2>
            <p className="page-description">
              {selectedProject?.description ??
                "Inspect datasets, test cases, runs, comparisons, and debug cases for this ASR project."}
            </p>
          </div>

          <div className="header-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={closeWorkspace}
            >
              Back to dashboard
            </button>
            <button
              className="primary-button"
              type="button"
              disabled={openCases.length === 0}
              onClick={() => setSelectedDebugCaseId(openCases[0]?.id ?? null)}
            >
              Open debug workspace
            </button>
          </div>
        </header>

        {isWorkspaceLoading && (
          <section className="state-banner" role="status" aria-live="polite">
            Loading project workspace from the backend API...
          </section>
        )}

        {workspaceError && (
          <section className="state-banner error" role="alert">
            <strong>Unable to load project workspace.</strong>
            <span>{workspaceError}</span>
          </section>
        )}

        {workspaceData && (
          <>
            <section className="workspace-summary" aria-label="Workspace metrics">
              {workspaceMetrics.map((metric) => (
                <article className="metric-card" key={metric.label}>
                  <div className="metric-card-header">
                    <p>{metric.label}</p>
                    <span className={`status-pill ${metric.status}`}>
                      {getStatusLabel(metric.status)}
                    </span>
                  </div>
                  <strong>{metric.value}</strong>
                  <span>{metric.helper}</span>
                </article>
              ))}
            </section>

            <section className="workspace-grid">
              <article className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Datasets</p>
                    <h3>Reference groups</h3>
                  </div>
                  <span className="count-badge">{workspaceData.datasets.length}</span>
                </div>

                <form className="dataset-form" onSubmit={handleCreateDataset}>
                  <div className="form-grid">
                    <label className="form-field">
                      <span>Dataset name</span>
                      <input
                        value={datasetName}
                        onChange={(event) => setDatasetName(event.target.value)}
                        placeholder="Example: Noisy call samples"
                      />
                    </label>

                    <label className="form-field">
                      <span>Description</span>
                      <textarea
                        value={datasetDescription}
                        onChange={(event) =>
                          setDatasetDescription(event.target.value)
                        }
                        placeholder="What kind of audio or test cases belong here?"
                        rows={3}
                      />
                    </label>
                  </div>

                  <div className="form-actions">
                    <button
                      className="primary-button"
                      type="submit"
                      disabled={isCreatingDataset}
                    >
                      {isCreatingDataset ? "Creating..." : "Create dataset"}
                    </button>

                    {datasetFormMessage && <span>{datasetFormMessage}</span>}
                  </div>
                </form>

                {workspaceData.datasets.length === 0 ? (
                  <div className="empty-state">
                    No datasets yet. Add a dataset before uploading test cases.
                  </div>
                ) : (
                  <div className="item-list">
                    {workspaceData.datasets.map((dataset) => {
                      const testCaseCount =
                        workspaceData.testCasesByDataset[dataset.id]?.length ?? 0;

                      return (
                        <article className="list-card dataset-card" key={dataset.id}>
                          <div>
                            <p className="eyebrow">Dataset #{dataset.id}</p>
                            <h4>{dataset.name}</h4>
                          </div>
                          <p>
                            {dataset.description ??
                              "No dataset description provided yet."}
                          </p>
                          <div className="list-card-meta-row">
                            <span>{testCaseCount} test cases</span>
                            <span>Created {formatDate(dataset.created_at)}</span>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                )}
              </article>

              <article className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Test cases</p>
                    <h3>Evaluation samples</h3>
                  </div>
                  <span className="count-badge">{workspaceTestCases.length}</span>
                </div>

                {workspaceData.datasets.length === 0 ? (
                  <div className="empty-state">
                    Add a dataset first before uploading test cases.
                  </div>
                ) : (
                  <form className="dataset-form" onSubmit={handleCreateTestCase}>
                    <div className="form-grid">
                      <label className="form-field">
                        <span>Dataset</span>
                        <select
                          value={testCaseDatasetId}
                          onChange={(event) =>
                            setTestCaseDatasetId(Number(event.target.value))
                          }
                        >
                          {workspaceData.datasets.map((dataset) => (
                            <option value={dataset.id} key={dataset.id}>
                              {dataset.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="form-field">
                        <span>Test case title</span>
                        <input
                          value={testCaseTitle}
                          onChange={(event) => setTestCaseTitle(event.target.value)}
                          placeholder="Example: Noisy speaker intro"
                        />
                      </label>

                      <label className="form-field">
                        <span>Audio file</span>
                        <input
                          type="file"
                          accept=".wav,.mp3,.m4a"
                          onChange={(event) =>
                            setAudioFile(event.target.files?.[0] ?? null)
                          }
                        />
                        <small>Allowed: .wav, .mp3, .m4a</small>
                      </label>

                      <label className="form-field">
                        <span>Reference transcript</span>
                        <input
                          type="file"
                          accept=".txt"
                          onChange={(event) =>
                            setReferenceFile(event.target.files?.[0] ?? null)
                          }
                        />
                        <small>Upload a UTF-8 .txt transcript file.</small>
                      </label>
                    </div>

                    <div className="form-actions">
                      <button
                        className="primary-button"
                        type="submit"
                        disabled={isCreatingTestCase}
                      >
                        {isCreatingTestCase ? "Uploading..." : "Upload test case"}
                      </button>

                      {testCaseFormMessage && <span>{testCaseFormMessage}</span>}
                    </div>
                  </form>
                )}

                {workspaceTestCases.length === 0 ? (
                  <div className="empty-state">
                    No test cases yet. Upload one audio file and one reference
                    transcript so Ovrin can evaluate ASR output against expected text.
                  </div>
                ) : (
                  <div className="item-list">
                    {workspaceTestCases.map((testCase) => (
                      <article className="list-card test-case-card" key={testCase.id}>
                        <div>
                          <p className="eyebrow">
                            {getDatasetName(testCase.dataset_id)}
                          </p>
                          <h4>{testCase.title}</h4>
                        </div>

                        <div className="test-case-artifacts">
                          <span
                            className={`artifact-pill ${
                              testCase.audio_file_path ? "available" : "missing"
                            }`}
                          >
                            Audio {testCase.audio_file_path ? "available" : "missing"}
                          </span>
                          <span
                            className={`artifact-pill ${
                              testCase.reference_file_path ? "available" : "missing"
                            }`}
                          >
                            Reference{" "}
                            {testCase.reference_file_path ? "available" : "missing"}
                          </span>
                        </div>

                        <p>{testCase.reference_transcript.slice(0, 180)}...</p>

                        <div className="list-card-meta-row">
                          <span>Created {formatDate(testCase.created_at)}</span>
                          <span>Test case #{testCase.id}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </article>
            </section>

            <section className="panel full-width-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Runs</p>
                  <h3>Evaluation history</h3>
                </div>
                <span className="count-badge">{workspaceData.runs.length}</span>
              </div>

              <div className="workflow-guidance">
                <strong>Run workflow</strong>
                <div className="workflow-step-list">
                  <span>1. Create a baseline run</span>
                  <span>2. Evaluate one or more test cases</span>
                  <span>3. Compare against a current run</span>
                </div>
              </div>

              <form className="dataset-form run-form" onSubmit={handleCreateRun}>
                <div className="form-grid run-form-grid">
                  <label className="form-field">
                    <span>Run name</span>
                    <input
                      value={runName}
                      onChange={(event) => setRunName(event.target.value)}
                      placeholder="Example: Whisper small v2 baseline"
                    />
                  </label>

                  <label className="form-field">
                    <span>Model name</span>
                    <input
                      value={modelName}
                      onChange={(event) => setModelName(event.target.value)}
                      placeholder="Example: whisper-small-v2"
                    />
                  </label>
                </div>

                <div className="form-actions">
                  <button
                    className="primary-button"
                    type="submit"
                    disabled={isCreatingRun}
                  >
                    {isCreatingRun ? "Creating..." : "Create run"}
                  </button>

                  {runFormMessage && <span>{runFormMessage}</span>}
                </div>
              </form>

              {workspaceData.runs.length === 0 || workspaceTestCases.length === 0 ? (
                <div className="empty-state spaced-state">
                  Create at least one run and upload at least one test case before
                  evaluating ASR output. A run represents one model, provider, or
                  configuration you want to test.
                </div>
              ) : (
                <form
                  className="dataset-form run-form"
                  onSubmit={handleEvaluateTestCase}
                >
                  <div className="form-grid run-form-grid">
                    <label className="form-field">
                      <span>Run</span>
                      <select
                        value={evaluationRunId}
                        onChange={(event) =>
                          setEvaluationRunId(Number(event.target.value))
                        }
                      >
                        {workspaceData.runs.map((run) => (
                          <option value={run.id} key={run.id}>
                            {run.run_name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="form-field">
                      <span>Test case</span>
                      <select
                        value={evaluationTestCaseId}
                        onChange={(event) =>
                          setEvaluationTestCaseId(Number(event.target.value))
                        }
                      >
                        {workspaceTestCases.map((testCase) => (
                          <option value={testCase.id} key={testCase.id}>
                            {testCase.title}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="form-field">
                      <span>Generated transcript</span>
                      <input
                        type="file"
                        accept=".txt"
                        onChange={(event) =>
                          setGeneratedFile(event.target.files?.[0] ?? null)
                        }
                      />
                      <small>
                        Manual path: upload a UTF-8 .txt transcript produced by
                        another ASR model or provider.
                      </small>
                    </label>
                  </div>

                  <div className="evaluation-mode-grid">
                    <div className="evaluation-mode-card">
                      <strong>Manual evaluate</strong>
                      <span>
                        Use when you already have a generated transcript file and
                        want Ovrin to calculate WER/CER.
                      </span>
                    </div>
                    <div className="evaluation-mode-card">
                      <strong>Transcribe + evaluate</strong>
                      <span>
                        Use the configured local ASR provider, then evaluate the
                        generated transcript against the reference.
                      </span>
                    </div>
                  </div>

                  <div className="form-actions">
                    <button
                      className="primary-button"
                      type="submit"
                      disabled={isEvaluating}
                    >
                      {isEvaluating ? "Evaluating..." : "Evaluate test case"}
                    </button>

                    <button
                      className="secondary-button"
                      type="button"
                      disabled={isTranscribing || isEvaluating}
                      onClick={handleTranscribeAndEvaluate}
                    >
                      {isTranscribing ? "Transcribing..." : "Transcribe + evaluate"}
                    </button>

                    {evaluationMessage && <span>{evaluationMessage}</span>}
                    {transcriptionMessage && <span>{transcriptionMessage}</span>}
                  </div>
                </form>
              )}

              {workspaceData.runs.length === 0 ? (
                <div className="empty-state">
                  No evaluation runs yet. Create a run, evaluate test cases, then
                  compare it against another run.
                </div>
              ) : (
                <div className="run-list">
                  {workspaceData.runs.map((run) => (
                    <article className="run-row" key={run.id}>
                      <div>
                        <p className="eyebrow">Run #{run.id}</p>
                        <h4>{run.run_name}</h4>
                        <span>{run.model_name}</span>
                        <div className="run-row-meta">
                          <span>Created {formatDate(run.created_at)}</span>
                          <span>
                            {run.status === "evaluated"
                              ? "Ready for comparison"
                              : "Needs evaluation"}
                          </span>
                        </div>
                      </div>

                      <div className="run-metrics">
                        <span className="status-pill neutral">{cleanLabel(run.status)}</span>
                        <span
                          className={`status-pill ${getQualityStatus(
                            run.quality_label,
                          )}`}
                        >
                          {cleanLabel(run.quality_label)}
                        </span>
                        <strong>WER {formatScore(run.wer)}</strong>
                        <strong>CER {formatScore(run.cer)}</strong>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="dashboard-grid">
              <article className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Comparisons</p>
                    <h3>Baseline vs current</h3>
                  </div>
                  <span className="count-badge">
                    {workspaceData.comparisons.length}
                  </span>
                </div>

                <div className="workflow-guidance comparison-guidance">
                  <strong>Comparison workflow</strong>
                  <div className="workflow-step-list">
                    <span>1. Pick the trusted baseline run</span>
                    <span>2. Pick the current run to check</span>
                    <span>3. Create a debug case only if regression is detected</span>
                  </div>
                </div>

                {workspaceData.runs.filter((run) => run.status === "evaluated").length < 2 ? (
                  <div className="empty-state spaced-state">
                    Evaluate at least two runs before creating a comparison.
                    Use one run as the baseline and another run as the current
                    candidate.
                  </div>
                ) : (
                  <form
                    className="dataset-form run-form"
                    onSubmit={handleCompareRuns}
                  >
                    <div className="form-grid run-form-grid">
                      <label className="form-field">
                        <span>Baseline run</span>
                        <select
                          value={baselineRunId}
                          onChange={(event) =>
                            setBaselineRunId(Number(event.target.value))
                          }
                        >
                          {workspaceData.runs
                            .filter((run) => run.status === "evaluated")
                            .map((run) => (
                              <option value={run.id} key={run.id}>
                                {run.run_name}
                              </option>
                            ))}
                        </select>
                      </label>

                      <label className="form-field">
                        <span>Current run</span>
                        <select
                          value={currentRunId}
                          onChange={(event) =>
                            setCurrentRunId(Number(event.target.value))
                          }
                        >
                          {workspaceData.runs
                            .filter((run) => run.status === "evaluated")
                            .map((run) => (
                              <option value={run.id} key={run.id}>
                                {run.run_name}
                              </option>
                            ))}
                        </select>
                      </label>
                    </div>

                    <div className="form-actions">
                      <button
                        className="primary-button"
                        type="submit"
                        disabled={isComparingRuns}
                      >
                        {isComparingRuns ? "Comparing..." : "Compare runs"}
                      </button>

                      {comparisonMessage && <span>{comparisonMessage}</span>}
                    </div>
                  </form>
                )}

                {latestComparison ? (
                  <>
                    <dl className="comparison-list">
                      <div>
                        <dt>Baseline run</dt>
                        <dd>#{latestComparison.baseline_run_id}</dd>
                      </div>
                      <div>
                        <dt>Current run</dt>
                        <dd>#{latestComparison.current_run_id}</dd>
                      </div>
                      <div>
                        <dt>WER delta</dt>
                        <dd>{formatMetric(latestComparison.wer_delta)}</dd>
                      </div>
                      <div>
                        <dt>CER delta</dt>
                        <dd>{formatMetric(latestComparison.cer_delta)}</dd>
                      </div>
                    </dl>

                    <div className="delta-legend">
                      <span>Positive delta = current run is worse</span>
                      <span>Negative delta = current run improved</span>
                    </div>

                    <div className="insight-box">
                      <strong>{cleanLabel(latestComparison.comparison_status)}</strong>
                      <p>
                        {latestComparison.summary ??
                          "No comparison summary is available yet."}
                      </p>
                    </div>

                    <div className="debug-case-guidance">
                      {latestComparison.comparison_status === "regression"
                        ? "Regression detected. Create a debug case so an engineer can inspect the failing sample."
                        : "Debug case creation is enabled only when the comparison detects a regression."}
                    </div>

                    <div className="form-actions comparison-actions">
                      <button
                        className="primary-button"
                        type="button"
                        disabled={
                          isCreatingDebugCase ||
                          latestComparison.comparison_status !== "regression"
                        }
                        onClick={() =>
                          handleCreateDebugCase(latestComparison.id)
                        }
                      >
                        {isCreatingDebugCase
                          ? "Creating..."
                          : "Create debug case"}
                      </button>

                      {debugCaseMessage && <span>{debugCaseMessage}</span>}
                    </div>
                  </>
                ) : (
                  <div className="empty-state">
                    No comparisons yet. Compare two evaluated runs to see regression
                    deltas here.
                  </div>
                )}
              </article>

              <article className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Debug cases</p>
                    <h3>Regression work queue</h3>
                  </div>
                  <span className="count-badge">{openCases.length}</span>
                </div>

                {openCases.length === 0 ? (
                  <div className="empty-state">
                    No open debug cases for this project.
                  </div>
                ) : (
                  <div className="debug-case-list">
                    {openCases.map((debugCase) => (
                      <article className="debug-case-card" key={debugCase.id}>
                        <div className="debug-case-topline">
                          <span className={`severity-badge ${debugCase.severity}`}>
                            {debugCase.severity}
                          </span>
                          <span className="status-pill neutral">
                            {debugCase.status}
                          </span>
                        </div>

                        <h4>{debugCase.title}</h4>

                        <div className="debug-case-meta-row">
                          <span>{cleanLabel(debugCase.failure_type)}</span>
                          {debugCase.baseline_run_id && (
                            <span>Baseline #{debugCase.baseline_run_id}</span>
                          )}
                          {debugCase.current_run_id && (
                            <span>Current #{debugCase.current_run_id}</span>
                          )}
                        </div>

                        <p>
                          {debugCase.summary ??
                            "No summary is available for this debug case yet."}
                        </p>

                        <button
                            className="text-button"
                            type="button"
                            onClick={() => setSelectedDebugCaseId(debugCase.id)}
                          >
                            Open in debug workspace
                          </button>
                      </article>
                    ))}
                  </div>
                )}
              </article>
            </section>
          </>
        )}
      </>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            O
          </div>
          <div>
            <p className="eyebrow">Ovrin</p>
            <h1>Speech AI Debugger</h1>
          </div>
        </div>

        <nav className="nav-list" aria-label="Ovrin sections">
          <button
            className={`nav-link nav-button ${!selectedProjectId ? "active" : ""}`}
            type="button"
            onClick={closeWorkspace}
          >
            Dashboard
          </button>
          <a className="nav-link" href="#projects" onClick={closeWorkspace}>
            Projects
          </a>
          <a className="nav-link" href="#runs">
            Runs
          </a>
          <a className="nav-link" href="#comparisons">
            Comparisons
          </a>
          <a className="nav-link" href="#debug-cases">
            Debug cases
          </a>
        </nav>

        <section className="sidebar-note" aria-labelledby="workflow-title">
          <h2 id="workflow-title">
            {selectedProject ? "Current project" : "Current workflow"}
          </h2>
          <p>
            {selectedProject
              ? selectedProject.name
              : "Evaluate runs, compare baseline vs current, detect regressions, and create debug cases for engineers."}
          </p>
        </section>
      </aside>

      <section className="content-area">
          {selectedProjectId && selectedDebugCaseId
            ? renderDebugWorkspace()
            : selectedProjectId
              ? renderWorkspace()
              : renderDashboard()}
        </section>
    </main>
  );
}

export default App;
