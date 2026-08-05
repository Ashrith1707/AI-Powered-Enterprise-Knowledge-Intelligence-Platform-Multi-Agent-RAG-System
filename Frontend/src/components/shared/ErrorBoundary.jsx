import { Component } from 'react'
import { RefreshCcw, ServerCrash } from 'lucide-react'

export class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('UI crash:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6 text-center">
        <div className="mb-4 rounded-2xl bg-danger-soft p-4">
          <ServerCrash className="h-8 w-8 text-danger" />
        </div>
        <h1 className="text-lg font-semibold text-ink">Something broke in the UI</h1>
        <p className="mt-1.5 max-w-md text-sm text-muted">{String(this.state.error?.message ?? this.state.error)}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          <RefreshCcw className="h-4 w-4" /> Reload application
        </button>
      </div>
    )
  }
}
