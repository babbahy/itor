'use client';

import {
  CircleAlert,
  Clock,
  Eye,
  Hand,
  LifeBuoy,
  Send,
  ShieldCheck,
  Trophy,
  WifiOff,
  Wrench,
} from 'lucide-react';
import { useState, useSyncExternalStore } from 'react';
import type {
  CompanyStatus,
  Connectivity,
  Fix,
  Incident,
  Team,
  WorkDayView,
} from '@/lib/api';
import { causeLabel, duration, timeLabel } from '@/lib/presentation';
import { Badge, Notice, Spinner } from './ui';

const stateCopy: Record<WorkDayView['state'], { label: string; tone: string }> = {
  active: { label: 'Active now', tone: 'green' },
  idle: { label: 'Idle', tone: 'muted' },
  lost: { label: 'Losing time to a tool', tone: 'amber' },
  unknown: { label: 'Starting…', tone: 'muted' },
};

function TimeBar({ active, lost, idle }: { active: number; lost: number; idle: number }) {
  const total = active + lost + idle || 1;
  return (
    <div className="time-bar" role="img" aria-label={`Active ${duration(active)}, lost ${duration(lost)}, idle ${duration(idle)}`}>
      <span className="time-active" style={{ width: `${(active / total) * 100}%` }} />
      <span className="time-lost" style={{ width: `${(lost / total) * 100}%` }} />
      <span className="time-idle" style={{ width: `${(idle / total) * 100}%` }} />
    </div>
  );
}

export function DayCard({
  day,
  busy,
  down,
  onBlocked,
}: {
  day?: WorkDayView;
  busy: boolean;
  down: boolean;
  onBlocked: (blocked: boolean) => void;
}) {
  const state = stateCopy[day?.state ?? 'unknown'];
  // Hide causes under 30 s: they would show as "0 min".
  const causes = Object.entries(day?.lost_by_cause ?? {})
    .filter(([, seconds]) => seconds >= 30)
    .sort((a, b) => b[1] - a[1]);
  const frozen = Object.entries(day?.frozen_apps ?? {}).filter(([, seconds]) => seconds >= 30);
  return (
    <article className="card detail-card day-card">
      <div className="section-heading">
        <div className="section-icon violet-icon">
          <Clock size={21} />
        </div>
        <div>
          <h2>Your time today</h2>
          <p>
            {day?.first_seen ? `Since ${timeLabel(day.first_seen)}` : 'itor counts your time while this PC is on.'}
            {day?.demo ? ' · includes a demo morning' : ''}
          </p>
        </div>
        <Badge tone={state.tone} dot>
          {down ? 'Not measured' : state.label}
        </Badge>
      </div>
      <div className="time-numbers">
        <div className="time-number">
          <span className="eyebrow">Active</span>
          <strong>{duration(day?.active_seconds)}</strong>
        </div>
        <div className="time-number lost">
          <span className="eyebrow">Lost to tools</span>
          <strong>{duration(day?.lost_seconds)}</strong>
        </div>
        <div className="time-number">
          <span className="eyebrow">Idle</span>
          <strong>{duration(day?.idle_seconds)}</strong>
        </div>
        <div className="time-number paid">
          <span className="eyebrow">Hours to pay</span>
          <strong>{duration(day?.paid_seconds_total)}</strong>
        </div>
      </div>
      <TimeBar active={day?.active_seconds ?? 0} lost={day?.lost_seconds ?? 0} idle={day?.idle_seconds ?? 0} />
      <p className="muted small">
        Active = mouse or keyboard used in the last 2 minutes. Lost = you were working but a tool got in the way.
        Hours to pay = active + lost.
      </p>
      {causes.length > 0 && (
        <ul className="cause-list">
          {causes.map(([cause, seconds]) => (
            <li key={cause}>
              <span>{causeLabel(cause)}</span>
              <strong>{duration(seconds)}</strong>
            </li>
          ))}
          {frozen.map(([app, seconds]) => (
            <li key={app} className="muted">
              <span>Frozen: {app}</span>
              <strong>{duration(seconds)}</strong>
            </li>
          ))}
        </ul>
      )}
      <div className="button-row">
        <button
          className={`button ${day?.blocked ? 'primary' : 'secondary'}`}
          disabled={down || busy}
          onClick={() => onBlocked(!day?.blocked)}
        >
          {busy ? <Spinner /> : <Hand size={17} />}
          {day?.blocked ? "I'm not blocked anymore" : "I'm blocked"}
        </button>
        {day?.blocked && <span className="muted small">This time counts as lost because of tools, not idle.</span>}
      </div>
    </article>
  );
}

export function ManagerView({ day, company }: { day?: WorkDayView; company?: CompanyStatus }) {
  let sent = 'Not connected to a company server.';
  if (company?.configured) {
    if (company.pending > 0) sent = `${company.pending} report(s) waiting. They will be sent when the connection is back.`;
    else if (company.last_sent_at) sent = `Last sent at ${timeLabel(company.last_sent_at)}.`;
    else sent = 'Will be sent in about a minute.';
  }
  return (
    <article className="card detail-card manager-card">
      <div className="section-heading">
        <div className="section-icon">
          <Eye size={21} />
        </div>
        <div>
          <h2>What your manager sees</h2>
          <p>The exact same numbers as you. Nothing more.</p>
        </div>
      </div>
      <dl className="approval-details">
        <div>
          <dt>Name</dt>
          <dd>{company?.employee ?? day?.employee ?? '—'}</dd>
        </div>
        <div>
          <dt>Active · Lost · Idle</dt>
          <dd>
            {duration(day?.active_seconds)} · {duration(day?.lost_seconds)} · {duration(day?.idle_seconds)}
          </dd>
        </div>
        <div>
          <dt>Hours to pay</dt>
          <dd>{duration(day?.paid_seconds_total)}</dd>
        </div>
        <div>
          <dt>Sent to</dt>
          <dd>Your company only. Never Nexthink. {sent}</dd>
        </div>
      </dl>
      <p className="muted small">
        Never collected: what you type, screenshots, websites, app usage. Only &quot;mouse or keyboard used or not&quot;
        and the name of an app when it freezes.
      </p>
    </article>
  );
}

export function OfflineHelp({
  connectivity,
  incident,
  fixes,
  planning,
  onAsk,
  onFix,
  always = false,
}: {
  connectivity?: Connectivity;
  incident?: Incident | null;
  fixes?: Fix[];
  planning?: string;
  onAsk: () => void;
  onFix: (fix: Fix) => void;
  always?: boolean;
}) {
  const offline = Boolean(
    connectivity &&
      (connectivity.offline_rescue ||
        connectivity.simulated_cloud_outage ||
        ['disconnected', 'unreachable'].includes(connectivity.internet.state)),
  );
  if (!offline && !always) return null;
  return (
    <article className={`card detail-card ${offline ? 'offline-card' : ''}`}>
      <div className="section-heading">
        <div className={`section-icon ${offline ? 'amber-icon' : 'violet-icon'}`}>
          {offline ? <WifiOff size={21} /> : <LifeBuoy size={21} />}
        </div>
        <div>
          <h2>{offline ? "You're offline. itor keeps helping." : 'Quick fixes'}</h2>
          <p>
            {offline
              ? 'The local AI works without internet. itor writes down what happens and sends it to IT when the connection is back.'
              : 'Safe fixes. Each one shows its command and runs only after you approve.'}
          </p>
        </div>
        {offline && <Badge tone="amber" dot>Offline mode</Badge>}
      </div>
      {offline && (
        <div className="button-row">
          <button className="button primary" onClick={onAsk}>
            <LifeBuoy size={17} />
            Ask the local helper
          </button>
        </div>
      )}
      <ul className="provider-list compact">
        {(fixes ?? []).map((fix) => (
          <li key={fix.id}>
            <div>
              <strong>{fix.title}</strong>
              <p className="muted small">{fix.what_it_does}</p>
            </div>
            <button
              className="button secondary"
              disabled={!fix.supported || Boolean(planning)}
              title={fix.supported ? fix.command : 'Only on Windows'}
              onClick={() => onFix(fix)}
            >
              {planning === fix.id ? <Spinner /> : <Wrench size={16} />}
              {fix.supported ? 'Fix it' : 'Windows only'}
            </button>
          </li>
        ))}
      </ul>
      {incident && (
        <div className="evidence-block">
          <span className="eyebrow">Outage log · started {timeLabel(incident.started_at)}</span>
          <ul>
            <li>Not working: {incident.what_failed.join(', ') || 'checking…'}</li>
            {incident.help_given.map((item) => (
              <li key={item}>Help: {item}</li>
            ))}
            {incident.fixes.map((item, index) => (
              <li key={`${item}-${index}`}>Fix: {item}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

export function TeamView({
  team,
  company,
  sending,
  onSend,
  stale,
}: {
  team?: Team;
  company?: CompanyStatus;
  sending: boolean;
  onSend: () => void;
  stale: boolean;
}) {
  const causes = Object.entries(team?.lost_by_cause ?? {}).sort((a, b) => b[1] - a[1]);
  return (
    <>
      <article className="card detail-card">
        <div className="section-heading">
          <div className="section-icon violet-icon">
            <Trophy size={21} />
          </div>
          <div>
            <h2>Team ranking · today</h2>
            <p>Ranked by active time. Data stays inside the company. Never sent to Nexthink.</p>
          </div>
          <button className="button secondary" onClick={onSend} disabled={sending || stale}>
            {sending ? <Spinner /> : <Send size={16} />}
            Send my day now
          </button>
        </div>
        {company && company.pending > 0 && (
          <Notice kind="neutral">
            {company.pending} report(s) are waiting on this PC. They will be sent when the connection is back.
          </Notice>
        )}
        <div className="table-wrap">
          <table className="team-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Employee</th>
                <th>Active</th>
                <th>Lost to tools</th>
                <th>Idle</th>
                <th>Hours to pay</th>
                <th>Active share</th>
              </tr>
            </thead>
            <tbody>
              {(team?.rows ?? []).map((row) => (
                <tr key={row.employee} className={row.employee === company?.employee ? 'me' : ''}>
                  <td>{row.rank}</td>
                  <td>
                    {row.employee}
                    {row.employee === company?.employee && <Badge tone="violet">You</Badge>}
                  </td>
                  <td>{duration(row.active_seconds)}</td>
                  <td className={row.lost_seconds > 1800 ? 'warn' : ''}>{duration(row.lost_seconds)}</td>
                  <td>{duration(row.idle_seconds)}</td>
                  <td>
                    <strong>{duration(row.paid_seconds_total)}</strong>
                  </td>
                  <td>
                    <span className="share-bar">
                      <span style={{ width: `${Math.round(row.active_share * 100)}%` }} />
                    </span>
                    {Math.round(row.active_share * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!team?.rows.length && <p className="muted">{stale ? 'Unavailable.' : 'No reports yet today.'}</p>}
      </article>
      <div className="dashboard-grid dashboard-body">
        <article className="card detail-card">
          <div className="section-heading">
            <div className="section-icon amber-icon">
              <CircleAlert size={21} />
            </div>
            <div>
              <h2>Time the team lost to tools</h2>
              <p>Total today: {duration(team?.total_lost_seconds)}. This is what IT can fix.</p>
            </div>
          </div>
          <ul className="cause-list">
            {causes.map(([cause, seconds]) => (
              <li key={cause}>
                <span>{causeLabel(cause)}</span>
                <strong>{duration(seconds)}</strong>
              </li>
            ))}
          </ul>
        </article>
        <article className="card detail-card">
          <div className="section-heading">
            <div className="section-icon">
              <WifiOff size={21} />
            </div>
            <div>
              <h2>Outage logs received</h2>
              <p>Written offline by itor, sent when the connection came back.</p>
            </div>
          </div>
          <ul className="event-list">
            {(team?.recent_incidents ?? []).map((item) => (
              <li key={item.id}>
                <span className="mini-icon">
                  <WifiOff size={16} />
                </span>
                <div>
                  <strong>
                    {item.employee} · {duration(item.duration_seconds)}
                    {item.simulated ? ' (demo)' : ''}
                  </strong>
                  <p>{item.what_failed.join(', ') || 'Connection lost'}</p>
                </div>
                <span>{timeLabel(item.started_at)}</span>
              </li>
            ))}
          </ul>
          {!team?.recent_incidents.length && <p className="muted">No outage logs yet.</p>}
        </article>
      </div>
    </>
  );
}

const noticeKey = 'itor-notice-seen';
const readSeen = () => {
  try {
    return window.localStorage.getItem(noticeKey) === '1';
  } catch {
    return false;
  }
};

export function FirstLaunchNotice() {
  const stored = useSyncExternalStore(
    () => () => undefined,
    readSeen,
    () => true,
  );
  const [closed, setClosed] = useState(false);
  if (stored || closed) return null;
  return (
    <Notice kind="neutral">
      <div className="section-heading">
        <div className="section-icon violet-icon">
          <ShieldCheck size={21} />
        </div>
        <div>
          <h2>itor counts your working time</h2>
          <p>
            Measured: whether the mouse or keyboard was used (active / idle), and time lost because of tools
            (internet down, PC overloaded, frozen app). Never measured: what you type, screenshots, websites.
            Your manager sees exactly what you see on this page, inside the company only.
          </p>
        </div>
      </div>
      <div className="button-row">
        <button
          className="button primary"
          onClick={() => {
            try {
              window.localStorage.setItem(noticeKey, '1');
            } catch {
              /* private window: just hide it for now */
            }
            setClosed(true);
          }}
        >
          Got it
        </button>
      </div>
    </Notice>
  );
}
