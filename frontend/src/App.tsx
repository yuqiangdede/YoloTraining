import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { AnnotationPage } from './pages/AnnotationPage'
import { AnalysisPage } from './pages/AnalysisPage'
import { DashboardPage } from './pages/DashboardPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { DatasetWorkspacePage } from './pages/DatasetWorkspacePage'
import { ModelsPage } from './pages/ModelsPage'
import { ModelTestPage } from './pages/ModelTestPage'
import { ProjectPage, ProjectsPage } from './pages/ProjectsPage'
import { SystemPage } from './pages/SystemPage'
import { TrainingPage } from './pages/TrainingPage'

export function App() {
  return <Routes><Route element={<AppShell />}>
    <Route index element={<DashboardPage />} />
    <Route path="projects" element={<ProjectsPage />} />
    <Route path="projects/:projectId" element={<ProjectPage />} />
    <Route path="datasets/:datasetId" element={<DatasetWorkspacePage />} />
    <Route path="datasets/:datasetId/annotate" element={<AnnotationPage />} />
    <Route path="datasets/:datasetId/analysis" element={<AnalysisPage />} />
    <Route path="datasets" element={<DatasetsPage />} />
    <Route path="training" element={<TrainingPage />} />
    <Route path="models" element={<ModelsPage />} />
    <Route path="models/test" element={<ModelTestPage />} />
    <Route path="system" element={<SystemPage />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Route></Routes>
}
