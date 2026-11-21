import { describe, expect, it } from 'vitest';
import { connectivitySchema, meetingSchema, statusSchema } from '../lib/api';
import {
  actionPending,
  currentReadiness,
  meetingCountdown,
  safeJoin,
  upcomingMeetings,
} from '../lib/presentation';
import {
  connectivity,
  makeMeeting,
  readinessReport,
  statusReport,
} from './fixtures';

const now = Date.parse('2026-11-21T14:00:00Z');

it('validates time-zone-aware meeting data and sorts upcoming meetings', () => {
  const early = makeMeeting(now, 12);
  const late = makeMeeting(now, 90);
  const finished = makeMeeting(now, -31);
  expect(meetingSchema.parse(early)).toEqual(early);
  expect(
    meetingSchema.safeParse({ ...early, start_at: '2026-11-21T14:12:00' })
      .success,
  ).toBe(false);
  expect(upcomingMeetings([late, finished, early], now)).toEqual([early, late]);
  expect(meetingCountdown(early, now)).toBe('In 12 min');
});

it('makes missing, checking, and disconnected readings explicit', () => {
  expect(currentReadiness(undefined, false, false)).toBe('unknown');
  expect(currentReadiness(readinessReport('ready'), false, false)).toBe(
    'ready',
  );
  expect(currentReadiness(readinessReport('ready'), true, false)).toBe(
    'unknown',
  );
  expect(currentReadiness(readinessReport('attention'), false, true)).toBe(
    'checking',
  );
  expect(currentReadiness(readinessReport('attention'), false, false)).toBe(
    'attention',
  );
});

it('keeps local services independent when an external probe fails', () => {
  const report = statusSchema.parse(statusReport({ offline: true }));
  expect(report.connectivity.internet.state).toBe('unreachable');
  expect(report.connectivity.agent.state).toBe('connected');
  expect(report.connectivity.ollama.state).toBe('connected');
});

describe('meeting launch', () => {
  const url = 'https://meet.example/session';
  it('accepts HTTPS links when network checks are available or unconfigured', () => {
    expect(safeJoin(url)).toBe(url);
    expect(
      safeJoin(
        url,
        connectivitySchema.parse(connectivity({ simulated: true })),
      ),
    ).toBe(url);
  });
  it('blocks launch during actual loss of network connectivity', () => {
    const interfaceAbsent = connectivitySchema.parse(
      connectivity({ disconnected: true }),
    );
    const internetUnreachable = connectivitySchema.parse(
      connectivity({ offline: true }),
    );
    expect(safeJoin(url, interfaceAbsent)).toBeNull();
    expect(safeJoin(url, internetUnreachable)).toBeNull();
    expect(safeJoin(url, undefined, true)).toBeNull();
  });
  it.each([
    'javascript:alert(1)',
    'http://meet.example',
    'https://person:secret@meet.example',
    'invalid',
  ])('rejects unsafe link %s', (link) => expect(safeJoin(link)).toBeNull());
});

it('polls only approved operations that are still in flight', () => {
  expect(actionPending('awaiting_approval')).toBe(false);
  expect(actionPending('verifying')).toBe(true);
  expect(actionPending('failed')).toBe(false);
  expect(actionPending('succeeded')).toBe(false);
});
