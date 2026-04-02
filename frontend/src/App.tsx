import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Country from './pages/Country';
import Surges from './pages/Surges';
import Delegations from './pages/Delegations';
import Report from './pages/Report';
import Connectivity from './pages/Connectivity';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/country/:iso2" element={<Country />} />
            <Route path="/surges" element={<Surges />} />
            <Route path="/delegations" element={<Delegations />} />
            <Route path="/connectivity" element={<Connectivity />} />
            <Route path="/report" element={<Report />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
