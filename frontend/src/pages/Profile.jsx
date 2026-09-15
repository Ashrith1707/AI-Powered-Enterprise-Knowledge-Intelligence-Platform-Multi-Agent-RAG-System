import { useState } from 'react'
import { api } from '../api/client'
import { ErrorBanner, PageHeader } from '../components/ui'
import { useAuth } from '../context/AuthContext'

export default function Profile() {
  const { user, reload } = useAuth()
  const [fullName, setFullName] = useState(user?.full_name || '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const saveName = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null); setMessage(null)
    try {
      await api.patch('/auth/me', { full_name: fullName })
      await reload()
      setMessage('Profile updated.')
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  const changePassword = async (e) => {
    e.preventDefault()
    setError(null); setMessage(null)
    if (password !== confirm) { setError({ message: 'Passwords do not match.', code: 'validation_error' }); return }
    setBusy(true)
    try {
      await api.patch('/auth/me', { password })
      setPassword(''); setConfirm('')
      setMessage('Password changed successfully.')
    } catch (err) { setError(err) } finally { setBusy(false) }
  }

  return (
    <div className="max-w-xl">
      <PageHeader title="Profile" subtitle="Your account details" />
      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      {message && (
        <div className="mb-4 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-2.5 text-sm text-emerald-300">
          ✓ {message}
        </div>
      )}

      <div className="card mb-4 p-5">
        <div className="mb-4 flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-600/20 text-xl font-bold text-brand-300">
            {(user?.full_name || user?.email || '?')[0].toUpperCase()}
          </div>
          <div>
            <div className="text-sm font-bold text-white">{user?.email}</div>
            <div className="text-xs text-slate-500">
              Role: <span className="badge bg-slate-800 text-slate-300">{user?.role}</span>
              {user?.created_at && <span className="ml-2">Joined {new Date(user.created_at).toLocaleDateString()}</span>}
            </div>
          </div>
        </div>
        <form onSubmit={saveName} className="space-y-3">
          <div>
            <label className="label">Full name</label>
            <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={160} />
          </div>
          <button className="btn-primary" disabled={busy}>Save name</button>
        </form>
      </div>

      <div className="card p-5">
        <h3 className="mb-3 text-sm font-semibold text-slate-300">Change password</h3>
        <form onSubmit={changePassword} className="space-y-3">
          <div>
            <label className="label">New password</label>
            <input className="input" type="password" required minLength={8} value={password}
                   onChange={(e) => setPassword(e.target.value)} placeholder="min 8 chars, letters + numbers" />
          </div>
          <div>
            <label className="label">Confirm new password</label>
            <input className="input" type="password" required value={confirm}
                   onChange={(e) => setConfirm(e.target.value)} />
          </div>
          <button className="btn-primary" disabled={busy || !password}>Change password</button>
        </form>
      </div>
    </div>
  )
}
