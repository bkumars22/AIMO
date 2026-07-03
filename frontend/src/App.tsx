import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard      from './pages/Dashboard'
import Incidents      from './pages/Incidents'
import IncidentDetail from './pages/IncidentDetail'
import PipelineDetail from './pages/PipelineDetail'
import Settings       from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"                 element={<Dashboard />} />
        <Route path="/incidents"        element={<Incidents />} />
        <Route path="/incidents/:id"    element={<IncidentDetail />} />
        <Route path="/pipelines/:id"    element={<PipelineDetail />} />
        <Route path="/settings"         element={<Settings />} />
      </Routes>
    </BrowserRouter>
  )
}
