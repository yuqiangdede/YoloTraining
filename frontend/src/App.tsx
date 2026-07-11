import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { AnnotationPage } from './pages/AnnotationPage'
import { AssetsPage } from './pages/AssetsPage'
import { DashboardPage } from './pages/DashboardPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { ModelsPage } from './pages/ModelsPage'
import { SystemPage } from './pages/SystemPage'
import { TrainingPage } from './pages/TrainingPage'

export function App() {
  return <Routes><Route element={<AppShell />}>
    <Route index element={<DashboardPage />} />
    <Route path="assets" element={<AssetsPage />} />
    <Route path="annotate" element={<AnnotationPage />} />
    <Route path="datasets" element={<DatasetsPage />} />
    <Route path="training" element={<TrainingPage />} />
    <Route path="models" element={<ModelsPage />} />
    <Route path="system" element={<SystemPage />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Route></Routes>
}
