'use client';

import {
  Activity,
  AudioLines,
  CheckCircle2,
  CircleAlert,
  Cpu,
  Database,
  Gauge,
  MemoryStick,
  ShieldCheck,
  Sparkles,
  Wifi,
} from 'lucide-react';
import { motion, useReducedMotion } from 'motion/react';
import { Area, AreaChart, ResponsiveContainer, YAxis } from 'recharts';
import type {
  Action,
  Diagnosis,
  Finding,
  Readiness,
  Snapshot,
} from '@/lib/api';
import {
  actionPending,
  gib,
  reading,
  readinessCopy,
  timeLabel,
  providerLabel,
} from '@/lib/presentation';
import { Badge, CheckMark, Notice, Spinner, StateBadge } from './ui';

function MetricSparkline({
  id,
  history,
  color,
}: {
  id: string;
  history?: { value: number | null }[];
  color: string;
}) {
  if (!history || history.filter((point) => point.value != null).length < 2)
    return null;
  return (
    <ResponsiveContainer
      width="100%"
      height="100%"
      initialDimension={{ width: 145, height: 32 }}
    >
      <AreaChart data={history}>
        <defs>
          <linearGradient id={`shade-${id}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={[0, 100]} />
        <Area
          type="monotone"
          stroke={color}
          strokeWidth={1.65}
          fill={`url(#shade-${id})`}
          dataKey="value"
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function Metrics({
  snapshot,
  history,
  stale = false,
  loading = false,
}: {
  snapshot?: Snapshot;
  history?: Snapshot[];
  stale?: boolean;
  loading?: boolean;
}) {
  const metrics = [
    {
      id: 'cpu',
      label: 'CPU load',
      icon: Cpu,
      value: snapshot?.cpu_percent,
      color: '#a682fa',
      history: history?.map((item) => ({ value: item.cpu_percent })),
      detail: snapshot?.cpu_logical
        ? `${snapshot.cpu_logical} logical cores`
        : 'System utilization',
    },
    {
      id: 'memory',
      label: 'Memory',
      icon: MemoryStick,
      value: snapshot?.memory_percent,
      color: '#71b6f9',
      history: history?.map((item) => ({ value: item.memory_percent })),
      detail:
        snapshot?.memory_available != null
          ? `${gib(snapshot.memory_available)} available`
          : 'Available memory',
    },
    {
      id: 'disk',
      label: 'Storage',
      icon: Database,
      value: snapshot?.disk_percent,
      color: '#66d8b0',
      history: history?.map((item) => ({ value: item.disk_percent })),
      detail:
        snapshot?.disk_free != null
          ? `${gib(snapshot.disk_free)} free`
          : 'Disk capacity',
    },
  ];
  return (
    <div className="metrics-grid">
      {metrics.map(
        ({ id, label, icon: Icon, value, color, history, detail }) => (
          <article
            className="metric card"
            key={id}
            style={{ '--metric-color': color } as React.CSSProperties}
          >
            <header>
              <span className="mini-icon">
                <Icon size={17} />
              </span>
              <span>{label}</span>
            </header>
            <strong
              className={`metric-value ${loading ? 'skeleton' : ''}`}
              aria-label={`${label} ${value == null ? 'unavailable' : `${Math.round(value)} percent`}`}
            >
              {reading(value)}
            </strong>
            <div className="metric-chart" aria-hidden="true">
              <MetricSparkline id={id} history={history} color={color} />
            </div>
            <p>{stale ? 'Last local reading' : detail}</p>
          </article>
        ),
      )}
    </div>
  );
}

export function ReadinessCard({
  state,
  readiness,
  checked,
  down,
  onReview,
}: {
  state: keyof typeof readinessCopy;
  readiness?: Readiness;
  checked: boolean;
  down: boolean;
  onReview: () => void;
}) {
  const copy = readinessCopy[state];
  const Icon =
    state === 'ready'
      ? ShieldCheck
      : state === 'attention' || state === 'not_ready'
        ? CircleAlert
        : Gauge;
  return (
    <article className={`card readiness-panel readiness-${copy.tone}`}>
      <div className="readiness-heading">
        <div className="section-icon">
          <Icon size={23} />
        </div>
        <div>
          <h2>Device readiness</h2>
          <p>
            {down
              ? 'The local device agent is unreachable.'
              : state === 'checking'
                ? copy.description
                : checked
                  ? copy.description
                  : 'Quick checks of your PC and connection.'}
          </p>
        </div>
      </div>
      <StateBadge state={state} />
      <div className="mini-checks">
        {[
          { id: 'cpu', label: 'Performance', icon: Activity },
          { id: 'network', label: 'Network adapter', icon: Wifi },
          { id: 'audio', label: 'Audio check', icon: AudioLines },
        ].map(({ id, label, icon: CheckIcon }) => {
          const performanceWarning =
            id === 'cpu' &&
            readiness?.checks.find(
              (item) =>
                ['cpu', 'workload', 'memory'].includes(item.id) &&
                item.state === 'warning',
            );
          const check = down
            ? undefined
            : performanceWarning ||
              readiness?.checks.find((item) => item.id === id);
          return (
            <div key={id}>
              <CheckIcon size={16} aria-hidden="true" />
              <span>{label}</span>
              <CheckMark state={check?.state ?? 'unknown'} />
            </div>
          );
        })}
      </div>
      <button className="text-button readiness-link" onClick={onReview}>
        View device checks
      </button>
    </article>
  );
}

export function Checks({
  readiness,
  stale,
}: {
  readiness?: Readiness;
  stale: boolean;
}) {
  return readiness ? (
    <ul className="check-list">
      {readiness.checks.map((check) => (
        <li key={check.id}>
          <CheckMark state={stale ? 'unknown' : check.state} />
          <div>
            <strong>{check.label}</strong>
            <p>{check.detail}</p>
          </div>
          <span className="check-label">
            {stale
              ? 'Stale'
              : {
                  passed: 'Passed',
                  warning: 'Review',
                  unknown: 'Unknown',
                  unsupported: 'Unsupported',
                }[check.state]}
          </span>
        </li>
      ))}
    </ul>
  ) : (
    <p className="muted">
      Device checks will appear when the local agent responds.
    </p>
  );
}

export function Workload({
  snapshot,
  history,
  stale = false,
}: {
  snapshot?: Snapshot;
  history?: Snapshot[];
  stale?: boolean;
}) {
  if (!snapshot) return null;
  const workload = snapshot.workload;
  return (
    <div className="workload-strip">
      <div className="mini-icon">
        <Activity size={17} />
      </div>
      <div>
        <strong>Controlled workload</strong>
        <p>
          {workload.active
            ? `${reading(workload.cpu_percent)} of one CPU core · Demo workload`
            : 'No itor workload is running.'}
        </p>
      </div>
      {workload.active && (
        <div className="workload-chart" aria-hidden="true">
          <MetricSparkline
            id="workload"
            color="#f4c681"
            history={history?.map((item) => ({
              value: item.workload.active
                ? (item.workload.cpu_percent ?? null)
                : 0,
            }))}
          />
        </div>
      )}
      <Badge tone={!stale && workload.active ? 'amber' : 'muted'} dot>
        {stale ? 'Last observed' : workload.active ? 'Active' : 'Idle'}
      </Badge>
    </div>
  );
}

export function DiagnosisCard({
  finding,
  diagnosis,
  pending,
  disabled,
  canFix,
  planPending,
  explainingError,
  onExplain,
  onFix,
}: {
  finding?: Finding;
  diagnosis?: Diagnosis;
  pending: boolean;
  disabled: boolean;
  canFix: boolean;
  planPending: boolean;
  explainingError?: string;
  onExplain: () => void;
  onFix: () => void;
}) {
  const reduced = useReducedMotion();
  if (!finding && !diagnosis) return null;
  const evidence = finding
    ? Array.isArray(finding.evidence)
      ? finding.evidence
      : [finding.evidence]
    : (diagnosis?.observed_facts ?? []);
  return (
    <motion.article
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="card detail-card diagnosis-card"
    >
      <div className="section-heading">
        <div className="section-icon violet-icon">
          <Sparkles size={21} />
        </div>
        <div>
          <h2>Diagnosis</h2>
          <p>
            {providerLabel(diagnosis) ?? 'A measured device finding'}
          </p>
        </div>
        {pending && <Spinner />}
      </div>
      <h3>{diagnosis?.headline ?? finding?.title}</h3>
      <div className="evidence-block">
        <span className="eyebrow">Observed evidence</span>
        <ul>
          {evidence.map((fact) => (
            <li key={fact}>{fact}</li>
          ))}
        </ul>
      </div>
      {diagnosis && (
        <div className="diagnosis-explanation">
          <p>{diagnosis.explanation}</p>
          {diagnosis.potential_impact && (
            <p>
              <strong>Potential impact</strong> {diagnosis.potential_impact}
            </p>
          )}
          {diagnosis.uncertainty && (
            <p className="muted">{diagnosis.uncertainty}</p>
          )}
        </div>
      )}
      {!diagnosis && finding && (
        <p className="muted">{finding.potential_impact}</p>
      )}
      {explainingError && <Notice kind="error">{explainingError}</Notice>}
      <div className="button-row">
        {canFix && (
          <button
            className="button primary"
            disabled={disabled || planPending}
            onClick={onFix}
          >
            {planPending ? <Spinner /> : <ShieldCheck size={17} />} Fix this for
            me
          </button>
        )}
        <button
          className="button secondary"
          disabled={disabled || pending}
          onClick={onExplain}
        >
          <Sparkles size={17} />
          {pending
            ? 'Explaining…'
            : diagnosis
              ? 'Refresh explanation'
              : 'Explain this finding'}
        </button>
      </div>
    </motion.article>
  );
}

export function ActionOutcome({ action }: { action?: Action }) {
  if (!action) return null;
  if (actionPending(action.status)) {
    const label = {
      approved: 'Approval received',
      executing: 'Stopping the controlled workload',
      verifying: 'Verifying process exit and measuring again',
    }[action.status as 'approved' | 'executing' | 'verifying'];
    return (
      <article className="card detail-card action-progress" role="status">
        <Spinner />
        <div>
          <h2>{label}</h2>
          <p>Waiting for results from the local agent.</p>
        </div>
      </article>
    );
  }
  if (action.status === 'failed' || action.status === 'expired')
    return (
      <Notice kind="error">
        <strong>
          {action.status === 'expired' ? 'Approval expired' : 'Action failed'}
        </strong>
        <p>{action.message ?? 'Start a new preflight and try again.'}</p>
      </Notice>
    );
  if (action.status !== 'succeeded') return null;
  const labels = [
    ['Before', action.before],
    ['After', action.after],
  ] as const;
  const processExited = action.verification?.process_exited === true;
  return (
    <article className="card detail-card verification-card" aria-live="polite">
      <div className="section-heading">
        <div className="section-icon green-icon">
          <CheckCircle2 size={22} />
        </div>
        <div>
          <h2>
            {processExited
              ? 'Workload stopped and verified'
              : 'Action completed'}
          </h2>
          <p>{action.message ?? 'Measured on this device after approval.'}</p>
        </div>
      </div>
      <div className="comparison">
        {labels.map(([label, measurement]) => (
          <div key={label}>
            <span className="eyebrow">{label}</span>
            <strong>{reading(measurement?.workload_cpu_percent)}</strong>
            <p>Workload CPU · one core</p>
            <dl>
              <div>
                <dt>Workload</dt>
                <dd>
                  {measurement
                    ? measurement.workload_active
                      ? 'Running'
                      : 'Stopped'
                    : 'Unavailable'}
                </dd>
              </div>
              <div>
                <dt>System CPU</dt>
                <dd>{reading(measurement?.system_cpu_percent)}</dd>
              </div>
              <div>
                <dt>Readiness</dt>
                <dd>
                  {measurement
                    ? (readinessCopy[
                        measurement.readiness as keyof typeof readinessCopy
                      ]?.title ?? measurement.readiness)
                    : 'Unavailable'}
                </dd>
              </div>
              <div>
                <dt>Measured</dt>
                <dd>
                  {measurement
                    ? timeLabel(measurement.captured_at)
                    : 'Unavailable'}
                </dd>
              </div>
            </dl>
          </div>
        ))}
      </div>
      {action.verification?.system_cpu_delta != null && (
        <p className="muted">
          System CPU change:{' '}
          {action.verification.system_cpu_delta > 0 ? '+' : ''}
          {action.verification.system_cpu_delta.toFixed(1)} percentage points.
          Other processes can affect system CPU.
        </p>
      )}
    </article>
  );
}
