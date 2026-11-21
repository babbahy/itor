'use client';

import {
  Activity as ActivityIcon,
  Check,
  ChevronRight,
  CircleHelp,
  FlaskConical,
  Menu,
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
  companyStatusSchema,
  fixRunSchema,
  fixesSchema,
  incidentsSchema,
  teamSchema,
  ticketSchema,
  workDayViewSchema,
  post,
  preflightSchema,
  privacySchema,
  readinessSchema,
  resetSchema,
  statusSchema,
  workloadSchema,
  type Action,
  type Finding,
  type Fix,
  type FixRun,
  type Preflight,
} from '@/lib/api';
import {
  actionPending,
  actionable,
  currentReadiness,
  dateLabel,
  sections,
  timeLabel,
  toMessage,
} from '@/lib/presentation';
import {
  ActionOutcome,
  Checks,
  DiagnosisCard,
  Metrics,
  ReadinessCard,
  Workload,
} from './health';
import { AgentUnavailable, NetworkPanel, OfflineBanner } from './network';
import { EventList, Privacy, Settings } from './secondary';
import { DayCard, FirstLaunchNotice, ManagerView, OfflineHelp, TeamView } from './worktime';
import { AskIT, HomeScreen, type HomeStatus } from './home';
import { Badge, Dialog, Notice, ServiceBadge, Spinner, StateBadge } from './ui';

const subscription = (callback: () => void) => {
  const timer = window.setInterval(callback, 5000);
  return () => window.clearInterval(timer);
};
const browserTime = () => Math.floor(Date.now() / 5000) * 5000;
const serverTime = () => 0;
const stopAction = 'stop_demo_workload';

type DialogName =
  | 'fix'
  | 'askit'
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
  const [fixRun, setFixRun] = useState<FixRun>();
  const [fixError, setFixError] = useState<string>();
  const [fixPick, setFixPick] = useState<Fix>();
  const [askDiagnosis, setAskDiagnosis] = useState<string>();
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
  const worktime = useQuery({
    queryKey: ['worktime'],
    queryFn: () => api(workDayViewSchema, 'worktime/today'),
    refetchInterval: 5000,
  });
  const company = useQuery({
    queryKey: ['company'],
    queryFn: () => api(companyStatusSchema, 'company/status'),
    refetchInterval: 10_000,
  });
  const fixes = useQuery({
    queryKey: ['fixes'],
    queryFn: () => api(fixesSchema, 'fixes'),
  });
  const incidents = useQuery({
    queryKey: ['incidents'],
    queryFn: () => api(incidentsSchema, 'incidents'),
    refetchInterval: 5000,
  });
  const events = useQuery({
    queryKey: ['activity'],
    queryFn: () => api(activitySchema, 'activity'),
    refetchInterval: 8000,
  });
  const team = useQuery({
    queryKey: ['team'],
    queryFn: () => api(teamSchema, 'company/team'),
    enabled: path === '/team',
    refetchInterval: 5000,
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
          ['readiness', 'history', 'status', 'activity', 'worktime'].includes(
            String(queryKey[0]),
          ),
      });
  }, [actionFinished, client]);
  const connectivity = status.data?.connectivity;
  const down = status.isError;
  const finding =
    !down &&
    (actionable(readiness.data?.findings ?? []) ?? readiness.data?.findings[0]);

  function refresh(...keys: string[]) {
    for (const key of keys) void client.invalidateQueries({ queryKey: [key] });
  }

  const explain = useMutation({
    mutationFn: (id: string) =>
      post(diagnosisSchema, 'diagnose', { session_id: id }),
    onSuccess: () => refresh('activity'),
  });
  const preflight = useMutation({
    mutationFn: () => post(preflightSchema, 'preflight'),
    onSuccess: (result) => {
      setSession(result);
      refresh('readiness', 'history', 'activity');
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
      refresh('readiness', 'history', 'status', 'activity', 'worktime');
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
        mode === 'reset' ? 'Demo reset.' : 'Demo workload stopped.',
      );
      refresh('status', 'readiness', 'history', 'activity');
    },
  });
  const simulateCloud = useMutation({
    mutationFn: (enabled: boolean) =>
      post(connectivitySchema, 'demo/cloud', { enabled }),
    onSuccess: () => refresh('status', 'activity'),
  });
  const blocked = useMutation({
    mutationFn: (value: boolean) =>
      post(workDayViewSchema, 'worktime/blocked', { blocked: value }),
    onSuccess: (result) => {
      client.setQueryData(['worktime'], result);
      refresh('activity');
    },
  });
  const demoDay = useMutation({
    mutationFn: () => post(workDayViewSchema, 'demo/worktime'),
    onSuccess: (result) => {
      client.setQueryData(['worktime'], result);
      setDemoNotice('A demo morning was added to today.');
      refresh('activity', 'company', 'team');
    },
  });
  const sendCompany = useMutation({
    mutationFn: () => post(companyStatusSchema, 'company/send'),
    onSuccess: (result) => {
      client.setQueryData(['company'], result);
      refresh('team');
    },
  });
  const planFix = useMutation({
    mutationFn: (fix: Fix) => post(fixRunSchema, `fixes/${fix.id}/plan`),
    onSuccess: (result, fix) => {
      setFixPick(fix);
      setFixRun(result);
      setFixError(undefined);
      setDialog('fix');
    },
    onError: (error) => setAnnouncement(toMessage(error)),
  });
  const approveFix = useMutation({
    mutationFn: (run: FixRun) =>
      post(fixRunSchema, `fixes/runs/${run.id}/approve`, {
        approval_token: run.approval_token,
        approved: true,
      }),
    onSuccess: (result) => {
      setFixRun(result);
      refresh('status', 'activity', 'incidents');
    },
    onError: (error) => setFixError(toMessage(error)),
  });
  const cancelFix = useMutation({
    mutationFn: (run: FixRun) =>
      post(fixRunSchema, `fixes/runs/${run.id}/cancel`, {
        approval_token: run.approval_token,
      }),
    onSettled: () => {
      setDialog(null);
      setFixRun(undefined);
      refresh('activity');
    },
  });
  const checkProblem = useMutation({
    mutationFn: async (question: string) => {
      const result = await preflight.mutateAsync();
      return question.trim()
        ? post(diagnosisSchema, 'diagnosis/chat', { question, session_id: result.id })
        : post(diagnosisSchema, 'diagnose', { session_id: result.id });
    },
    onSuccess: () => refresh('activity'),
  });
  const sendTicket = useMutation({
    mutationFn: (message: string) =>
      post(ticketSchema, 'support/ticket', { message, diagnosis: askDiagnosis ?? null }),
    onSuccess: () => refresh('activity', 'company'),
  });
  const clearHistory = useMutation({
    mutationFn: () => api(z.unknown(), 'privacy/history', { method: 'DELETE' }),
    onSuccess: () => {
      setSession(undefined);
      setAction(undefined);
      explain.reset();
      refresh('activity', 'history', 'worktime', 'privacy');
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

  function runCheck() {
    setAnnouncement(undefined);
    explain.reset();
    preflight.mutate(undefined, {
      onSuccess: (result) => {
        setAnnouncement('PC check complete.');
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
          : await preflight.mutateAsync();
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
    if (dialog === 'fix') {
      if (fixRun?.status === 'awaiting_approval') {
        if (!approveFix.isPending && !cancelFix.isPending) cancelFix.mutate(fixRun);
        return;
      }
      if (approveFix.isPending) return;
      setFixRun(undefined);
    }
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
  const today = path === '/day';
  const home = path === '/';
  const snapshot = readiness.data?.snapshot;
  const latestLabel = snapshot
    ? `${down || readiness.isError ? 'Last reading' : 'Updated'} ${timeLabel(snapshot.captured_at)}`
    : 'Waiting for measurements';
  const displayTitle = today ? 'Your day' : currentSection.label;
  const sectionDescription: Record<string, string> = {
    '/day': 'Your working time today, and help when a tool slows you down, even offline.',
    '/readiness': 'Live readings from your PC, quick checks and safe fixes.',
    '/activity': 'Everything itor noticed and did on this PC.',
    '/team': 'Working time of the team, and the time lost to tools. Inside the company only.',
    '/privacy': 'See what itor processes and stores on your device.',
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
          The action result is unavailable. itor will check again when
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
  const isOffline = Boolean(
    connectivity &&
      (connectivity.offline_rescue ||
        connectivity.simulated_cloud_outage ||
        ['disconnected', 'unreachable'].includes(connectivity.internet.state) ||
        connectivity.network_interface.state === 'disconnected'),
  );
  let homeStatus: HomeStatus = {
    tone: 'green',
    title: 'Everything looks fine',
    detail: "Your PC and connection look OK. If something still doesn't work, itor can help.",
    offline: false,
  };
  if (down)
    homeStatus = { tone: 'muted', title: 'itor is not running', detail: 'Start itor again, or ask IT.', offline: false };
  else if (isOffline)
    homeStatus = {
      tone: 'amber',
      title: "You're offline",
      detail: 'itor still works without internet and can help you get back online.',
      offline: true,
    };
  else if (readiness.data && ['attention', 'not_ready'].includes(readiness.data.readiness))
    homeStatus = {
      tone: 'amber',
      title: 'Something is slowing your PC',
      detail: readiness.data.findings[0]?.title ?? 'itor found something worth fixing.',
      offline: false,
    };
  function openAskIT(diagnosisHeadline?: string) {
    sendTicket.reset();
    setAskDiagnosis(diagnosisHeadline);
    setDialog('askit');
  }

  return (
    <div className={home ? 'home-shell' : 'shell'}>
      {home ? (
        <HomeScreen
          status={homeStatus}
          paidSeconds={worktime.data?.paid_seconds_total}
          down={down}
          checking={checkProblem.isPending}
          diagnosis={checkProblem.data}
          checkError={checkProblem.isError ? toMessage(checkProblem.error) : undefined}
          fixes={fixes.data}
          planning={planFix.isPending ? planFix.variables?.id : undefined}
          canStopWorkload={Boolean(
            session && checkProblem.data?.recommended_action_id === stopAction,
          )}
          stopping={plan.isPending || isFixing}
          outcome={actionOutcomes}
          notice={<FirstLaunchNotice />}
          onCheck={(question) => checkProblem.mutate(question)}
          onQuickFix={(fix) => planFix.mutate(fix)}
          onStopWorkload={() => {
            if (!session) return;
            setDialogFinding(actionable(session.findings));
            plan.mutate(session.id);
          }}
          onAskIT={openAskIT}
          onDemo={openDemo}
        />
      ) : (
        <>
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
              it<span className="brand-accent">or</span>
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
                <p>{sectionDescription[path] ?? ''}</p>
              </div>
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
                <FirstLaunchNotice />
                <div className="dashboard-grid dashboard-top">
                  <DayCard
                    day={worktime.data}
                    busy={blocked.isPending}
                    down={down || worktime.isError}
                    onBlocked={(value) => blocked.mutate(value)}
                  />
                  <ReadinessCard
                    state={state}
                    readiness={readiness.data ?? session}
                    checked={Boolean(session)}
                    down={down || readiness.isError}
                    onReview={() => router.push('/readiness')}
                  />
                </div>
                <div className="dashboard-grid dashboard-body">
                  <div className="main-stack">
                    <OfflineHelp
                      connectivity={down ? undefined : connectivity}
                      incident={incidents.data?.current}
                      fixes={fixes.data}
                      planning={planFix.isPending ? planFix.variables?.id : undefined}
                      onAsk={() => setDialog('network')}
                      onFix={(fix) => planFix.mutate(fix)}
                    />
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
                      aria-label="PC check results"
                    >
                      {diagnostic}
                      {actionOutcomes}
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
                    <ManagerView day={worktime.data} company={company.data} />
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
                <OfflineHelp
                  always
                  connectivity={down ? undefined : connectivity}
                  incident={incidents.data?.current}
                  fixes={fixes.data}
                  planning={planFix.isPending ? planFix.variables?.id : undefined}
                  onAsk={() => setDialog('network')}
                  onFix={(fix) => planFix.mutate(fix)}
                />
                <article className="card detail-card">
                  <div className="panel-heading">
                    <h2>PC checks</h2>
                    <button
                      className="button secondary"
                      disabled={down || preflight.isPending}
                      onClick={runCheck}
                    >
                      {preflight.isPending ? (
                        <Spinner />
                      ) : (
                        <ActivityIcon size={17} />
                      )}
                      Check my PC
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
            {path === '/team' && (
              <div className="stack subpage">
                <TeamView
                  team={team.data}
                  company={company.data}
                  sending={sendCompany.isPending}
                  onSend={() => sendCompany.mutate()}
                  stale={down || team.isError}
                />
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
        </>
      )}
      {dialog === 'askit' && (
        <Dialog title="Ask IT" onDismiss={dismiss}>
          <AskIT
            diagnosis={askDiagnosis}
            sending={sendTicket.isPending}
            error={sendTicket.isError ? toMessage(sendTicket.error) : undefined}
            ticket={sendTicket.data}
            offline={isOffline}
            onSend={(message) => sendTicket.mutate(message)}
            onClose={dismiss}
          />
        </Dialog>
      )}
      {dialog === 'fix' && fixRun && (
        <Dialog title="Approve a quick fix" onDismiss={dismiss}>
          <div className="approval-body">
            <div className="section-heading">
              <div className="section-icon violet-icon">
                <ShieldCheck size={22} />
              </div>
              <div>
                <h3>{fixRun.title}</h3>
                <p>{fixPick?.what_it_does}</p>
              </div>
            </div>
            <dl className="approval-details">
              <div>
                <dt>Exact command</dt>
                <dd>
                  <code>{fixPick?.command}</code>
                </dd>
              </div>
              {fixPick?.needs_admin && (
                <div>
                  <dt>Needs</dt>
                  <dd>itor running as administrator</dd>
                </div>
              )}
              {fixRun.status !== 'awaiting_approval' && (
                <div>
                  <dt>Result</dt>
                  <dd>
                    {fixRun.status === 'succeeded' ? 'Done. ' : `${fixRun.status}. `}
                    Internet before: {fixRun.internet_before ?? '—'} · after: {fixRun.internet_after ?? '—'}
                    {fixRun.message ? ` · ${fixRun.message}` : ''}
                  </dd>
                </div>
              )}
            </dl>
            {fixError && <Notice kind="error">{fixError}</Notice>}
            <div className="button-row dialog-actions">
              {fixRun.status === 'awaiting_approval' ? (
                <>
                  <button
                    className="button secondary"
                    onClick={dismiss}
                    disabled={approveFix.isPending || cancelFix.isPending}
                  >
                    Decline
                  </button>
                  <button
                    className="button primary"
                    onClick={() => approveFix.mutate(fixRun)}
                    disabled={down || approveFix.isPending || cancelFix.isPending || !fixRun.approval_token}
                  >
                    {approveFix.isPending ? <Spinner /> : <ShieldCheck size={17} />}
                    {approveFix.isPending ? 'Running…' : 'Approve and run'}
                  </button>
                </>
              ) : (
                <button className="button primary" onClick={dismiss}>
                  Close
                </button>
              )}
            </div>
          </div>
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
                <p>{dialogFinding?.title ?? 'itor safe action'}</p>
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
                <p>Live readings from this PC, plus demo tools.</p>
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
                    ? 'Stop the itor demonstration workload?'
                    : 'Reset the demo and stop any running demonstration workload?'}
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
                disabled={down || demoDay.isPending}
                onClick={() => demoDay.mutate()}
              >
                {demoDay.isPending && <Spinner />}Add a demo morning
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
                  runCheck();
                }}
              >
                Check my PC
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
