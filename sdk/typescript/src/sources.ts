import type { PackSpec } from "./index.js";

/** Source selection is explicit: no fallback to weaker embedded policies. */
export type PackSpecMode = "internal" | "property" | "file" | "studio";
export type PackSpecLoader = () => Promise<PackSpec>;
export interface SourceOptions {
  mode: PackSpecMode;
  internalPack?: PackSpec;
  json?: string;
  path?: string;
  /** Server-side file loader; application supplies fs adapter. */
  readFile?: (path: string) => Promise<string>;
  registryUrl?: string;
  registryToken?: string;
  serviceId?: string;
  environment?: string;
  /** Inject fetch for testing / server use. Never expose operator tokens in browsers. */
  request?: typeof fetch;
}
const maxBytes = 262_144;
const segment = /^[A-Za-z0-9._-]+$/;

function validate(value: unknown): PackSpec {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid PackSpec");
  const p = value as PackSpec;
  if (typeof p.id !== "string" || !p.id.trim() ||
      typeof p.version !== "string" || !p.version.trim() ||
      !Array.isArray(p.requirements) || !p.requirements.length) throw new Error("Invalid PackSpec");
  const ids = new Set<string>();
  for (const r of p.requirements) {
    if (!r || typeof r.id !== "string" || !r.id || ids.has(r.id)) throw new Error("Invalid requirement");
    ids.add(r.id);
    if (r.min_independent_sources !== undefined &&
      (!Number.isInteger(r.min_independent_sources) || r.min_independent_sources < 1)) throw new Error("Invalid minimum");
    if (r.max_age_seconds !== undefined &&
      (!Number.isInteger(r.max_age_seconds) || r.max_age_seconds < 0)) throw new Error("Invalid maximum age");
  }
  return p;
}
function parse(json: string): PackSpec { return validate(JSON.parse(json)); }
function required(value: string | undefined, label: string): string {
  if (!value?.trim()) throw new Error(label + " required");
  return value;
}
export function packSpecSource(options: SourceOptions): PackSpecLoader {
  if (options.mode === "internal" || options.mode === "property") {
    const snapshot = options.mode === "internal"
      ? JSON.stringify(validate(options.internalPack))
      : JSON.stringify(parse(required(options.json, "Inline PackSpec")));
    return async () => parse(snapshot);
  }
  if (options.mode === "file") {
    const path = required(options.path, "PackSpec path");
    if (!options.readFile) throw new Error("File loader adapter required");
    return async () => {
      const json = await options.readFile!(path);
      if (new TextEncoder().encode(json).length > maxBytes) throw new Error("PackSpec file too large");
      return parse(json);
    };
  }
  if (options.mode === "studio") {
    const url = new URL(required(options.registryUrl, "Registry URL"));
    if (!(url.protocol === "https:" || (url.protocol === "http:" &&
      ["localhost", "127.0.0.1"].includes(url.hostname)))) throw new Error("HTTPS required outside loopback");
    if (url.username || url.password || url.search || url.hash) throw new Error("Invalid registry URL");
    const token = required(options.registryToken, "Registry credential");
    const service = required(options.serviceId, "Service ID");
    const environment = required(options.environment, "Environment");
    if (!segment.test(service) || !segment.test(environment)) throw new Error("Invalid service/environment");
    const endpoint = new URL("/v1/resolve/" + service + "/" + environment, url).toString();
    const request = options.request || fetch;
    return async () => {
      const response = await request(endpoint, {
        headers: { Authorization: "Bearer " + token, Accept: "application/json" },
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error("Registry policy resolution failed");
      const body = await response.text();
      if (new TextEncoder().encode(body).length > maxBytes) throw new Error("Registry response too large");
      const envelope = JSON.parse(body);
      if (envelope.status !== "APPROVED" || envelope.serviceId !== service ||
          envelope.environment !== environment) throw new Error("Registry binding mismatch");
      const policy = validate(envelope.policy);
      const expected = envelope.sha256;
      if (typeof expected !== "string" || !/^[0-9a-f]{64}$/.test(expected)) throw new Error("Missing registry digest");
      const data = new TextEncoder().encode(JSON.stringify(policy));
      const digest = await crypto.subtle.digest("SHA-256", data);
      const actual = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
      if (actual !== expected) throw new Error("Registry digest mismatch");
      return policy;
    };
  }
  throw new Error("Explicit PackSpec source required");
}
