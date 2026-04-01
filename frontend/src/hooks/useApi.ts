import { useQuery } from '@tanstack/react-query';
import {
  fetchDashboard,
  fetchCountries,
  fetchSurges,
  fetchDelegations,
  fetchCountryDetail,
} from '../api/client';

// Dashboard refreshes every 60s, all others every 30 minutes (for overnight sessions)
const REFRESH_FAST = 60_000;
const REFRESH_SLOW = 30 * 60_000;

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: REFRESH_FAST,
  });
}

export function useCountries(params?: string) {
  return useQuery({
    queryKey: ['countries', params],
    queryFn: () => fetchCountries(params),
    refetchInterval: REFRESH_SLOW,
  });
}

export function useCountryDetail(iso2: string) {
  return useQuery({
    queryKey: ['country', iso2],
    queryFn: () => fetchCountryDetail(iso2),
    enabled: !!iso2,
    refetchInterval: REFRESH_SLOW,
  });
}

export function useSurges(params?: string) {
  return useQuery({
    queryKey: ['surges', params],
    queryFn: () => fetchSurges(params),
    refetchInterval: REFRESH_SLOW,
  });
}

export function useDelegations(params?: string) {
  return useQuery({
    queryKey: ['delegations', params],
    queryFn: () => fetchDelegations(params),
    refetchInterval: REFRESH_SLOW,
  });
}
