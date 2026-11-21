'use client';

import { CircleHelp, Plug, Radar, Wifi, WifiOff } from 'lucide-react';
import type { Connectivity, Diagnosis } from '@/lib/api';
import { providerLabel, timeLabel } from '@/lib/presentation';
import { Badge, Notice, ServiceBadge, Spinner } from './ui';

export function OfflineBanner({
  connectivity,
  onOpen,
}: {
  connectivity?: Connectivity;
  onOpen: () => void;
}) {
  if (!connectivity?.offline_rescue && !connectivity?.simulated_cloud_outage)
    return null;
  return (
    <div className="offline-banner" role="status">
      <WifiOff size={22} />
      <div>
        <strong>
          {connectivity.simulated_cloud_outage
            ? 'Simulated service outage'
            : 'Offline Rescue'}
        </strong>
        <p>
          Cloud services are unavailable. Local diagnostics are still running.
        </p>
      </div>
      <button className="button secondary" onClick={onOpen}>
        Investigate connection
      </button>
    </div>
  );
}

export function NetworkPanel({
  connectivity,
  down,
  probing,
  error,
  onCheck,
  diagnosis,
  diagnosing,
  diagnosisError,
  onAsk,
}: {
  connectivity?: Connectivity;
  down: boolean;
  probing: boolean;
  error?: string;
  onCheck: () => void;
  diagnosis?: Diagnosis;
  diagnosing: boolean;
  diagnosisError?: string;
  onAsk: (question: string) => void;
}) {
  const services = connectivity
    ? ([
        ['Device agent', connectivity.agent],
        ['Local AI', connectivity.ollama],
        ['Network interface', connectivity.network_interface],
        ['Default route', connectivity.gateway],
        ['DNS resolver', connectivity.dns_resolver],
        ['DNS resolution', connectivity.dns],
        ['Internet connectivity', connectivity.internet],
        ['Nexthink', connectivity.nexthink],
        ...(connectivity.nexthink_reachability?.configured
          ? [
              [
                'Nexthink reachability',
                connectivity.nexthink_reachability,
              ] as const,
            ]
          : []),
        ...(connectivity.nexthink_auth?.configured
          ? [['Nexthink authentication', connectivity.nexthink_auth] as const]
          : []),
      ] as const)
    : [];
  return (
    <div className="network-content">
      <div className="section-heading">
        <div className="section-icon violet-icon">
          <Radar size={21} />
        </div>
        <div>
          <h3>Connection checks</h3>
          <p>
            {connectivity
              ? `Last updated ${timeLabel(connectivity.updated_at)}`
              : 'Waiting for local measurements'}
          </p>
        </div>
      </div>
      {down && (
        <Notice kind="error">The local device agent is unreachable.</Notice>
      )}
      {connectivity?.simulated_cloud_outage && (
        <Badge tone="amber" dot>
          Simulated service outage
        </Badge>
      )}
      {connectivity?.cloud_data_stale && (
        <Notice kind="neutral">
          Cloud context is stale. Last updated{' '}
          {connectivity.cloud_last_updated_at
            ? timeLabel(connectivity.cloud_last_updated_at)
            : 'unavailable'}
          .
        </Notice>
      )}
      <ul className="service-list">
        {services.map(([label, service]) => (
          <li key={label}>
            <div>
              <strong>{label}</strong>
              <p>{service.explanation}</p>
              {service.last_checked_at && (
                <span>
                  Checked {timeLabel(service.last_checked_at)}
                  {service.duration_ms != null
                    ? ` · ${Math.round(service.duration_ms)} ms`
                    : ''}
                </span>
              )}
              {service.state !== 'connected' && service.last_success_at && (
                <span>
                  {' '}
                  · Last success {timeLabel(service.last_success_at)}
                </span>
              )}
            </div>
            <ServiceBadge service={down ? undefined : service} />
          </li>
        ))}
      </ul>
      {error && <Notice kind="error">{error}</Notice>}
      <button
        className="button secondary"
        disabled={down || probing}
        onClick={onCheck}
      >
        {probing ? <Spinner /> : <Wifi size={17} />}
        {probing ? 'Checking connection…' : 'Check connection now'}
      </button>
      <div className="network-question">
        <div className="section-heading">
          <div className="section-icon">
            <CircleHelp size={20} />
          </div>
          <div>
            <h3>Understand the checks</h3>
            <p>Explain the latest measurements using the local agent.</p>
          </div>
        </div>
        <form
          className="question-form"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const question = String(data.get('question')).trim();
            if (question) onAsk(question);
          }}
        >
          <label className="sr-only" htmlFor="network-question">
            Connection question
          </label>
          <input
            id="network-question"
            name="question"
            maxLength={400}
            required
            placeholder="Could this be a DNS issue?"
          />
          <button
            className="button secondary"
            disabled={down || diagnosing}
            type="submit"
          >
            {diagnosing && <Spinner />}Explain
          </button>
        </form>
        {diagnosisError && <Notice kind="error">{diagnosisError}</Notice>}
        {diagnosis && (
          <div className="network-answer" aria-live="polite">
            <Badge tone={diagnosis.provider === 'rules' ? 'muted' : 'violet'}>
              {providerLabel(diagnosis)}
            </Badge>
            <h4>{diagnosis.headline}</h4>
            <p>{diagnosis.explanation}</p>
            {diagnosis.safe_steps.length > 0 && (
              <ul>
                {diagnosis.safe_steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
            )}
            {diagnosis.uncertainty && (
              <p className="muted">{diagnosis.uncertainty}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function AgentUnavailable() {
  return (
    <div className="offline-banner agent-unavailable" role="alert">
      <Plug size={22} />
      <div>
        <strong>Device agent unavailable</strong>
        <p>
          Start the local itor agent. The dashboard reconnects
          automatically.
        </p>
      </div>
    </div>
  );
}
