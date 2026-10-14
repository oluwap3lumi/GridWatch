import { StrictMode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createRoot } from 'react-dom/client';
import { Dashboard } from './pages/Dashboard';
import './styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('GridWatch root element is missing');
const queryClient = new QueryClient();
createRoot(root).render(<StrictMode><QueryClientProvider client={queryClient}><Dashboard /></QueryClientProvider></StrictMode>);
