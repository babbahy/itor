import {
  Activity,
  ChartNoAxesCombined,
  Gauge,
  House,
  Settings,
  ShieldCheck,
} from 'lucide-react';
import type {
  Action,
  Connectivity,
  Meeting,
  Readiness,
  ServiceStatus,
} from './api';

export const sections = [
  { href: '/', label: 'Today', icon: House },
  { href: '/readiness', label: 'Device readiness', icon: Gauge },
  { href: '/activity', label: 'Activity', icon: Activity },
  { href: '/insights', label: 'Insights', icon: ChartNoAxesCombined },
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
    description: 'Your device looks ready for this meeting.',
  },
  attention: {
    title: 'Attention needed',
    tone: 'amber',
    description: 'A device check found something worth reviewing.',
  },
  not_ready: {
    title: 'Not ready',
    tone: 'amber',
    description: 'A critical check needs attention before joining.',
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

export function upcomingMeetings(meetings: Meeting[], now: number) {
  return meetings
    .filter((meeting) => Date.parse(meeting.end_at) > now)
    .sort(
      (first, second) =>
        Date.parse(first.start_at) - Date.parse(second.start_at),
    );
}

export function meetingCountdown(meeting: Meeting, now: number) {
  const minutes = Math.ceil((Date.parse(meeting.start_at) - now) / 60_000);
  if (minutes <= 0) return 'In progress';
  if (minutes < 60) return `In ${minutes} min`;
  if (minutes < 180) return `In ${Math.ceil(minutes / 60)} hr`;
  return dateLabel(meeting.start_at, { month: 'short', day: 'numeric' });
}

export function safeJoin(
  url: string | null | undefined,
  connectivity?: Connectivity,
  agentDown = false,
): string | null {
  if (
    !url ||
    agentDown ||
    connectivity?.internet.state === 'unreachable' ||
    connectivity?.internet.state === 'disconnected' ||
    connectivity?.network_interface.state === 'disconnected'
  )
    return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' && !parsed.username && !parsed.password
      ? parsed.href
      : null;
  } catch {
    return null;
  }
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
