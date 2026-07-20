import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { CreateGamePage } from './pages/CreateGamePage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { GameMapPage } from './pages/GameMapPage'
import { GamesListPage } from './pages/GamesListPage'
import { HealthPage } from './pages/HealthPage'
import { JoinGamePage } from './pages/JoinGamePage'
import { LobbyPage } from './pages/LobbyPage'
import { MapPage } from './pages/MapPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/health" element={<HealthPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<GamesListPage />} />
          <Route path="/games/new" element={<CreateGamePage />} />
          <Route path="/games/:gameId" element={<LobbyPage />} />
          <Route path="/games/:gameId/map" element={<GameMapPage />} />
          <Route path="/join/:inviteCode" element={<JoinGamePage />} />
          <Route path="/map" element={<MapPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
