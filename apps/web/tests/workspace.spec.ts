import { expect, test, type Page } from '@playwright/test';
import type { Readiness } from '../lib/api';
import {
  approval,
  companyStatus,
  connectivity,
  explanation,
  fixRun,
  fixes,
  readinessReport,
  sample,
  statusReport,
  team,
  workDay,
} from './fixtures';

type Scenario = {
  state?: Readiness['readiness'];
  agentDown?: boolean;
  ollama?: boolean;
  offline?: boolean;
  failAction?: boolean;
};

async function stubAgent(page: Page, options: Scenario = {}) {
  let state = options.state ?? 'ready';
  let simulated = false;
  let actionPolls = 0;
  let approved = false;
  let blocked = false;
  let fixApproved = false;
  await page.addInitScript(() => window.localStorage.setItem('itor-notice-seen', '1'));
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
    if (endpoint === 'activity') return route.fulfill({ json: [] });
    if (endpoint === 'worktime/today')
      return route.fulfill({ json: workDay({ blocked, state: blocked ? 'lost' : 'active' }) });
    if (endpoint === 'worktime/blocked') {
      blocked = route.request().postDataJSON().blocked;
      return route.fulfill({ json: workDay({ blocked, state: blocked ? 'lost' : 'active' }) });
    }
    if (endpoint === 'company/status') return route.fulfill({ json: companyStatus });
    if (endpoint === 'company/team') return route.fulfill({ json: team() });
    if (endpoint === 'fixes') return route.fulfill({ json: fixes });
    if (endpoint === 'support/ticket')
      return route.fulfill({
        status: 201,
        json: {
          id: 'ticket',
          employee: 'alex',
          created_at: new Date().toISOString(),
          message: route.request().postDataJSON().message,
          diagnosis: null,
          pc_status: 'ready',
          findings: [],
          connection: ['Connection looks normal'],
          tried: [],
          outage_id: null,
          sent: !options.offline,
        },
      });
    if (endpoint === 'incidents')
      return route.fulfill({ json: { current: null, history: [] } });
    if (endpoint === 'fixes/flush_dns/plan')
      return route.fulfill({ json: fixRun('awaiting_approval'), status: 201 });
    if (endpoint === 'fixes/runs/run/approve') {
      fixApproved = true;
      return route.fulfill({ json: fixRun('succeeded') });
    }
    if (endpoint === 'fixes/runs/run/cancel')
      return route.fulfill({ json: fixRun('canceled') });
    if (endpoint === 'preflight')
      return route.fulfill({
        json: {
          ...readinessReport(state),
          id: 'session',
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
  return { isApproved: () => approved, isFixApproved: () => fixApproved };
}

test('shows my working time and exactly what the manager sees', async ({ page }) => {
  await stubAgent(page, { ollama: true });
  await page.goto('/day');
  await expect(page.getByRole('heading', { name: 'Your time today' })).toBeVisible();
  await expect(page.getByText('Active now', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'What your manager sees' })).toBeVisible();
  await expect(page.getByText('3h 15').first()).toBeVisible();
  await expect(page.getByText('Local AI available', { exact: true })).toBeVisible();
});

test('marks time as blocked', async ({ page }) => {
  await stubAgent(page);
  await page.goto('/day');
  await page.getByRole('button', { name: "I'm blocked" }).click();
  await expect(page.getByText('Losing time to a tool', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: "I'm not blocked anymore" })).toBeVisible();
});

test('shows unknown readiness and handles a disconnected backend', async ({
  page,
}) => {
  await stubAgent(page, { state: 'unknown' });
  await page.goto('/day');
  await expect(
    page.getByText('Checks incomplete', { exact: true }),
  ).toBeVisible();
  await page.unroute('**/api/**');
  await stubAgent(page, { agentDown: true });
  await expect(
    page.getByRole('alert').getByText('Device agent unavailable'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: "I'm blocked" })).toBeDisabled();
});

test('requires approval and displays verified before and after measurements', async ({
  page,
}) => {
  const { isApproved } = await stubAgent(page, {
    state: 'attention',
    ollama: false,
  });
  await page.goto('/day');
  await expect(
    page.getByText('Attention needed', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Explain this finding' }).click();
  await expect(
    page.getByText('Simple rules · works offline', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Fix this for me' }).click();
  const dialog = page.getByRole('dialog', { name: 'Approve local action' });
  await expect(
    dialog.getByText('Stop the temporary workload created by itor.'),
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
    page.getByRole('heading', { name: 'Workload stopped and verified' }),
  ).toBeVisible();
});

test('keeps action failure visible and never reports it as verified', async ({
  page,
}) => {
  await stubAgent(page, { state: 'attention', failAction: true });
  await page.goto('/day');
  await page.getByRole('button', { name: 'Fix this for me' }).click();
  await page.getByRole('button', { name: 'Approve and stop workload' }).click();
  await expect(page.getByText('Action failed', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Workload stopped and verified' }),
  ).toHaveCount(0);
});

test('offers local help and quick fixes when offline', async ({ page }) => {
  const { isFixApproved } = await stubAgent(page, { offline: true, ollama: true });
  await page.goto('/day');
  await expect(
    page.getByRole('heading', { name: "You're offline. itor keeps helping." }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Fix it' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Approve a quick fix' });
  await expect(dialog.getByText('ipconfig /flushdns')).toBeVisible();
  expect(isFixApproved()).toBe(false);
  await dialog.getByRole('button', { name: 'Approve and run' }).click();
  await expect(dialog.getByText(/Internet before: unreachable/)).toBeVisible();
  expect(isFixApproved()).toBe(true);
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Ask the local helper' }).click();
  await expect(
    page.getByRole('dialog', { name: 'Investigate connection' }),
  ).toBeVisible();
});

test('shows the team ranking', async ({ page }) => {
  await stubAgent(page);
  await page.goto('/team');
  await expect(page.getByRole('heading', { name: 'Team ranking · today' })).toBeVisible();
  const rows = page.locator('.team-table tbody tr');
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1)).toContainText('alex');
  await expect(rows.nth(1)).toContainText('You');
});

test('simulates a cloud outage without disabling local services', async ({
  page,
}) => {
  await stubAgent(page, { ollama: true });
  await page.goto('/day');
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
  await page.getByRole('button', { name: 'Demo controls' }).click();
  await dialog.getByRole('button', { name: 'Restore cloud adapter' }).click();
  await dialog.getByRole('button', { name: 'Close dialog' }).click();
  await expect(
    page.getByText('Simulated service outage', { exact: true }),
  ).toHaveCount(0);
});

test('home shows only the status and two buttons', async ({ page }) => {
  await stubAgent(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Everything looks fine' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Fix my problem' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Ask IT' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Your time today' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Fix my problem' }).click();
  await page.getByLabel('What is not working? (optional)').fill('websites do not load');
  await page.getByRole('button', { name: 'Check and fix' }).click();
  await expect(page.getByRole('heading', { name: 'What itor can try' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'See more ›' })).toHaveAttribute('href', '/day');
});

test('asks IT offline and says the ticket will leave later', async ({ page }) => {
  await stubAgent(page, { offline: true });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: "You're offline" })).toBeVisible();
  await page.getByRole('button', { name: 'Ask IT' }).click();
  const dialog = page.getByRole('dialog', { name: 'Ask IT' });
  await dialog.getByLabel('Tell IT what is wrong').fill('VPN does not connect');
  await dialog.getByRole('button', { name: 'Send to IT' }).click();
  await expect(dialog.getByText('Saved. It will be sent when you are back online.')).toBeVisible();
});
