import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import Dashboard from './pages/Dashboard'
import VaultExplorer from './pages/VaultExplorer'
import AgentConsole from './pages/AgentConsole'
import Ingestion from './pages/Ingestion'
import Search from './pages/Search'
import Admin from './pages/Admin'
import KnowledgeGraph from './pages/KnowledgeGraph'
import Skills from './pages/Skills'
import WorkflowEditor from './pages/WorkflowEditor'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="vault" element={<VaultExplorer />} />
          <Route path="agent" element={<AgentConsole />} />
          <Route path="workflow" element={<WorkflowEditor />} />
          <Route path="ingest" element={<Ingestion />} />
          <Route path="search" element={<Search />} />
          <Route path="admin" element={<Admin />} />
          <Route path="graph" element={<KnowledgeGraph />} />
          <Route path="skills" element={<Skills />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
