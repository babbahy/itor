'use client';

import {
  Activity as ActivityIcon,
  Check,
  ChevronRight,
  CircleHelp,
  FlaskConical,
  Menu,
  Plus,
  ShieldCheck,
  Sparkles,
  Wifi,
} from 'lucide-react';
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { z } from 'zod';
import {
  actionSchema,
  activitySchema,
  api,
  connectivitySchema,
  diagnosisSchema,
  historySchema,
  insightsSchema,
  meetingSchema,
  meetingsSchema,
  post,
  preflightSchema,
  privacySchema,
  readinessSchema,
  resetSchema,
  statusSchema,
  workloadSchema,
  type Action,
  type Finding,
  type Meeting,
  type Preflight,
} from '@/lib/api';
import {
  actionPending,
  actionable,
  currentReadiness,
  dateLabel,
  safeJoin,
  sections,
  timeLabel,
  toMessage,
  upcomingMeetings,
} from '@/lib/presentation';
import {
  ActionOutcome,
  Checks,
  DiagnosisCard,
  Metrics,
  ReadinessCard,
  Workload,
} from './health';
import { DailyTip, MeetingForm, MeetingHero, Upcoming } from './meetings';
import { AgentUnavailable, NetworkPanel, OfflineBanner } from './network';
import { EventList, Insights, Privacy, Settings } from './secondary';
import { Badge, Dialog, Notice, ServiceBadge, Spinner, StateBadge } from './ui';

const subscription = (callback: () => void) => {
  const timer = window.setInterval(callback, 5000);
  return () => window.clearInterval(timer);
};
const browserTime = () => Math.floor(Date.now() / 5000) * 5000;
const serverTime = () => 0;
const stopAction = 'stop_demo_workload';

type DialogName =
  | 'meeting'
  | 'network'
  | 'demo'
  | 'approval'
  | 'history'
  | null;

export function Workspace({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, staleTime: 1500 },
          mutations: { retry: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard>{children}</Dashboard>
    </QueryClientProvider>
  );
}

function Dashboard({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const now = useSyncExternalStore(subscription, browserTime, serverTime);
  const [dialog, setDialog] = useState<DialogName>(null);
  const [menu, setMenu] = useState(false);
  const [session, setSession] = useState<Preflight>();
  const [action, setAction] = useState<Action>();
  const [demoConfirm, setDemoConfirm] = useState<'stop' | 'reset' | null>(null);
  const [approvalError, setApprovalError] = useState<string>();
  const [demoNotice, setDemoNotice] = useState<string>();
  const [announcement, setAnnouncement] = useState<string>();
  const [dialogFinding, setDialogFinding] = useState<Finding>();
  const [audioChecked, setAudioChecked] = useState<Record<string, boolean>>({});
  const busyReview = useRef<HTMLElement>(null);

  const status = useQuery({
    queryKey: ['status'],
    queryFn: () => api(statusSchema, 'status'),
    refetchInterval: 2500,
  });
  const readiness = useQuery({
    queryKey: ['readiness'],
    queryFn: () => api(readinessSchema, 'device/readiness'),
    refetchInterval: 2500,
  });
  const history = useQuery({
    queryKey: ['history'],
    queryFn: () => api(historySchema, 'device/history'),
    refetchInterval: 4500,
  });
  const meetings = useQuery({
    queryKey: ['meetings'],
    queryFn: () => api(meetingsSchema, 'meetings'),
    refetchInterval: 30_000,
  });
  const events = useQuery({
    queryKey: ['activity'],
    queryFn: () => api(activitySchema, 'activity'),
    refetchInterval: 8000,
  });
  const insights = useQuery({
    queryKey: ['insights'],
    queryFn: () => api(insightsSchema, 'insights'),
    enabled: path === '/insights',
  });
  const privacy = useQuery({
    queryKey: ['privacy'],
    queryFn: () => api(privacySchema, 'privacy'),
    enabled: path === '/privacy',
  });
  const liveAction = useQuery({
    queryKey: ['action', action?.id],
    queryFn: () => api(actionSchema, `actions/${action?.id}`),
    enabled: Boolean(action && actionPending(action.status)),
    refetchInterval: ({ state }) =>
      state.data && !actionPending(state.data.status) ? false : 500,
  });
  const currentAction = liveAction.data ?? action;
  const isFixing = Boolean(
    currentAction && actionPending(currentAction.status),
  );
  const actionFinished =
    liveAction.data && !actionPending(liveAction.data.status);
  useEffect(() => {
    if (actionFinished)
      void client.invalidateQueries({
        predicate: ({ queryKey }) =>
          ['readiness', 'history', 'status', 'activity', 'insights'].includes(
            String(queryKey[0]),
          ),
      });
  }, [actionFinished, client]);
  const connectivity = status.data?.connectivity;
  const down = status.isError;
  const sorted = upcomingMeetings(meetings.data ?? [], now);
  const nextMeeting = sorted[0];
  const sessionForMeeting =
    session?.meeting_id === nextMeeting?.id ? session : undefined;
  const finding =
    !down &&
    (actionable(readiness.data?.findings ?? []) ?? readiness.data?.findings[0]);
  const join = safeJoin(nextMeeting?.join_url, connectivity, down);
  const joinBlocked = Boolean(nextMeeting?.join_url && !join && !down);

  function refresh(...keys: string[]) {
    for (const key of keys) void client.invalidateQueries({ queryKey: [key] });
  }

  const addMeeting = useMutation({
    mutationFn: (body: object) => post(meetingSchema, 'meetings', body),
    onSuccess: () => {
      refresh('meetings');
      setDialog(null);
      setAnnouncement('Meeting added.');
    },
  });
  const explain = useMutation({
    mutationFn: (id: string) =>
      post(diagnosisSchema, 'diagnose', { session_id: id }),
    onSuccess: () => refresh('activity'),
  });
  const preflight = useMutation({
    mutationFn: (meeting: Meeting | undefined) =>
      post(preflightSchema, 'preflight', { meeting_id: meeting?.id ?? null }),
    onSuccess: (result) => {
      setSession(result);
      refresh('readiness', 'history', 'activity', 'insights');
    },
  });
  const plan = useMutation({
    mutationFn: (id: string) =>
      post(actionSchema, 'actions/plan', {
        session_id: id,
        action_id: stopAction,
      }),
    onSuccess: (result) => {
      setAction(result);
      setApprovalError(undefined);
      setDialog('approval');
    },
  });
  const approve = useMutation({
    mutationFn: (target: Action) =>
      post(actionSchema, `actions/${target.id}/approve`, {
        approval_token: target.approval_token,
        approved: true,
      }),
    onSuccess: (result) => {
      setAction(result);
      client.setQueryData(['action', result.id], result);
      setDialog(null);
      refresh('readiness', 'history', 'status', 'activity', 'insights');
    },
    onError: (error) => setApprovalError(toMessage(error)),
  });
  const cancel = useMutation({
    mutationFn: (target: Action) =>
      post(actionSchema, `actions/${target.id}/cancel`, {
        approval_token: target.approval_token,
      }),
    onSuccess: (result) => {
      setAction(result);
      setDialog(null);
      refresh('activity');
    },
    onError: () => {
      setDialog(null);
      setAnnouncement('Approval dialog dismissed. No approval was sent.');
    },
  });
  const probe = useMutation({
    mutationFn: () => post(connectivitySchema, 'connectivity/check'),
    onSuccess: (newConnectivity) => {
      client.setQueryData(
        ['status'],
        status.data
          ? { ...status.data, connectivity: newConnectivity }
          : undefined,
      );
      refresh('status', 'activity');
    },
  });
  const networkExplain = useMutation({
    mutationFn: (question: string) =>
      post(diagnosisSchema, 'diagnosis/chat', { question }),
    onSuccess: () => refresh('activity'),
  });
  const startDemo = useMutation({
    mutationFn: () => post(workloadSchema, 'demo/start'),
    onSuccess: () => {
      setDemoNotice('The controlled demo workload is running.');
      refresh('status', 'readiness', 'history', 'activity');
    },
  });
  const cleanupDemo = useMutation({
    mutationFn: async (mode: 'stop' | 'reset') => {
      if (mode === 'stop')
        await post(workloadSchema, 'demo/stop', { confirm: true });
      else await post(resetSchema, 'demo/reset', { confirm: true });
    },
    onSuccess: (_result, mode) => {
      if (mode === 'reset') {
        setSession(undefined);
        setAction(undefined);
        explain.reset();
      }
      setDemoConfirm(null);
      setDemoNotice(
        mode === 'reset'
          ? 'Demo schedule and session reset.'
          : 'Demo workload stopped.',
      );
      refresh('meetings', 'status', 'readiness', 'history', 'activity');
    },
  });
  const simulateCloud = useMutation({
    mutationFn: (enabled: boolean) =>
      post(connectivitySchema, 'demo/cloud', { enabled }),
    onSuccess: () => refresh('status', 'activity'),
  });
  const clearHistory = useMutation({
    mutationFn: () => api(z.unknown(), 'privacy/history', { method: 'DELETE' }),
    onSuccess: () => {
      setSession(undefined);
      setAction(undefined);
      explain.reset();
      refresh('activity', 'history', 'insights', 'privacy');
      setDialog(null);
      setAnnouncement('Local history cleared.');
    },
  });

  const state = currentReadiness(
    readiness.data ?? session,
    down || readiness.isError,
    preflight.isPending || (readiness.isPending && !down),
  );
  const isSameWorkload =
    session?.snapshot.workload.id === readiness.data?.snapshot.workload.id;
  const matchesFinding =
    finding &&
    session?.findings.some(
      (entry) => entry.id === finding.id || entry.category === finding.category,
    );
  const latestDiagnosis =
    matchesFinding && isSameWorkload && explain.variables === session?.id
      ? explain.data
      : undefined;

  function preflightMeeting() {
    setAnnouncement(undefined);
    explain.reset();
    preflight.mutate(nextMeeting, {
      onSuccess: (result) => {
        setAnnouncement('Preflight complete. Device checks are up to date.');
        if (result.findings.length) explain.mutate(result.id);
      },
    });
  }

  async function loadFinding(mode: 'explain' | 'fix') {
    try {
      const existing = isSameWorkload && matchesFinding;
      const result =
        existing && session
          ? session
          : await preflight.mutateAsync(nextMeeting);
      if (mode === 'fix') {
        if (!actionable(result.findings))
          throw new Error(
            'The controlled workload is no longer eligible for a fix.',
          );
        setDialogFinding(actionable(result.findings));
        plan.mutate(result.id);
      } else {
        explain.mutate(result.id);
      }
    } catch (error) {
      setAnnouncement(toMessage(error));
    }
  }

  function dismiss() {
    if (dialog === 'approval' && action?.approval_token) {
      if (!approve.isPending && !cancel.isPending) cancel.mutate(action);
      return;
    }
    setDemoConfirm(null);
    setDialog(null);
  }

  function openDemo() {
    setDemoConfirm(null);
    setDemoNotice(undefined);
    startDemo.reset();
    cleanupDemo.reset();
    simulateCloud.reset();
    setDialog('demo');
  }

  const currentSection =
    sections.find((section) => section.href === path) ?? sections[0];
  const today = path === '/';
  const snapshot = readiness.data?.snapshot;
  const latestLabel = snapshot
    ? `${down || readiness.isError ? 'Last reading' : 'Updated'} ${timeLabel(snapshot.captured_at)}`
    : 'Waiting for measurements';
  const displayTitle = today ? 'Your workday, ready.' : currentSection.label;
  const sectionDescription: Record<string, string> = {
    '/': 'Get set for your next meeting with a quick check-in on your device.',
    '/readiness':
      'Live measurements and the device checks that support your next meeting.',
    '/activity': 'Preflights, findings, and approved actions on this device.',
    '/insights':
      'A clear view of meeting preparation and fixes on this device.',
    '/privacy': 'See what Spark Ready processes and stores on your device.',
    '/settings': 'Local services, connection diagnostics, and demo controls.',
  };
  const diagnostic = (
    <DiagnosisCard
      finding={finding || undefined}
      diagnosis={latestDiagnosis}
      pending={explain.isPending}
      disabled={down || isFixing || preflight.isPending}
      explainingError={explain.isError ? toMessage(explain.error) : undefined}
      canFix={Boolean(
        finding && finding.recommended_action_ids.includes(stopAction),
      )}
      planPending={plan.isPending}
      onExplain={() => void loadFinding('explain')}
      onFix={() => void loadFinding('fix')}
    />
  );
  const actionOutcomes = (
    <>
      <ActionOutcome action={currentAction} />
      {liveAction.isError && isFixing && (
        <Notice kind="error">
          The action result is unavailable. Spark Ready will check again when
          the agent reconnects.
        </Notice>
      )}
      {plan.isError && <Notice kind="error">{toMessage(plan.error)}</Notice>}
    </>
  );
  const networkButton = (
    <button className="button secondary" onClick={() => setDialog('network')}>
      <Wifi size={17} />
      Investigate connection
    </button>
  );
  const demoError = startDemo.error ?? cleanupDemo.error ?? simulateCloud.error;

  return (
    <div className="shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside
        className={`sidebar ${menu ? 'menu-open' : ''}`}
        aria-label="Workspace navigation"
      >
        <Link href="/" className="brand" onClick={() => setMenu(false)}>
          <span className="brand-icon">
            <Sparkles size={23} fill="currentColor" strokeWidth={1.5} />
          </span>
          <span>
            Spark<span className="brand-accent">Ready</span>
            <small>LOCAL WORKSPACE</small>
          </span>
        </Link>
        <nav className="nav-links" aria-label="Primary">
          {sections.map(({ href, label, icon: Icon }) => (
            <Link
              href={href}
              key={href}
              aria-current={path === href ? 'page' : undefined}
              onClick={() => setMenu(false)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {path === href && (
                <ChevronRight
                  className="nav-current"
                  size={15}
                  aria-hidden="true"
                />
              )}
            </Link>
          ))}
        </nav>
        <div className="side-footer">
          <button
            className="demo-button"
            onClick={() => {
              setMenu(false);
              openDemo();
            }}
          >
            <FlaskConical size={17} />
            <span>Demo controls</span>
            <ChevronRight size={15} />
          </button>
          <div className="sidebar-device">
            <div className="side-device-icon">
              <ShieldCheck size={19} />
            </div>
            <div>
              <strong>On this device</strong>
              <p>Privacy-first workspace</p>
            </div>
          </div>
        </div>
      </aside>
      <div className="layout">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button menu-button"
              aria-label={menu ? 'Close menu' : 'Open menu'}
              aria-expanded={menu}
              onClick={() => setMenu(!menu)}
            >
              <Menu size={21} />
            </button>
            <span className="topbar-location">{currentSection.label}</span>
            <span className="topbar-divider" />
            <time className="today-date">
              {now
                ? dateLabel(now, {
                    weekday: 'long',
                    month: 'long',
                    day: 'numeric',
                  })
                : 'Today'}
            </time>
          </div>
          <div className="topbar-right" aria-label="Service status">
            <span
              className="header-indicator"
              title={down ? 'Device agent unreachable' : 'Local device agent'}
            >
              <span
                className={`header-dot ${down ? 'dot-amber' : status.isSuccess ? 'dot-green' : 'dot-muted'}`}
              />
              <span className="indicator-text">
                {down
                  ? 'Agent unavailable'
                  : status.isSuccess
                    ? 'Device connected'
                    : 'Connecting'}
              </span>
            </span>
            <button
              className="header-indicator"
              onClick={() => setDialog('network')}
              title={connectivity?.ollama.explanation ?? 'Local AI status'}
            >
              <Sparkles size={15} />
              <span className="indicator-text">
                {!down && connectivity?.ollama.state === 'connected'
                  ? connectivity?.ollama_loading
                    ? 'Local AI loading'
                    : 'Local AI available'
                  : status.isPending
                    ? 'Local AI'
                    : 'Local AI unavailable'}
              </span>
            </button>
            <Link
              className="header-indicator privacy-indicator"
              href="/privacy"
              title="Privacy details"
            >
              <ShieldCheck size={15} />
              <span className="indicator-text">Private by design</span>
            </Link>
          </div>
        </header>
        <main className="main" id="main">
          <div className="page-heading">
            <div>
              <h1>{displayTitle}</h1>
              <p>{sectionDescription[path] ?? sectionDescription['/']}</p>
            </div>
            {today && (
              <button
                className="button secondary new-meeting"
                onClick={() => {
                  addMeeting.reset();
                  setDialog('meeting');
                }}
                disabled={down || status.isPending}
              >
                <Plus size={18} />
                Add meeting
              </button>
            )}
            {path === '/readiness' && networkButton}
          </div>
          <p className="sr-only" aria-live="polite">
            {announcement}
          </p>
          {down ? (
            <AgentUnavailable />
          ) : (
            <OfflineBanner
              connectivity={connectivity}
              onOpen={() => setDialog('network')}
            />
          )}
          {!down &&
            !today &&
            connectivity?.nexthink.state === 'authentication_error' && (
              <Notice kind="neutral">
                Nexthink authentication needs attention. Local services are
                available.
              </Notice>
            )}
          {preflight.isError && (
            <Notice kind="error">{toMessage(preflight.error)}</Notice>
          )}
          {today && (
            <>
              <div className="dashboard-grid dashboard-top">
                <MeetingHero
                  meeting={nextMeeting}
                  now={now}
                  preflight={sessionForMeeting}
                  join={join}
                  joinBlocked={joinBlocked}
                  down={down}
                  loading={meetings.isPending}
                  preparing={preflight.isPending}
                  onPrepare={preflightMeeting}
                  onChecklist={() =>
                    busyReview.current?.scrollIntoView({ block: 'start' })
                  }
                  onAdd={() => {
                    addMeeting.reset();
                    setDialog('meeting');
                  }}
                />
                <ReadinessCard
                  state={state}
                  readiness={readiness.data ?? session}
                  checked={Boolean(sessionForMeeting)}
                  down={down || readiness.isError}
                  onReview={() => router.push('/readiness')}
                />
              </div>
              <div className="dashboard-grid dashboard-body">
                <div className="main-stack">
                  <section aria-labelledby="metrics-heading">
                    <div className="row-heading">
                      <div>
                        <h2 id="metrics-heading">Device performance</h2>
                        <p>Live readings from your local agent</p>
                      </div>
                      <span className="timestamp">
                        <span
                          className={`status-dot ${down || !snapshot ? 'muted-dot' : ''}`}
                        />
                        {latestLabel}
                      </span>
                    </div>
                    <Metrics
                      snapshot={snapshot}
                      history={history.data}
                      stale={down || readiness.isError}
                      loading={readiness.isPending && !down}
                    />
                    {snapshot?.workload.active && (
                      <Workload
                        snapshot={snapshot}
                        history={history.data}
                        stale={down || readiness.isError}
                      />
                    )}
                  </section>
                  <section
                    ref={busyReview}
                    className="stack"
                    aria-label="Meeting preparation results"
                  >
                    {diagnostic}
                    {actionOutcomes}
                    {sessionForMeeting && !isFixing && (
                      <article className="card detail-card prep-card">
                        <div className="section-heading">
                          <div className="section-icon violet-icon">
                            <Check size={21} />
                          </div>
                          <div>
                            <h2>Meeting checklist</h2>
                            <p>
                              Preflight completed at{' '}
                              {timeLabel(sessionForMeeting.completed_at)}
                            </p>
                          </div>
                          <StateBadge state={state} />
                        </div>
                        <Checks
                          readiness={readiness.data ?? sessionForMeeting}
                          stale={down || readiness.isError}
                        />
                        {nextMeeting && (
                          <div className="manual-checks">
                            <h3>Your preparation</h3>
                            <label>
                              <input
                                type="checkbox"
                                checked={audioChecked[nextMeeting.id] ?? false}
                                onChange={(event) =>
                                  setAudioChecked({
                                    ...audioChecked,
                                    [nextMeeting.id]: event.target.checked,
                                  })
                                }
                              />
                              I tested my microphone and speakers in the meeting
                              app.
                            </label>
                            <p>
                              {join
                                ? 'Meeting link available.'
                                : joinBlocked
                                  ? 'Meeting link saved. It is unavailable while offline.'
                                  : 'This meeting has no join link.'}
                            </p>
                          </div>
                        )}
                      </article>
                    )}
                  </section>
                  {(events.data?.length ?? 0) > 0 && (
                    <article className="card detail-card">
                      <div className="panel-heading">
                        <h2>Recent activity</h2>
                        <Link className="text-button" href="/activity">
                          View activity
                        </Link>
                      </div>
                      <EventList events={events.data} limit={3} stale={down} />
                    </article>
                  )}
                </div>
                <div className="side-stack">
                  <Upcoming
                    meetings={sorted.slice(1)}
                    now={now}
                    stale={down}
                    onAdd={() => {
                      addMeeting.reset();
                      setDialog('meeting');
                    }}
                  />
                  <DailyTip />
                  <article className="card connectivity-card">
                    <div className="panel-heading">
                      <h2>Connectivity</h2>
                      <button
                        className="icon-button"
                        aria-label="Investigate connection"
                        title="Investigate connection"
                        onClick={() => setDialog('network')}
                      >
                        <CircleHelp size={18} />
                      </button>
                    </div>
                    <dl>
                      <div>
                        <dt>Device agent</dt>
                        <dd>
                          {down ? (
                            <Badge tone="amber" dot>
                              Unreachable
                            </Badge>
                          ) : (
                            <ServiceBadge service={connectivity?.agent} />
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Local AI</dt>
                        <dd>
                          <ServiceBadge
                            service={down ? undefined : connectivity?.ollama}
                            connectedLabel="Available"
                          />
                        </dd>
                      </div>
                      <div>
                        <dt>Internet</dt>
                        <dd>
                          <ServiceBadge
                            service={down ? undefined : connectivity?.internet}
                          />
                        </dd>
                      </div>
                      <div>
                        <dt>Nexthink</dt>
                        <dd>
                          <ServiceBadge
                            service={down ? undefined : connectivity?.nexthink}
                          />
                        </dd>
                      </div>
                    </dl>
                  </article>
                </div>
              </div>
            </>
          )}
          {path === '/readiness' && (
            <div className="stack subpage">
              <section aria-labelledby="device-current">
                <div className="row-heading">
                  <div>
                    <h2 id="device-current">Device performance</h2>
                    <p>{latestLabel}</p>
                  </div>
                  <StateBadge state={state} />
                </div>
                <Metrics
                  snapshot={snapshot}
                  history={history.data}
                  stale={down || readiness.isError}
                  loading={readiness.isPending && !down}
                />
                <Workload
                  snapshot={snapshot}
                  history={history.data}
                  stale={down || readiness.isError}
                />
              </section>
              {diagnostic}
              {actionOutcomes}
              <article className="card detail-card">
                <div className="panel-heading">
                  <h2>Readiness checklist</h2>
                  <button
                    className="button secondary"
                    disabled={down || preflight.isPending}
                    onClick={preflightMeeting}
                  >
                    {preflight.isPending ? (
                      <Spinner />
                    ) : (
                      <ActivityIcon size={17} />
                    )}
                    Run preflight
                  </button>
                </div>
                <Checks
                  readiness={readiness.data ?? session}
                  stale={down || readiness.isError}
                />
              </article>
            </div>
          )}
          {path === '/activity' && (
            <div className="subpage">
              <article className="card detail-card">
                <EventList events={events.data} stale={down} />
              </article>
            </div>
          )}
          {path === '/insights' && (
            <div className="stack subpage">
              <Insights insights={insights.data} stale={down || insights.isError} />
            </div>
          )}
          {path === '/privacy' && (
            <div className="stack subpage">
              <Privacy
                privacy={privacy.data}
                connectivity={connectivity}
                onClear={() => {
                  clearHistory.reset();
                  setDialog('history');
                }}
                down={down || isFixing}
              />
            </div>
          )}
          {path === '/settings' && (
            <div className="stack subpage">
              <Settings
                connectivity={connectivity}
                model={status.data?.model}
                onNetwork={() => setDialog('network')}
                onDemo={openDemo}
              />
            </div>
          )}
          {children}
        </main>
      </div>
      {dialog === 'meeting' && (
        <Dialog title="Add a meeting" onDismiss={dismiss}>
          <MeetingForm
            now={now}
            busy={addMeeting.isPending}
            error={addMeeting.isError ? toMessage(addMeeting.error) : undefined}
            onSave={addMeeting.mutate}
            onCancel={dismiss}
          />
        </Dialog>
      )}
      {dialog === 'network' && (
        <Dialog title="Investigate connection" onDismiss={dismiss}>
          <NetworkPanel
            connectivity={connectivity}
            down={down}
            probing={probe.isPending}
            error={probe.isError ? toMessage(probe.error) : undefined}
            onCheck={() => probe.mutate()}
            diagnosis={networkExplain.data}
            diagnosing={networkExplain.isPending}
            diagnosisError={
              networkExplain.isError
                ? toMessage(networkExplain.error)
                : undefined
            }
            onAsk={networkExplain.mutate}
          />
        </Dialog>
      )}
      {dialog === 'approval' && action && (
        <Dialog title="Approve local action" onDismiss={dismiss}>
          <div className="approval-body">
            <div className="section-heading">
              <div className="section-icon violet-icon">
                <ShieldCheck size={22} />
              </div>
              <div>
                <h3>{action.title}</h3>
                <p>{dialogFinding?.title ?? 'Spark Ready safe action'}</p>
              </div>
            </div>
            <dl className="approval-details">
              <div>
                <dt>Scope</dt>
                <dd>{action.scope}</dd>
              </div>
              <div>
                <dt>Expected result</dt>
                <dd>{action.expected_result}</dd>
              </div>
              <div>
                <dt>Side effects</dt>
                <dd>{action.side_effects}</dd>
              </div>
            </dl>
            {approvalError && <Notice kind="error">{approvalError}</Notice>}
            <p className="muted">
              Approval expires at {timeLabel(action.expires_at)}.
            </p>
            <div className="button-row dialog-actions">
              <button
                className="button secondary"
                onClick={dismiss}
                disabled={approve.isPending || cancel.isPending}
              >
                Cancel
              </button>
              <button
                className="button primary"
                onClick={() => approve.mutate(action)}
                disabled={
                  down ||
                  approve.isPending ||
                  cancel.isPending ||
                  !action.approval_token
                }
              >
                {approve.isPending ? <Spinner /> : <ShieldCheck size={17} />}
                Approve and stop workload
              </button>
            </div>
          </div>
        </Dialog>
      )}
      {dialog === 'history' && (
        <Dialog title="Clear local history?" onDismiss={dismiss}>
          <p className="muted">
            This deletes locally stored readiness activity, diagnostics, and
            action history.
          </p>
          {clearHistory.isError && (
            <Notice kind="error">{toMessage(clearHistory.error)}</Notice>
          )}
          <div className="button-row dialog-actions">
            <button className="button secondary" onClick={dismiss}>
              Cancel
            </button>
            <button
              className="button danger"
              onClick={() => clearHistory.mutate()}
              disabled={clearHistory.isPending || down}
            >
              {clearHistory.isPending && <Spinner />}Clear history
            </button>
          </div>
        </Dialog>
      )}
      {dialog === 'demo' && (
        <Dialog title="Demo controls" onDismiss={dismiss}>
          <div className="demo-content">
            <div className="section-heading">
              <div className="section-icon violet-icon">
                <FlaskConical size={21} />
              </div>
              <div>
                <h3>Presenter workspace</h3>
                <p>Sample meetings with live local telemetry.</p>
              </div>
              <Badge tone="violet">Demo tools</Badge>
            </div>
            <ul className="provider-list compact">
              <li>
                <strong>Device agent</strong>
                {down ? (
                  <Badge tone="amber" dot>
                    Unreachable
                  </Badge>
                ) : (
                  <ServiceBadge service={connectivity?.agent} />
                )}
              </li>
              <li>
                <strong>
                  Local AI{status.data?.model ? ` · ${status.data.model}` : ''}
                </strong>
                <ServiceBadge
                  service={down ? undefined : connectivity?.ollama}
                  connectedLabel="Available"
                />
              </li>
              <li>
                <strong>Device readings</strong>
                <Badge>Live local</Badge>
              </li>
              <li>
                <strong>Controlled workload</strong>
                <Badge tone={status.data?.demo.active ? 'amber' : 'muted'} dot>
                  {status.data?.demo.active
                    ? 'Active'
                    : down
                      ? 'Unknown'
                      : 'Idle'}
                </Badge>
              </li>
              <li>
                <strong>Cloud simulation</strong>
                <Badge
                  tone={
                    connectivity?.simulated_cloud_outage ? 'amber' : 'muted'
                  }
                >
                  {connectivity?.simulated_cloud_outage
                    ? 'Outage simulated'
                    : 'Idle'}
                </Badge>
              </li>
            </ul>
            {demoNotice && (
              <p role="status" className="inline-success">
                <Check size={17} />
                {demoNotice}
              </p>
            )}
            {demoError && <Notice kind="error">{toMessage(demoError)}</Notice>}
            {demoConfirm && (
              <Notice>
                <p>
                  {demoConfirm === 'stop'
                    ? 'Stop the Spark Ready demonstration workload?'
                    : 'Reset the demo schedule and stop any running demonstration workload?'}
                </p>
                <div className="button-row">
                  <button
                    className="button secondary"
                    onClick={() => setDemoConfirm(null)}
                  >
                    Cancel
                  </button>
                  <button
                    className="button primary"
                    onClick={() => cleanupDemo.mutate(demoConfirm)}
                    disabled={cleanupDemo.isPending}
                  >
                    {cleanupDemo.isPending && <Spinner />}Confirm {demoConfirm}
                  </button>
                </div>
              </Notice>
            )}
            <div className="demo-buttons">
              <button
                className="button primary"
                disabled={
                  down ||
                  Boolean(status.data?.demo.active) ||
                  startDemo.isPending ||
                  cleanupDemo.isPending
                }
                onClick={() => startDemo.mutate()}
              >
                {startDemo.isPending && <Spinner />}Start safe CPU workload
              </button>
              <button
                className="button secondary"
                disabled={down || !status.data?.demo.active || isFixing}
                onClick={() => setDemoConfirm('stop')}
              >
                Stop workload
              </button>
              <button
                className="button secondary"
                disabled={
                  down || isFixing || preflight.isPending || startDemo.isPending
                }
                onClick={() => setDemoConfirm('reset')}
              >
                Reset demo session
              </button>
              <button
                className="button secondary"
                disabled={down || preflight.isPending}
                onClick={() => {
                  setDialog(null);
                  preflightMeeting();
                }}
              >
                Run preflight
              </button>
              <button
                className="button secondary"
                disabled={down || status.isFetching}
                onClick={() => {
                  void status
                    .refetch()
                    .then((result) =>
                      setDemoNotice(
                        result.isError
                          ? 'The local agent did not respond.'
                          : 'Local AI status requested.',
                      ),
                    );
                }}
              >
                Check Ollama
              </button>
              <button
                className="button secondary"
                disabled={down || simulateCloud.isPending}
                onClick={() =>
                  simulateCloud.mutate(!connectivity?.simulated_cloud_outage)
                }
              >
                {connectivity?.simulated_cloud_outage
                  ? 'Restore cloud adapter'
                  : 'Simulate cloud unavailability'}
              </button>
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
}
