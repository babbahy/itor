import type {
  Action,
  Diagnosis,
  Meeting,
  Readiness,
  ServiceStatus,
  Snapshot,
} from '../lib/api';

export function makeMeeting(now: number, minutes = 12): Meeting {
  return {
    id: `meeting-${minutes}`,
    title: minutes === 12 ? 'Product Team Weekly' : 'Project Review',
    start_at: new Date(now + minutes * 60_000).toISOString(),
    end_at: new Date(now + (minutes + 30) * 60_000).toISOString(),
    platform: 'Microsoft Teams',
    join_url: 'https://meet.example/session',
    notes: null,
    source: 'demo',
  };
}

const now = () => new Date().toISOString();

function service(
  name: string,
  state: ServiceStatus['state'] = 'connected',
): ServiceStatus {
  return {
    name,
    state,
    configured: state !== 'not_configured',
    explanation: `${name} status: ${state}.`,
    last_checked_at: now(),
  };
}

type ConnectionFixture = {
  offline?: boolean;
  disconnected?: boolean;
  simulated?: boolean;
  ollama?: boolean;
};

export function connectivity({
  offline,
  disconnected,
  simulated,
  ollama = true,
}: ConnectionFixture = {}) {
  return {
    agent: service('Device agent'),
    ollama: service('Ollama', ollama ? 'connected' : 'unreachable'),
    ollama_loading: false,
    network_interface: service(
      'Network interface',
      disconnected ? 'disconnected' : 'connected',
    ),
    gateway: service('Default route'),
    dns_resolver: service('DNS resolver'),
    dns: service('DNS', 'unknown'),
    internet: service('Internet', offline ? 'unreachable' : 'not_configured'),
    nexthink: service('Nexthink', simulated ? 'unreachable' : 'not_configured'),
    offline_rescue: Boolean(offline),
    simulated_cloud_outage: Boolean(simulated),
    updated_at: now(),
    cloud_data_stale: Boolean(offline || simulated),
    cloud_last_updated_at: null,
  };
}

export function statusReport(options?: ConnectionFixture, active = false) {
  return {
    agent: 'connected',
    telemetry: 'local',
    remediation: 'local',
    mode: 'live_local',
    model: 'qwen3.5:4b',
    connectivity: connectivity(options),
    demo: { active },
  };
}

export function sample(active = false, unknown = false): Snapshot {
  return {
    id: 'sample-1',
    captured_at: now(),
    source: 'local',
    cpu_percent: unknown ? null : active ? 19 : 12,
    cpu_logical: 8,
    cpu_physical: 4,
    memory_percent: 47,
    memory_total: 8 * 2 ** 30,
    memory_available: 4 * 2 ** 30,
    disk_percent: 37,
    disk_total: 500 * 2 ** 30,
    disk_free: 315 * 2 ** 30,
    workload: {
      active,
      id: active ? 'workload' : null,
      cpu_percent: active ? 42 : 0,
    },
    network_up: true,
    errors: [],
  };
}

export function readinessReport(readiness: Readiness['readiness']): Readiness {
  const active = readiness === 'attention';
  return {
    readiness,
    snapshot: sample(active, readiness === 'unknown'),
    findings: active
      ? [
          {
            id: 'finding',
            category: 'workload',
            severity: 'warning',
            title: 'Controlled workload consuming CPU',
            evidence: 'The controlled workload used 42% of one CPU core.',
            window_seconds: 2,
            potential_impact: 'Less CPU is available for a meeting app.',
            recommended_action_ids: ['stop_demo_workload'],
            source: 'local',
            limitations: 'Overall CPU can change independently.',
          },
        ]
      : [],
    checks: [
      {
        id: 'cpu',
        label: 'CPU utilization',
        state:
          readiness === 'unknown' ? 'unknown' : active ? 'warning' : 'passed',
        detail: 'Measured on this device.',
      },
      {
        id: 'audio',
        label: 'Audio availability',
        state: 'unsupported',
        detail: 'Test audio in your meeting app.',
      },
      {
        id: 'network',
        label: 'Network adapter',
        state: 'passed',
        detail: 'An interface is up.',
      },
    ],
  };
}

export function explanation(rules = true): Diagnosis {
  return {
    status: rules ? 'fallback' : 'complete',
    provider: rules ? 'rules' : 'ollama',
    model: rules ? null : 'qwen3.5:4b',
    headline: 'A temporary workload is using CPU',
    explanation: 'The measured workload can be safely stopped.',
    observed_facts: ['The controlled workload used 42% of one CPU core.'],
    possible_causes: [],
    potential_impact: 'It uses CPU time.',
    recommended_action_id: 'stop_demo_workload',
    action_explanation: 'Stops the demo.',
    uncertainty: 'System-wide CPU may vary.',
    verification_advice: 'Check whether the workload exited.',
    safe_steps: ['Check if Wi-Fi is enabled.'],
  };
}

export function approval(status: Action['status']): Action {
  const completed = status === 'succeeded';
  return {
    id: 'action',
    session_id: 'session',
    action_id: 'stop_demo_workload',
    status,
    title: 'Stop demo workload',
    scope: 'Stop the temporary workload created by itor.',
    expected_result: 'Release the CPU time used by this workload.',
    side_effects: 'Ends the current demo run.',
    expires_at: new Date(Date.now() + 120_000).toISOString(),
    approval_token:
      status === 'awaiting_approval' ? 'test-approval-token' : null,
    before: {
      captured_at: now(),
      workload_active: true,
      workload_cpu_percent: 42,
      system_cpu_percent: 19,
      readiness: 'attention',
    },
    after: completed
      ? {
          captured_at: now(),
          workload_active: false,
          workload_cpu_percent: 0,
          system_cpu_percent: 18,
          readiness: 'ready',
        }
      : null,
    verification: completed
      ? { process_exited: true, system_cpu_delta: -1, improved: true }
      : null,
    message:
      status === 'failed'
        ? 'Verification could not confirm the process exited.'
        : null,
  };
}
