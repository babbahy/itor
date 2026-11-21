import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const maxBody = 16_384;
const identifier = "[a-zA-Z0-9_-]{1,100}";
const routes = {
  GET: [
    /^(health|status|activity|insights|privacy|fixes|incidents)$/,
    /^device\/(snapshot|history|capabilities|readiness)$/,
    /^worktime\/(today|week)$/,
    /^company\/(status|team)$/,
    /^support\/tickets$/,
    new RegExp(`^fixes/runs/${identifier}$`),
    /^demo\/status$/,
    /^connectivity$/,
    new RegExp(`^preflight/${identifier}$`),
    new RegExp(`^actions/${identifier}$`),
  ],
  POST: [
    /^(preflight|diagnose)$/,
    /^diagnosis\/chat$/,
    /^demo\/(start|stop|reset|cloud|worktime)$/,
    /^worktime\/blocked$/,
    /^company\/send$/,
    /^support\/ticket$/,
    /^fixes\/(flush_dns|restart_wifi)\/plan$/,
    new RegExp(`^fixes/runs/${identifier}/(approve|cancel)$`),
    /^actions\/plan$/,
    /^connectivity\/check$/,
    new RegExp(`^actions/${identifier}/(approve|cancel)$`),
  ],
  DELETE: [/^privacy\/history$/],
} as const;

const safeHeaders = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Cross-Origin-Resource-Policy": "same-origin",
};

function failure(status: number, detail: string) {
  return Response.json({ detail }, { status, headers: safeHeaders });
}

function localOrigin(value: string): URL {
  const url = new URL(value);
  if (
    url.protocol !== "http:" ||
    !["127.0.0.1", "localhost"].includes(url.hostname) ||
    url.username || url.password || url.pathname !== "/" || url.search || url.hash
  ) {
    throw new Error("Expected a loopback origin");
  }
  return url;
}

async function requestBody(request: NextRequest) {
  if (Number(request.headers.get("content-length")) > maxBody) return null;
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks: Uint8Array<ArrayBufferLike>[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maxBody) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(method: keyof typeof routes, request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const target = path.join("/");
  if (!routes[method].some((pattern) => pattern.test(target))) {
    return failure(404, "This device-agent route is unavailable.");
  }

  let web: URL;
  let agent: URL;
  try {
    web = localOrigin(process.env.ITOR_WEB_ORIGIN || "http://127.0.0.1:3000");
    agent = localOrigin(process.env.ITOR_AGENT_URL || "http://127.0.0.1:8765");
  } catch {
    return failure(503, "itor needs valid loopback addresses for the app and device agent.");
  }
  const requestOrigin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (
    request.headers.get("host") !== web.host ||
    (fetchSite && fetchSite !== "same-origin" && fetchSite !== "none") ||
    (requestOrigin !== null && requestOrigin !== web.origin) ||
    (method !== "GET" && requestOrigin !== web.origin)
  ) {
    return failure(403, "Open itor from its configured local address.");
  }

  const key = process.env.ITOR_AGENT_KEY;
  if (!key) return failure(503, "Start itor with the local launcher to connect the device agent.");

  const headers = new Headers({ Accept: "application/json", "X-Itor-Key": key });
  let body: Uint8Array<ArrayBuffer> | undefined;
  if (method === "POST") {
    if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
      return failure(415, "Send a JSON request.");
    }
    const bytes = await requestBody(request);
    if (!bytes) return failure(413, "This request is too large.");
    body = bytes;
    headers.set("Content-Type", "application/json");
  }

  try {
    const url = new URL(`/api/${target}`, agent);
    url.search = request.nextUrl.search;
    const response = await fetch(url, {
      method,
      body,
      headers,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(180_000),
    });
    return new Response(response.body, {
      status: response.status,
      headers: { ...safeHeaders, "Content-Type": "application/json" },
    });
  } catch {
    return failure(503, "Device agent unavailable. Check that the local launcher is still running.");
  }
}

export function GET(request: NextRequest, context: RouteContext) {
  return forward("GET", request, context);
}

export function POST(request: NextRequest, context: RouteContext) {
  return forward("POST", request, context);
}

export function DELETE(request: NextRequest, context: RouteContext) {
  return forward("DELETE", request, context);
}
