const BASE = '/api/v1';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ── Types ────────────────────────────────────────────────────────────

export interface Alert {
  type: string;
  severity: string;
  country: string;
  message: string;
  delegations_at_risk: string[];
  detected_at: string;
}

export interface DeltaAlert {
  country: string;
  old_score: number;
  new_score: number;
  delta: number;
  direction: string;
  primary_driver: string;
}

export interface RiskCard {
  country: string;
  country_iso3: string;
  acled_events: number;
  acled_fatalities: number;
  ioda_score: number;
  cf_outages: number;
  snow_sitedown: number;
  combined_risk: number;
}

export interface DashboardResponse {
  generated_at: string;
  alerts: Alert[];
  delta_alerts: DeltaAlert[];
  risk_summary: { high: number; medium: number; low: number; minimal: number };
  risk_cards: RiskCard[];
  pipeline_status: {
    last_run: string;
    sources: Record<string, { status: string; last_pull: string | null; metric?: string | null }>;
  };
  bandwidth_top: { site: string; peak_mbps: number; avg_mbps: number; utilisation_pct: number | null }[];
  data_coherence: {
    netbox_sites: number;
    grafana_sites: number;
    circuits_total: number;
    circuits_with_rate: number;
    silent_sites: number;
  } | null;
}

export interface Country {
  iso2: string;
  iso3: string;
  name: string;
  risk_score: number;
  risk_tier: string;
  acled_events: number;
  acled_fatalities: number;
  acled_trend: string;
  ioda_score: number;
  cf_outages: number;
  snow_sitedown: number;
  delegations: string[];
}

export interface CountriesResponse {
  countries: Country[];
}

export interface Surge {
  id: number;
  date: string;
  region: string;
  delegations: string[];
  countries: string[];
  score: number;
  precursors: {
    acled: { detected: boolean; events: number; ratio: number };
    ioda: { detected: boolean; alerts: number };
    cloudflare: { detected: boolean; events: number };
    internal: { detected: boolean; latency_alerts: number };
  };
  lead_time_h: number | null;
  any_precursor: boolean;
}

export interface SurgesResponse {
  surges: Surge[];
  stats: {
    total_surges: number;
    with_external_precursor: number;
    pct_with_precursor: number;
    avg_lead_time_hours: number;
  };
}

export interface Delegation {
  site_code: string;
  name: string;
  region: string;
  country: string;
  country_iso2: string;
  source: string;
  sub_sites: string[];
  circuits: { cid: string; provider: string; commit_rate_fmt: string }[];
  incident_count_30d: number;
  sitedown_count_30d: number;
  dominant_alert: string;
}

export interface DelegationsResponse {
  delegations: Delegation[];
  total: number;
}

// ── Fetchers ─────────────────────────────────────────────────────────

export const fetchDashboard = () =>
  fetchJson<DashboardResponse>(`${BASE}/dashboard`);

export const fetchCountries = (params?: string) =>
  fetchJson<CountriesResponse>(`${BASE}/countries${params ? '?' + params : ''}`);

export const fetchCountryDetail = (iso2: string) =>
  fetchJson<Record<string, unknown>>(`${BASE}/countries/${iso2}`);

export const fetchSurges = (params?: string) =>
  fetchJson<SurgesResponse>(`${BASE}/surges${params ? '?' + params : ''}`);

export const fetchDelegations = (params?: string) =>
  fetchJson<DelegationsResponse>(`${BASE}/delegations${params ? '?' + params : ''}`);

// ── Connectivity ────────────────────────────────────────────────────

export interface ConnectivityLink {
  cid: string;
  link_type: string | null;
  provider: string | null;
  effective_mbps: number;
  mathis_mbps: number;
  capacity_mbps: number | null;
  rtt_ms: number;
  rtt_source: string;
  loss: number;
  loss_source: string;
  is_primary: boolean;
}

export interface ConnectivitySite {
  site_code: string;
  country: string;
  region: string;
  score: number;
  grade: string;
  etu_mbps: number;
  etu_raw_mbps: number;
  num_users: number;
  num_users_source: string;
  num_links: number;
  jitter_penalty: number;
  availability_penalty: number;
  diversity_bonus: number;
  data_completeness: number;
  missing_data: string[];
  limiting_factor: string;
  links: ConnectivityLink[];
}

export interface ConnectivityResponse {
  sites: ConnectivitySite[];
  summary: {
    total_sites: number;
    scored_sites: number;
    by_grade: Record<string, number>;
    avg_completeness: number;
  };
  coverage: {
    has_bandwidth: number;
    has_circuits: number;
    has_rtt: number;
    has_loss: number;
    has_jitter: number;
    has_dhcp: number;
    has_availability: number;
    full_data: number;
    total_sites: number;
  };
}

export const fetchConnectivity = () =>
  fetchJson<ConnectivityResponse>(`${BASE}/connectivity`);

// ── Pipeline ─────────────────────────────────────────────────────────

export interface PipelineStatus {
  running: boolean;
  status: 'idle' | 'running' | 'done' | 'error';
  started_at: number | null;
  finished_at: number | null;
  error: string | null;
}

export const fetchPipelineStatus = () =>
  fetchJson<PipelineStatus>(`${BASE}/pipeline/status`);

export async function triggerRegenerate(): Promise<{ accepted: boolean; reason?: string }> {
  const res = await fetch(`${BASE}/pipeline/regenerate`, { method: 'POST' });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
