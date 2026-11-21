'use client';

import {
  Activity as ActivityIcon,
  ChartNoAxesCombined,
  CircleHelp,
  Cpu,
  Database,
  LockKeyhole,
  Plug,
  ShieldCheck,
  Sparkles,
  Wrench,
} from 'lucide-react';
import type { Activity, Connectivity, InsightsData } from '@/lib/api';
import { timeLabel } from '@/lib/presentation';
import { Badge, ServiceBadge, StateBadge } from './ui';

export function EventList({
  events,
  limit,
  stale = false,
}: {
  events: Activity | undefined;
  limit?: number;
  stale?: boolean;
}) {
  if (!events?.length)
    return (
      <div className="empty-state">
        <span className="section-icon">
          <ActivityIcon size={21} />
        </span>
        <p>
          {stale
            ? 'Activity is unavailable while the device agent is disconnected.'
            : 'Preflight checks and approved actions will appear here.'}
        </p>
      </div>
    );
  return (
    <ul className="event-list">
      {events.slice(0, limit ?? events.length).map((event) => (
        <li key={event.id}>
          <span className="mini-icon">
            <ActivityIcon size={16} />
          </span>
          <div>
            <strong>{event.title}</strong>
            <p>{event.detail}</p>
          </div>
          <span>{timeLabel(event.created_at)}</span>
        </li>
      ))}
    </ul>
  );
}

export function Insights({
  insights,
  stale,
}: {
  insights?: InsightsData;
  stale: boolean;
}) {
  const latestReadiness = stale ? undefined : insights?.recent_readiness;
  let latestSummary = 'Loading the saved result.';
  if (stale) latestSummary = 'The latest result is unavailable.';
  else if (latestReadiness) latestSummary = 'Most recent completed check on this device.';
  else if (insights) latestSummary = 'Run a preflight to record your first result.';
  return (
    <>
      <div className="insights-grid">
        {[
          {
            label: 'Preflights completed',
            value: insights?.preflights,
            icon: ShieldCheck,
          },
          {
            label: 'Device findings',
            value: insights?.findings,
            icon: CircleHelp,
          },
          {
            label: 'Verified actions',
            value: insights?.verified_actions,
            icon: Wrench,
          },
        ].map(({ label, value, icon: Icon }) => (
          <article className="card detail-card insight" key={label}>
            <div className="section-icon violet-icon">
              <Icon size={21} />
            </div>
            <h2>{label}</h2>
            <strong>{stale ? '—' : (value ?? '—')}</strong>
          </article>
        ))}
      </div>
      <article className="card detail-card">
        <div className="section-heading">
          <div className="section-icon">
            <ChartNoAxesCombined size={22} />
          </div>
          <div>
            <h2>Latest preflight</h2>
            <p>{latestSummary}</p>
          </div>
          {latestReadiness && <StateBadge state={latestReadiness} />}
        </div>
      </article>
    </>
  );
}

export function Privacy({
  privacy,
  connectivity,
  onClear,
  down,
}: {
  privacy?: {
    retention_days?: number;
    model?: string | null;
    inference_location?: string;
    telemetry_sources?: string[];
    stored_data?: string[];
    external_connections?: string[];
    sync?: {
      state: string;
      pending_events: number;
      failed_events: number;
      last_sync_at?: string | null;
    };
  };
  connectivity?: Connectivity;
  onClear: () => void;
  down: boolean;
}) {
  const facts = [
    {
      icon: Sparkles,
      label: 'AI inference',
      body:
        privacy?.inference_location ??
        'On this device through Ollama. A local rules engine is available as a fallback.',
      value: privacy?.model ?? 'Model unknown',
    },
    {
      icon: Cpu,
      label: 'Device measurements',
      body:
        privacy?.telemetry_sources?.join(' · ') ??
        'System CPU, available memory, disk capacity, network interface state, and itor workload metrics.',
      value: 'Local agent',
    },
    {
      icon: Database,
      label: 'Local storage',
      body:
        privacy?.stored_data?.join(' · ') ??
        'Meetings and minimal operational records are stored locally in SQLite.',
      value: privacy?.retention_days
        ? `${privacy.retention_days} day history retention`
        : 'Retention unavailable',
    },
    {
      icon: Plug,
      label: 'External connections',
      body: privacy?.external_connections?.length
        ? privacy.external_connections.join(' · ')
        : 'Connectivity probes are limited to approved endpoints. Local measurements are processed on this device.',
      value: privacy?.sync?.state
        ? `Sync ${privacy.sync.state.replaceAll('_', ' ')}`
        : 'Sync inactive',
    },
  ];
  return (
    <>
      <article className="card detail-card privacy-lead">
        <div className="section-icon green-icon">
          <LockKeyhole size={23} />
        </div>
        <div>
          <h2>Private by design</h2>
          <p>
            itor uses aggregate device readings and the meetings you add.
            Your files, screen, and browsing history stay outside its data
            collection.
          </p>
        </div>
      </article>
      <div className="privacy-grid">
        {facts.map(({ icon: Icon, label, body, value }) => (
          <article className="card detail-card" key={label}>
            <div className="section-heading">
              <div className="section-icon">
                <Icon size={19} />
              </div>
              <h2>{label}</h2>
            </div>
            <p>{body}</p>
            <Badge>{value}</Badge>
            {label === 'External connections' &&
              privacy?.sync?.last_sync_at && (
                <p>Last sync {timeLabel(privacy.sync.last_sync_at)}</p>
              )}
          </article>
        ))}
      </div>
      <article className="card detail-card integration-card">
        <div>
          <h2>Manage local history</h2>
          <p>
            Clear the retained activity, preflight, and action records on this
            device.
          </p>
        </div>
        <button className="button secondary" onClick={onClear} disabled={down}>
          Clear local history
        </button>
      </article>
      <article className="card detail-card integration-card">
        <div>
          <h2>Nexthink connection</h2>
          <p>
            Provider health is reported independently from local AI and device
            checks.
          </p>
        </div>
        <ServiceBadge service={connectivity?.nexthink} />
      </article>
    </>
  );
}

export function Settings({
  connectivity,
  model,
  onNetwork,
  onDemo,
}: {
  connectivity?: Connectivity;
  model?: string | null;
  onNetwork: () => void;
  onDemo: () => void;
}) {
  return (
    <>
      <article className="card detail-card">
        <div className="section-heading">
          <div className="section-icon violet-icon">
            <Plug size={21} />
          </div>
          <div>
            <h2>Providers</h2>
            <p>itor is a local prototype for the Nexthink ecosystem.</p>
          </div>
        </div>
        <ul className="provider-list">
          <li>
            <div>
              <strong>Device telemetry</strong>
              <p>
                Live CPU, memory, disk, and application-owned workload readings.
              </p>
            </div>
            <Badge>Local device</Badge>
          </li>
          <li>
            <div>
              <strong>Diagnosis</strong>
              <p>
                {model
                  ? `${model} via Ollama, with local readiness rules.`
                  : 'Ollama with local readiness rules.'}
              </p>
            </div>
            <ServiceBadge
              service={connectivity?.ollama}
              connectedLabel="Available"
            />
          </li>
          <li>
            <div>
              <strong>Remediation</strong>
              <p>Approved, scoped actions with measured verification.</p>
            </div>
            <Badge>Local safe actions</Badge>
          </li>
          <li>
            <div>
              <strong>Nexthink integration</strong>
              <p>
                Future providers for NQL telemetry, governed Remote Actions, and
                authenticated Spark handoff.
              </p>
            </div>
            <ServiceBadge service={connectivity?.nexthink} />
          </li>
        </ul>
      </article>
      <article className="card detail-card integration-card">
        <div>
          <h2>Connection diagnostics</h2>
          <p>Review interface, routing, DNS, internet, and provider checks.</p>
        </div>
        <button className="button secondary" onClick={onNetwork}>
          Investigate connection
        </button>
      </article>
      <article className="card detail-card integration-card">
        <div>
          <h2>Presenter tools</h2>
          <p>Manage the sample schedule and bounded demonstration workload.</p>
        </div>
        <button className="button secondary" onClick={onDemo}>
          Open demo controls
        </button>
      </article>
    </>
  );
}
