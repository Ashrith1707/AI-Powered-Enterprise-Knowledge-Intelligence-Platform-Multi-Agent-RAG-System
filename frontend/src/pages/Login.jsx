import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ErrorBanner } from '../components/ui'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-brand-950/40 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-2xl font-black text-white shadow-lg shadow-brand-600/30">
            K
          </div>
          <h1 className="text-2xl font-bold text-white">KnowledgeIQ</h1>
          <p className="mt-1 text-sm text-slate-400">Enterprise Knowledge Intelligence Platform</p>
        </div>

        <form onSubmit={submit} className="card space-y-4 p-6 shadow-xl">
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" required value={email}
                   onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" required value={password}
                   onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
          </div>
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="text-center text-xs text-slate-500">
            No account?{' '}
            <Link to="/register" className="font-medium text-brand-400 hover:text-brand-300">Create one</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
