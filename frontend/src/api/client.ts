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
    sources: Record<string, { status: string; last_pull: string | null }>;
  };
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
