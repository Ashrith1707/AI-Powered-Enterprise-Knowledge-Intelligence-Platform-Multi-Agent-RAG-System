import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '▦' },
  { to: '/documents', label: 'Documents', icon: '🗎' },
  { to: '/search', label: 'Search', icon: '🔍' },
  { to: '/ask', label: 'Ask AI', icon: '✦' },
  { to: '/analytics', label: 'Analytics', icon: '📈' },
  { to: '/reports', label: 'Reports', icon: '🧾' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [aiMode, setAiMode] = useState(null)

  useEffect(() => {
    api.get('/chat/mode').then(setAiMode).catch(() => setAiMode(null))
  }, [])

  const isMock = aiMode?.llm?.provider === 'mock'

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 flex w-60 flex-col border-r border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 font-bold text-white">K</div>
          <div>
            <div className="text-sm font-bold tracking-tight text-white">KnowledgeIQ</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Multi-Agent RAG</div>
          </div>
        </div>

        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
            >
              <span className="w-5 text-center">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-800 p-4">
          {aiMode && (
            <div
              className={`badge mb-3 w-full justify-center ${isMock ? 'bg-amber-500/10 text-amber-400' : 'bg-emerald-500/10 text-emerald-400'}`}
              title={isMock ? 'Offline mode: set GEMINI_API_KEY on the backend for full AI' : `Gemini model: ${aiMode.llm.model}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${isMock ? 'bg-amber-400' : 'bg-emerald-400'}`} />
              {isMock ? 'AI: offline mock mode' : `AI: ${aiMode.llm.model}`}
            </div>
          )}
          <div className="flex items-center justify-between">
            <button onClick={() => navigate('/profile')} className="text-left">
              <div className="text-xs font-semibold text-slate-200">{user?.full_name || user?.email}</div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{user?.role}</div>
            </button>
            <button onClick={logout} className="rounded-md p-1.5 text-slate-500 transition hover:bg-slate-800 hover:text-red-400" title="Sign out">
              ⏻
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="ml-60 flex-1 px-8 py-6">
        <Outlet />
      </main>
    </div>
  )
}
