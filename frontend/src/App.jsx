import AuthPage from './components/AuthPage'
import Dashboard from './Dashboard'
import { useRoute } from './hooks/useRoute'

/** Picks the screen from the address bar: the sign-in / sign-up page, or the dashboard. */
export default function App() {
  const route = useRoute()

  // Kept separate so the dashboard's live feed and data loading only run while it is on screen.
  return route === 'home' ? <Dashboard /> : <AuthPage route={route} />
}
