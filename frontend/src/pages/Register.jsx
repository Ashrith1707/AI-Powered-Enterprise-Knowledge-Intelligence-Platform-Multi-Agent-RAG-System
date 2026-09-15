import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ErrorBanner } from '../components/ui'
import { useAuth } from '../context/AuthContext'

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ fullName: '', email: '', password: '', confirm: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (form.password !== form.confirm) {
      setError({ message: 'Passwords do not match.', code: 'validation_error' })
      return
    }
    setBusy(true)
    try {
      await register(form.email, form.password, form.fullName)
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
          <h1 className="text-2xl font-bold text-white">Create your account</h1>
          <p className="mt-1 text-sm text-slate-400">The first account becomes the workspace admin.</p>
        </div>

        <form onSubmit={submit} className="card space-y-4 p-6 shadow-xl">
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
          <div>
            <label className="label">Full name</label>
            <input className="input" required value={form.fullName} onChange={set('fullName')} placeholder="Ada Lovelace" />
          </div>
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" required value={form.email} onChange={set('email')} placeholder="you@company.com" />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" required minLength={8} value={form.password} onChange={set('password')}
                   placeholder="min 8 chars, letters + numbers" />
          </div>
          <div>
            <label className="label">Confirm password</label>
            <input className="input" type="password" required value={form.confirm} onChange={set('confirm')} placeholder="repeat password" />
          </div>
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? 'Creating account…' : 'Create account'}
          </button>
          <p className="text-center text-xs text-slate-500">
            Already registered?{' '}
            <Link to="/login" className="font-medium text-brand-400 hover:text-brand-300">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
