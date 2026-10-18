import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import Home from './Home.tsx'
import Research from './Research.tsx'

// The globe pulls in three.js, so load it only when someone opens the app.
const App = lazy(() => import('./App.tsx'))

type Route = 'home' | 'app' | 'research'

function routeFromHash(): Route {
  const hash = window.location.hash.replace(/^#\/?/, '')
  if (hash === 'app') return 'app'
  if (hash === 'research') return 'research'
  return 'home'
}

class ViewErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="status status-error">
          This view needs WebGL. The orbit map cannot draw without it.
        </div>
      )
    }
    return this.props.children
  }
}

export default function Root() {
  const [route, setRoute] = useState<Route>(routeFromHash)

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (next: Route) => {
    window.location.hash = next === 'home' ? '/' : `/${next}`
  }

  if (route === 'app') {
    return (
      <ViewErrorBoundary>
        <Suspense fallback={<div className="status">Loading orbits</div>}>
          <App />
        </Suspense>
      </ViewErrorBoundary>
    )
  }
  if (route === 'research') return <Research onBack={() => go('home')} />
  return <Home onStart={() => go('app')} onResearch={() => go('research')} />
}
