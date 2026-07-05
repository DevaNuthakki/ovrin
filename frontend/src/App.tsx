import "./App.css";

type MetricCard = {
  label: string;
  value: string;
  helper: string;
  status?: "good" | "warning" | "danger" | "neutral";
};

type DebugCase = {
  id: number;
  title: string;
  severity: "high" | "medium" | "low";
  status: "open" | "reviewing" | "closed";
  summary: string;
};

const metrics: MetricCard[] = [
  {
    label: "Projects",
    value: "1",
    helper: "Active ASR evaluation workspace",
    status: "neutral",
  },
  {
    label: "Open debug cases",
    value: "1",
    helper: "Regression needs review",
    status: "danger",
  },
  {
    label: "Latest WER delta",
    value: "+0.500",
    helper: "Current run is worse than baseline",
    status: "danger",
  },
  {
    label: "Latest CER delta",
    value: "+0.421",
    helper: "Character error rate increased",
    status: "warning",
  },
];

const debugCases: DebugCase[] = [
  {
    id: 1,
    title: "Regression detected: Baseline run vs Current run with regression",
    severity: "high",
    status: "open",
    summary:
      "Baseline WER=0.100, current WER=0.600. The current run has a large regression and needs debugging.",
  },
];

function getStatusLabel(status?: MetricCard["status"]) {
  if (status === "good") return "Good";
  if (status === "warning") return "Warning";
  if (status === "danger") return "Needs attention";
  return "Neutral";
}

function App() {
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
            <button className="secondary-button" type="button">
              View API status
            </button>
            <button className="primary-button" type="button">
              New evaluation run
            </button>
          </div>
        </header>

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
              <span className="status-pill danger">Regression</span>
            </div>

            <dl className="comparison-list">
              <div>
                <dt>Baseline run</dt>
                <dd>Baseline run</dd>
              </div>
              <div>
                <dt>Current run</dt>
                <dd>Current run with regression</dd>
              </div>
              <div>
                <dt>WER change</dt>
                <dd className="danger-text">+0.500</dd>
              </div>
              <div>
                <dt>CER change</dt>
                <dd className="warning-text">+0.421</dd>
              </div>
            </dl>

            <div className="insight-box" role="note">
              <strong>Engineer summary</strong>
              <p>
                The current run is significantly worse than the baseline. Start
                by reviewing transcript differences and recent model or decoding
                changes.
              </p>
            </div>
          </article>

          <article className="panel" id="debug-cases">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Debug queue</p>
                <h3>Open debug cases</h3>
              </div>
              <span className="count-badge">{debugCases.length}</span>
            </div>

            <div className="debug-case-list">
              {debugCases.map((debugCase) => (
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
                  <p>{debugCase.summary}</p>

                  <button className="text-button" type="button">
                    Open debug case
                  </button>
                </article>
              ))}
            </div>
          </article>
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