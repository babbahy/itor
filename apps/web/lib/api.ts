import { z } from 'zod';

const timestamp = z.iso.datetime({ offset: true });
const metric = z.number().nullable();

export const meetingSchema = z.object({
  id: z.string(),
  title: z.string(),
  start_at: timestamp,
  end_at: timestamp,
  platform: z.string(),
  join_url: z.string().nullable(),
  notes: z.string().nullable(),
  source: z.enum(['demo', 'manual']),
});
export const meetingsSchema = z.array(meetingSchema);
export const workloadSchema = z.object({
  active: z.boolean(),
  id: z.string().nullish(),
  cpu_percent: metric.optional(),
  memory_bytes: metric.optional(),
  started_at: timestamp.nullish(),
  expires_at: timestamp.nullish(),
});
export const snapshotSchema = z.object({
  id: z.string(),
  captured_at: timestamp,
  source: z.string(),
  cpu_percent: metric,
  cpu_logical: metric,
  cpu_physical: metric,
  memory_percent: metric,
  memory_total: metric,
  memory_available: metric,
  disk_percent: metric,
  disk_total: metric,
  disk_free: metric,
  workload: workloadSchema,
  network_up: z.boolean().nullable(),
  errors: z.array(z.string()),
});
export const historySchema = z.array(snapshotSchema);
export const findingSchema = z.object({
  id: z.string(),
  category: z.string(),
  severity: z.string(),
  title: z.string(),
  evidence: z.union([z.string(), z.array(z.string())]),
  window_seconds: z.number().nullish(),
  potential_impact: z.string(),
  recommended_action_ids: z.array(z.string()),
  source: z.string(),
  limitations: z.union([z.string(), z.array(z.string())]).nullish(),
});
export const checkSchema = z.object({
  id: z.string(),
  label: z.string(),
  state: z.enum(['passed', 'warning', 'unknown', 'unsupported']),
  detail: z.string(),
});
export const readinessSchema = z.object({
  readiness: z.enum(['ready', 'attention', 'not_ready', 'unknown']),
  findings: z.array(findingSchema),
  snapshot: snapshotSchema,
  checks: z.array(checkSchema),
});
export const preflightSchema = readinessSchema.extend({
  id: z.string(),
  meeting_id: z.string().nullable(),
  started_at: timestamp,
  completed_at: timestamp,
  status: z.literal('completed'),
});
export const diagnosisSchema = z.object({
  status: z.string(),
  provider: z.enum(['ollama', 'rules']),
  model: z.string().nullable(),
  headline: z.string(),
  explanation: z.string(),
  observed_facts: z.array(z.string()),
  possible_causes: z.array(z.string()),
  potential_impact: z.string(),
  recommended_action_id: z.string().nullable(),
  action_explanation: z.string(),
  uncertainty: z.string(),
  verification_advice: z.string(),
  safe_steps: z.array(z.string()).default([]),
});
const summarySchema = z.object({
  captured_at: timestamp,
  system_cpu_percent: metric,
  workload_cpu_percent: metric,
  workload_active: z.boolean(),
  readiness: z.string(),
});
export const actionSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  action_id: z.string(),
  status: z.enum([
    'proposed',
    'awaiting_approval',
    'approved',
    'executing',
    'verifying',
    'succeeded',
    'failed',
    'canceled',
    'expired',
  ]),
  title: z.string(),
  scope: z.string(),
  expected_result: z.string(),
  side_effects: z.string(),
  expires_at: timestamp,
  approval_token: z.string().nullish(),
  before: summarySchema.nullish(),
  after: summarySchema.nullish(),
  verification: z
    .object({
      process_exited: z.boolean(),
      system_cpu_delta: metric,
      improved: z.boolean(),
    })
    .nullish(),
  message: z.string().nullish(),
});
export const serviceSchema = z.object({
  name: z.string(),
  state: z.enum([
    'connected',
    'disconnected',
    'unreachable',
    'authentication_error',
    'degraded',
    'checking',
    'unknown',
    'not_configured',
  ]),
  last_success_at: timestamp.nullish(),
  last_checked_at: timestamp.nullish(),
  duration_ms: z.number().nullish(),
  error_category: z.string().nullish(),
  explanation: z.string(),
  configured: z.boolean(),
});
export const connectivitySchema = z.object({
  agent: serviceSchema,
  ollama: serviceSchema,
  network_interface: serviceSchema,
  gateway: serviceSchema,
  dns_resolver: serviceSchema,
  dns: serviceSchema,
  internet: serviceSchema,
  nexthink: serviceSchema,
  nexthink_reachability: serviceSchema.optional(),
  nexthink_auth: serviceSchema.optional(),
  ollama_loading: z.boolean().default(false),
  offline_rescue: z.boolean(),
  simulated_cloud_outage: z.boolean(),
  updated_at: timestamp,
  cloud_data_stale: z.boolean(),
  cloud_last_updated_at: timestamp.nullish(),
});
export const statusSchema = z.object({
  agent: z.string(),
  telemetry: z.string(),
  remediation: z.string(),
  mode: z.string(),
  connectivity: connectivitySchema,
  demo: workloadSchema,
  model: z.string().nullish(),
});
export const activitySchema = z.array(
  z.object({
    id: z.string(),
    kind: z.string(),
    created_at: timestamp,
    title: z.string(),
    detail: z.string(),
  }),
);
export const privacySchema = z.object({
  retention_days: z.number().optional(),
  model: z.string().nullish(),
  inference_location: z.string().optional(),
  telemetry_sources: z.array(z.string()).optional(),
  stored_data: z.array(z.string()).optional(),
  external_connections: z.array(z.string()).optional(),
  sync: z
    .object({
      state: z.string(),
      configured: z.boolean(),
      pending_events: z.number(),
      failed_events: z.number(),
      last_sync_at: timestamp.nullish(),
    })
    .optional(),
});
export const insightsSchema = z
  .object({
    preflights: z.number().optional(),
    findings: z.number().optional(),
    verified_actions: z.number().optional(),
    recent_readiness: readinessSchema.shape.readiness.nullish(),
  })
  .passthrough();
export const resetSchema = z.object({
  workload: workloadSchema,
  meetings: meetingsSchema,
});

export type Meeting = z.infer<typeof meetingSchema>;
export type Snapshot = z.infer<typeof snapshotSchema>;
export type Finding = z.infer<typeof findingSchema>;
export type Readiness = z.infer<typeof readinessSchema>;
export type InsightsData = z.infer<typeof insightsSchema>;
export type Preflight = z.infer<typeof preflightSchema>;
export type Action = z.infer<typeof actionSchema>;
export type Diagnosis = z.infer<typeof diagnosisSchema>;
export type Connectivity = z.infer<typeof connectivitySchema>;
export type ServiceStatus = z.infer<typeof serviceSchema>;
export type Activity = z.infer<typeof activitySchema>;

export async function api<T>(
  schema: z.ZodType<T>,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    ...init,
    cache: 'no-store',
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => undefined);
    const error = z.object({ detail: z.string() }).safeParse(data);
    if (response.status >= 502)
      throw new Error(
        'The local device agent is unavailable. Start it and try again.',
      );
    if (response.status === 422 && !error.success)
      throw new Error('Review the form and try again.');
    throw new Error(
      error.success
        ? error.data.detail
        : `The request failed (${response.status}).`,
    );
  }
  if (response.status === 204) return schema.parse(undefined);
  const parsed = schema.safeParse(await response.json());
  if (!parsed.success)
    throw new Error('The local agent returned an unexpected response.');
  return parsed.data;
}

export const post = <T>(
  schema: z.ZodType<T>,
  path: string,
  body: object = {},
) => api(schema, path, { method: 'POST', body: JSON.stringify(body) });
