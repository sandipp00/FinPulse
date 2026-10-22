import AuthPage from './components/AuthPage'
import Dashboard from './Dashboard'
import { useRoute } from './hooks/useRoute'
import { AUTH_ROUTES } from './lib/routes'

/** Picks the screen from the address bar: the sign-in / sign-up page, or a dashboard page. */
export default function App() {
  const route = useRoute()

  // Kept separate so the dashboard's live feed and data loading only run while it is on screen.
  return AUTH_ROUTES.includes(route) ? <AuthPage route={route} /> : <Dashboard route={route} />
}
