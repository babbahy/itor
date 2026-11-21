import { expect, it } from 'vitest';
import { statusSchema, teamSchema, workDayViewSchema } from '../lib/api';
import {
  actionPending,
  causeLabel,
  currentReadiness,
  duration,
  providerLabel,
} from '../lib/presentation';
import {
  explanation,
  readinessReport,
  statusReport,
  team,
  workDay,
} from './fixtures';

it('formats working time and reads the time clock', () => {
  expect(duration(45 * 60)).toBe('45 min');
  expect(duration(2 * 3600 + 5 * 60)).toBe('2h 05');
  expect(duration(undefined)).toBe('—');
  expect(causeLabel('offline')).toBe('Internet or cloud down');
  expect(workDayViewSchema.parse(workDay()).paid_seconds_total).toBe(3 * 3600 + 15 * 60);
  expect(teamSchema.parse(team()).rows[0].rank).toBe(1);
});

it('says which AI answered', () => {
  expect(providerLabel({ ...explanation(true), provider: 'claude' })).toBe('Claude · online');
  expect(providerLabel(explanation(true))).toBe('Simple rules · works offline');
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

it('polls only approved operations that are still in flight', () => {
  expect(actionPending('awaiting_approval')).toBe(false);
  expect(actionPending('verifying')).toBe(true);
  expect(actionPending('failed')).toBe(false);
  expect(actionPending('succeeded')).toBe(false);
});
