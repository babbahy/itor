import {
  Activity,
  Clock,
  House,
  Gauge,
  Settings,
  ShieldCheck,
  Users,
} from 'lucide-react';
import type { Action, Diagnosis, Readiness, ServiceStatus } from './api';

export const sections = [
  { href: '/', label: 'Home', icon: House },
  { href: '/day', label: 'My day', icon: Clock },
  { href: '/readiness', label: 'My PC', icon: Gauge },
  { href: '/activity', label: 'Log', icon: Activity },
  { href: '/team', label: 'Team', icon: Users },
  { href: '/privacy', label: 'Privacy', icon: ShieldCheck },
  { href: '/settings', label: 'Settings', icon: Settings },
];

type ReadinessState = Readiness['readiness'] | 'checking';
export const readinessCopy: Record<
  ReadinessState,
  { title: string; tone: string; description: string }
> = {
  ready: {
    title: 'Ready',
    tone: 'green',
    description: 'Your PC looks fine. Nothing is slowing you down.',
  },
  attention: {
    title: 'Attention needed',
    tone: 'amber',
    description: 'A device check found something worth reviewing.',
  },
  not_ready: {
    title: 'Not ready',
    tone: 'amber',
    description: 'Something is blocking your work. itor can help.',
  },
  unknown: {
    title: 'Checks incomplete',
    tone: 'muted',
    description: 'Some checks need a current measurement.',
  },
  checking: {
    title: 'Checking',
    tone: 'violet',
    description: 'Collecting current measurements from your device.',
  },
};

export const serviceCopy: Record<
  ServiceStatus['state'],
  { label: string; tone: string }
> = {
  connected: { label: 'Connected', tone: 'green' },
  disconnected: { label: 'Disconnected', tone: 'amber' },
  unreachable: { label: 'Unreachable', tone: 'amber' },
  authentication_error: { label: 'Authentication error', tone: 'amber' },
  degraded: { label: 'Degraded', tone: 'amber' },
  checking: { label: 'Checking', tone: 'violet' },
  unknown: { label: 'Not checked', tone: 'muted' },
  not_configured: { label: 'Not configured', tone: 'muted' },
};

export function currentReadiness(
  readiness: Readiness | undefined,
  agentDown: boolean,
  checking: boolean,
): ReadinessState {
  if (agentDown) return 'unknown';
  if (checking) return 'checking';
  return readiness?.readiness ?? 'unknown';
}

export const actionPending = (status: Action['status']) =>
  ['approved', 'executing', 'verifying'].includes(status);
export const actionable = (findings: Readiness['findings']) =>
  findings.find((finding) =>
    finding.recommended_action_ids.includes('stop_demo_workload'),
  );
export const dateLabel = (
  date: string | number,
  options: Intl.DateTimeFormatOptions,
) => new Intl.DateTimeFormat(undefined, options).format(new Date(date));
export const timeLabel = (date: string | number) =>
  dateLabel(date, { hour: 'numeric', minute: '2-digit' });
export const reading = (value: number | null | undefined, units = '%') =>
  value == null ? '—' : `${Math.round(value)}${units}`;
export const gib = (bytes: number | null | undefined) =>
  bytes == null ? 'Unavailable' : `${(bytes / 2 ** 30).toFixed(1)} GB`;
export const toMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Something went wrong. Try again.';

/** 2h 05m style, for seconds. */
export function duration(seconds: number | null | undefined) {
  if (seconds == null) return '—';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}`;
}

export const causeLabels: Record<string, string> = {
  blocked: "Said \"I'm blocked\"",
  offline: 'Internet or cloud down',
  pc_overloaded: 'PC overloaded',
  frozen_app: 'App not responding',
};
export const causeLabel = (cause: string) => causeLabels[cause] ?? cause;

export function providerLabel(diagnosis: Diagnosis | undefined) {
  if (!diagnosis) return undefined;
  if (diagnosis.provider === 'gemini') return 'Gemini · online';
  if (diagnosis.provider === 'ollama') return `${diagnosis.model ?? 'Qwen'} · Local AI, works offline`;
  return 'Simple rules · works offline';
}
