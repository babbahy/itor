import { expect, test, type Page } from '@playwright/test';
import type { Readiness } from '../lib/api';
import {
  approval,
  connectivity,
  explanation,
  makeMeeting,
  readinessReport,
  sample,
  statusReport,
} from './fixtures';

type Scenario = {
  state?: Readiness['readiness'];
  agentDown?: boolean;
  ollama?: boolean;
  offline?: boolean;
  failAction?: boolean;
};

async function stubAgent(page: Page, options: Scenario = {}) {
  const meeting = makeMeeting(Date.now());
  const scheduled = [meeting, makeMeeting(Date.now(), 80)];
  let state = options.state ?? 'ready';
  let simulated = false;
  let actionPolls = 0;
  let approved = false;
  await page.route('**/api/**', async (route) => {
    const endpoint = new URL(route.request().url()).pathname.slice(5);
    if (options.agentDown)
      return route.fulfill({
        status: 503,
        json: { detail: 'Agent unreachable' },
      });
    const timestamp = new Date().toISOString();
    const connection = {
      ollama: options.ollama,
      offline: options.offline,
      simulated,
    };
    if (endpoint === 'status')
      return route.fulfill({
        json: statusReport(connection, state === 'attention'),
      });
    if (endpoint === 'device/readiness')
      return route.fulfill({ json: readinessReport(state) });
    if (endpoint === 'device/history')
      return route.fulfill({ json: [sample(), sample(state === 'attention')] });
    if (endpoint === 'meetings' && route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      const manual = {
        ...meeting,
        ...body,
        id: 'manual-meeting',
        source: 'manual',
        end_at: new Date(
          Date.parse(body.start_at) + body.duration_minutes * 60_000,
        ).toISOString(),
      };
      scheduled.push(manual);
      return route.fulfill({ json: manual, status: 201 });
    }
    if (endpoint === 'meetings') return route.fulfill({ json: scheduled });
    if (endpoint === 'activity') return route.fulfill({ json: [] });
    if (endpoint === 'preflight')
      return route.fulfill({
        json: {
          ...readinessReport(state),
          id: 'session',
          meeting_id: meeting.id,
          started_at: timestamp,
          completed_at: timestamp,
          status: 'completed',
        },
      });
    if (endpoint === 'diagnose' || endpoint === 'diagnosis/chat')
      return route.fulfill({ json: explanation(!options.ollama) });
    if (endpoint === 'demo/start') {
      state = 'attention';
      return route.fulfill({ json: { active: true } });
    }
    if (endpoint === 'demo/cloud') {
      simulated = route.request().postDataJSON().enabled;
      return route.fulfill({
        json: connectivity({ ...connection, simulated }),
      });
    }
    if (endpoint === 'connectivity/check')
      return route.fulfill({ json: connectivity(connection) });
    if (endpoint === 'actions/plan')
      return route.fulfill({ json: approval('awaiting_approval') });
    if (endpoint === 'actions/action/cancel')
      return route.fulfill({ json: approval('canceled') });
    if (endpoint === 'actions/action/approve') {
      expect(route.request().postDataJSON()).toEqual({
        approval_token: 'test-approval-token',
        approved: true,
      });
      approved = true;
      return route.fulfill({ json: approval('verifying'), status: 202 });
    }
    if (endpoint === 'actions/action') {
      if (++actionPolls < 3)
        return route.fulfill({ json: approval('verifying') });
      if (!options.failAction) state = 'ready';
      return route.fulfill({
        json: approval(options.failAction ? 'failed' : 'succeeded'),
      });
    }
    return route.fulfill({
      status: 404,
      json: { detail: 'Fixture route unavailable' },
    });
  });
  return () => approved;
}

test('prepares a healthy meeting and distinguishes demo meeting from live readings', async ({
  page,
}) => {
  await stubAgent(page, { ollama: true });
  await page.goto('/');
  const hero = page.getByRole('article', { name: 'Next meeting' });
  await expect(
    hero.getByRole('heading', { name: 'Product Team Weekly' }),
  ).toBeVisible();
  await expect(hero.getByText('Demo meeting', { exact: true })).toBeVisible();
  await expect(
    page.getByText('Live readings from your local agent'),
  ).toBeVisible();
  await expect(
    hero.getByRole('link', { name: 'Join meeting' }),
  ).toHaveAttribute('href', 'https://meet.example/session');
  await hero.getByRole('button', { name: 'Prepare my meeting' }).click();
  await expect(
    page.getByRole('heading', { name: 'Meeting checklist' }),
  ).toBeVisible();
  await expect(
    page.getByText('Your device looks ready for this meeting.'),
  ).toBeVisible();
  await expect(
    page.getByText('Local AI available', { exact: true }),
  ).toBeVisible();
});

test('shows unknown readiness and handles a disconnected backend', async ({
  page,
}) => {
  await stubAgent(page, { state: 'unknown' });
  await page.goto('/');
  await expect(
    page.getByText('Checks incomplete', { exact: true }),
  ).toBeVisible();
  await page.unroute('**/api/**');
  await stubAgent(page, { agentDown: true });
  await expect(
    page.getByRole('alert').getByText('Device agent unavailable'),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Prepare my meeting' }),
  ).toBeDisabled();
});

test('requires approval and displays verified before and after measurements', async ({
  page,
}) => {
  const isApproved = await stubAgent(page, {
    state: 'attention',
    ollama: false,
  });
  await page.goto('/');
  await expect(
    page.getByText('Attention needed', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Local AI unavailable', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Explain this finding' }).click();
  await expect(
    page.getByText('Rules-based explanation', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Fix this for me' }).click();
  const dialog = page.getByRole('dialog', { name: 'Approve local action' });
  await expect(
    dialog.getByText('Stop the temporary workload created by Spark Ready.'),
  ).toBeVisible();
  expect(isApproved()).toBe(false);
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toHaveCount(0);
  expect(isApproved()).toBe(false);
  await page.getByRole('button', { name: 'Fix this for me' }).click();
  await dialog
    .getByRole('button', { name: 'Approve and stop workload' })
    .click();
  await expect(
    page.getByRole('heading', {
      name: 'Verifying process exit and measuring again',
    }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Workload stopped and verified' }),
  ).toBeVisible();
  await expect(page.getByText('42%', { exact: true })).toBeVisible();
  await expect(page.getByText('0%', { exact: true })).toBeVisible();
});

test('keeps action failure visible and never reports it as verified', async ({
  page,
}) => {
  await stubAgent(page, { state: 'attention', failAction: true });
  await page.goto('/');
  await page.getByRole('button', { name: 'Fix this for me' }).click();
  await page.getByRole('button', { name: 'Approve and stop workload' }).click();
  await expect(page.getByText('Action failed', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Workload stopped and verified' }),
  ).toHaveCount(0);
});

test('keeps meeting and local AI available offline and withholds online meeting launch', async ({
  page,
}) => {
  await stubAgent(page, { offline: true, ollama: true });
  await page.goto('/');
  await expect(
    page.getByText(
      'Cloud services are unavailable. Local diagnostics are still running.',
    ),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Product Team Weekly' }),
  ).toBeVisible();
  await expect(
    page.getByText('Local AI available', { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Join meeting' })).toHaveCount(0);
  await expect(page.getByText('Join link unavailable offline')).toBeVisible();
  await page.getByRole('button', { name: 'Prepare my meeting' }).click();
  await expect(
    page.getByRole('heading', { name: 'Meeting checklist' }),
  ).toBeVisible();
  await page
    .locator('.offline-banner')
    .getByRole('button', { name: 'Investigate connection' })
    .click();
  const diagnostics = page.getByRole('dialog', {
    name: 'Investigate connection',
  });
  await expect(
    diagnostics.getByText('Internet connectivity', { exact: true }),
  ).toBeVisible();
  await expect(
    diagnostics.getByText(/Cloud context is stale. Last updated/),
  ).toBeVisible();
});

test('adds a local meeting through the accessible form', async ({ page }) => {
  await stubAgent(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Add meeting', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Add a meeting' });
  await dialog.getByLabel('Meeting title').fill('Local planning meeting');
  await dialog.getByLabel('Date', { exact: true }).fill('2040-04-03');
  await dialog.getByLabel('Time', { exact: true }).fill('14:45');
  await dialog.getByLabel('Join URL').fill('https://meet.example/plan');
  await dialog.getByRole('button', { name: 'Add meeting' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByText('Local planning meeting', { exact: true }),
  ).toBeVisible();
});

test('simulates a cloud outage without disabling local or meeting services', async ({
  page,
}) => {
  await stubAgent(page, { ollama: true });
  await page.goto('/');
  await page.getByRole('button', { name: 'Demo controls' }).click();
  const dialog = page.getByRole('dialog', { name: 'Demo controls' });
  await dialog
    .getByRole('button', { name: 'Simulate cloud unavailability' })
    .click();
  await expect(dialog.getByText('Outage simulated')).toBeVisible();
  await dialog.getByRole('button', { name: 'Close dialog' }).click();
  await expect(
    page.getByText('Simulated service outage', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Local AI available', { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Join meeting' })).toBeVisible();
  await page.getByRole('button', { name: 'Demo controls' }).click();
  await dialog.getByRole('button', { name: 'Restore cloud adapter' }).click();
  await dialog.getByRole('button', { name: 'Close dialog' }).click();
  await expect(
    page.getByText('Simulated service outage', { exact: true }),
  ).toHaveCount(0);
});
