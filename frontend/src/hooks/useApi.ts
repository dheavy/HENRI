import { useQuery } from '@tanstack/react-query';
import {
  fetchDashboard,
  fetchCountries,
  fetchSurges,
  fetchDelegations,
  fetchCountryDetail,
} from '../api/client';

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 60_000,
  });
}

export function useCountries(params?: string) {
  return useQuery({
    queryKey: ['countries', params],
    queryFn: () => fetchCountries(params),
  });
}

export function useCountryDetail(iso2: string) {
  return useQuery({
    queryKey: ['country', iso2],
    queryFn: () => fetchCountryDetail(iso2),
    enabled: !!iso2,
  });
}

export function useSurges(params?: string) {
  return useQuery({
    queryKey: ['surges', params],
    queryFn: () => fetchSurges(params),
  });
}

export function useDelegations(params?: string) {
  return useQuery({
    queryKey: ['delegations', params],
    queryFn: () => fetchDelegations(params),
  });
}
