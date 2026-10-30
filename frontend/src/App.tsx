import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, RequireAuth } from './auth/AuthProvider'
import { AppLayout } from './components/AppLayout'
import { BomDetailPage } from './pages/BomDetailPage'
import { CreateBomPage } from './pages/CreateBomPage'
import { LoginPage } from './pages/LoginPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { OrderPage } from './pages/OrderPage'
import { QueuePage } from './pages/QueuePage'
import { SignTypePage } from './pages/SignTypePage'
import { TemplateEditorPage } from './pages/TemplateEditorPage'
import { TemplatesPage } from './pages/TemplatesPage'

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<QueuePage />} />
            <Route path="/orders/:orderId" element={<OrderPage />} />
            <Route path="/orders/:orderId/bom" element={<CreateBomPage />} />
            <Route path="/boms/:bomId" element={<BomDetailPage />} />
            <Route path="/templates" element={<TemplatesPage />} />
            <Route path="/templates/:templateId" element={<TemplateEditorPage />} />
            <Route path="/sign-types/:signTypeId" element={<SignTypePage />} />
            <Route path="/inventory" element={<PlaceholderPage page="inventory" />} />
            <Route path="/sync" element={<PlaceholderPage page="sync" />} />
            <Route path="/reports" element={<PlaceholderPage page="reports" />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}
