import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'

// Lazy load pages
const Dashboard = lazy(() => import('./pages/Dashboard'))
const AgentConsole = lazy(() => import('./pages/AgentConsole'))
const Admin = lazy(() => import('./pages/Admin'))
const Skills = lazy(() => import('./pages/Skills'))
const WorkflowEditor = lazy(() => import('./pages/WorkflowEditor'))

// 통합 페이지 (신규)
const DocumentManager = lazy(() => import('./pages/DocumentManager'))
const KnowledgeSearch = lazy(() => import('./pages/KnowledgeSearch'))
const AccountSettings = lazy(() => import('./pages/AccountSettings'))

// 레거시 (리다이렉트용)
const VaultExplorer = lazy(() => import('./pages/VaultExplorer'))
const Ingestion = lazy(() => import('./pages/Ingestion'))
const Search = lazy(() => import('./pages/Search'))
const KnowledgeGraph = lazy(() => import('./pages/KnowledgeGraph'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="w-6 h-6 border-2 border-gold-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="agent" element={<AgentConsole />} />
            <Route path="docs" element={<DocumentManager />} />
            <Route path="knowledge" element={<KnowledgeSearch />} />
            <Route path="workflow" element={<WorkflowEditor />} />
            <Route path="skills" element={<Skills />} />
            <Route path="settings" element={<AccountSettings />} />
            <Route path="admin" element={<Admin />} />

            {/* 레거시 경로 리다이렉트 */}
            <Route path="vault" element={<Navigate to="/docs" replace />} />
            <Route path="ingest" element={<Navigate to="/docs" replace />} />
            <Route path="search" element={<Navigate to="/knowledge" replace />} />
            <Route path="graph" element={<Navigate to="/knowledge" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
