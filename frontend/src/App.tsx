import { useEffect, useMemo, useState } from "react";
import "./App.css";
import {
  getLatestComparison,
  getProjectDebugCases,
  getProjects,
  type DebugCase,
  type Project,
  type RunComparison,
} from "./api";

type MetricCard = {
  label: string;
  value: string;
  helper: string;
  status?: "good" | "warning" | "danger" | "neutral";
};

function formatMetric(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(3)}`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
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

function getComparisonStatusLabel(status: string | undefined) {
  if (!status) return "No comparison";

  return status.replaceAll("_", " ");
}

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [debugCases, setDebugCases] = useState<DebugCase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    async function loadDashboardData() {
      try {
        setIsLoading(true);
        setErrorMessage(null);

        const projectData = await getProjects();
        setProjects(projectData);

        const latestComparison = await getLatestComparison();
        setComparison(latestComparison);

        const firstProjectId = projectData[0]?.id ?? 1;
        const debugCaseData = await getProjectDebugCases(firstProjectId);
        setDebugCases(debugCaseData);
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
          <a className="nav-link active" href="#dashboard">
            Dashboard
          </a>
          <a className="nav-link" href="#projects">
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
          <h2 id="workflow-title">Current workflow</h2>
          <p>
            Evaluate runs, compare baseline vs current, detect regressions, and
            create debug cases for engineers.
          </p>
        </section>
      </aside>

      <section className="content-area">
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
                className={`status-pill ${
                  comparison?.comparison_status === "regression"
                    ? "danger"
                    : "neutral"
                }`}
              >
                {getComparisonStatusLabel(comparison?.comparison_status)}
              </span>
            </div>

            <dl className="comparison-list">
              <div>
                <dt>Baseline run ID</dt>
                <dd>{comparison?.baseline_run_id ?? "—"}</dd>
              </div>
              <div>
                <dt>Current run ID</dt>
                <dd>{comparison?.current_run_id ?? "—"}</dd>
              </div>
              <div>
                <dt>WER change</dt>
                <dd
                  className={
                    comparison?.wer_delta && comparison.wer_delta > 0
                      ? "danger-text"
                      : ""
                  }
                >
                  {formatMetric(comparison?.wer_delta)}
                </dd>
              </div>
              <div>
                <dt>CER change</dt>
                <dd
                  className={
                    comparison?.cer_delta && comparison.cer_delta > 0
                      ? "warning-text"
                      : ""
                  }
                >
                  {formatMetric(comparison?.cer_delta)}
                </dd>
              </div>
            </dl>

            <div className="insight-box" role="note">
              <strong>Engineer summary</strong>
              <p>
                {comparison?.summary ??
                  "No comparison summary is available yet. Create and compare evaluation runs to populate this view."}
              </p>
            </div>
          </article>

          <article className="panel" id="debug-cases">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Debug queue</p>
                <h3>Open debug cases</h3>
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

                    <button className="text-button" type="button">
                      Open debug case
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

                  <button className="text-button" type="button">
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
      </section>
    </main>
  );
}

export default App;
