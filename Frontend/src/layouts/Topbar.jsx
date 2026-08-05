import { Bell, ChevronRight, LogOut, Menu, Moon, Search, Settings, Sun, User } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Dropdown, DropdownItem, DropdownSeparator } from '@/components/ui/dropdown'
import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/context/ThemeContext'
import { useDashboard } from '@/hooks/useAnalytics'
import { NAV_SECTIONS } from './Sidebar'

const LABELS = Object.fromEntries(
  NAV_SECTIONS.flatMap((s) => s.items.map((i) => [i.to, i.label])),
)

function Breadcrumb() {
  const { pathname } = useLocation()
  const label = LABELS[pathname] ?? 'Page'
  return (
    <div className="hidden items-center gap-1.5 text-sm sm:flex">
      <Link to="/" className="text-muted hover:text-ink">Home</Link>
      {pathname !== '/' && (
        <>
          <ChevronRight className="h-3.5 w-3.5 text-muted" />
          <span className="font-medium text-ink">{label}</span>
        </>
      )}
    </div>
  )
}

export function Topbar({ onMenuClick }) {
  const { theme, toggle } = useTheme()
  const { user, logout } = useAuth()
  const { data: stats } = useDashboard()
  const navigate = useNavigate()

  const notifications = (stats?.recent_queries ?? []).slice(0, 5)

  return (
    <header className="sticky top-0 z-30 flex h-15 items-center gap-3 border-b border-edge bg-surface/85 px-4 backdrop-blur-md sm:px-6">
      <button className="rounded-lg p-2 text-ink-2 hover:bg-surface-2 lg:hidden"
        onClick={onMenuClick} aria-label="Open navigation menu">
        <Menu className="h-5 w-5" />
      </button>

      <Breadcrumb />

      {/* Global search -> semantic search page */}
      <form
        className="ml-auto hidden w-full max-w-sm md:block"
        onSubmit={(e) => {
          e.preventDefault()
          const q = new FormData(e.currentTarget).get('q')
          if (q?.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`)
          e.currentTarget.reset()
        }}
      >
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            name="q"
            placeholder="Search the knowledge base…"
            aria-label="Search the knowledge base"
            className="h-9 w-full rounded-lg border border-edge bg-surface-2/60 pl-9 pr-14 text-sm text-ink placeholder:text-muted focus:border-primary focus:bg-surface focus:outline-none"
          />
          <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-edge bg-surface px-1.5 py-0.5 text-[10px] text-muted">
            Ctrl K
          </kbd>
        </div>
      </form>

      <div className="ml-auto flex items-center gap-1.5 md:ml-0">
        {/* Theme */}
        <button
          onClick={toggle}
          title="Toggle theme"
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          className="rounded-lg p-2 text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
        >
          {theme === 'dark' ? <Sun className="h-4.5 w-4.5" /> : <Moon className="h-4.5 w-4.5" />}
        </button>

        {/* Notifications = recent search activity from the real API */}
        <Dropdown
          trigger={
            <button className="relative rounded-lg p-2 text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
              aria-label="Notifications">
              <Bell className="h-4.5 w-4.5" />
              {notifications.length > 0 && (
                <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-primary" />
              )}
            </button>
          }
          panelClassName="w-72"
        >
          <p className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Recent activity
          </p>
          {notifications.length === 0 && (
            <p className="px-3 pb-3 text-sm text-muted">No activity yet.</p>
          )}
          {notifications.map((q, i) => (
            <DropdownItem key={i} icon={Search} onClick={() => navigate('/search')}>
              <span className="truncate">{q}</span>
            </DropdownItem>
          ))}
        </Dropdown>

        {/* Profile */}
        <Dropdown
          trigger={
            <button className="ml-1 flex items-center gap-2 rounded-lg p-1.5 hover:bg-surface-2"
              aria-label="Account menu">
              <span className="flex h-7.5 w-7.5 items-center justify-center rounded-full bg-gradient-to-br from-primary to-[#6d5ae0] text-[11px] font-semibold text-white">
                {user?.initials ?? '??'}
              </span>
            </button>
          }
        >
          <div className="px-3 py-2">
            <p className="text-sm font-medium capitalize text-ink">{user?.name}</p>
            <p className="text-xs text-muted">{user?.email}</p>
          </div>
          <DropdownSeparator />
          <DropdownItem icon={User} onClick={() => navigate('/profile')}>Profile</DropdownItem>
          <DropdownItem icon={Settings} onClick={() => navigate('/settings')}>Settings</DropdownItem>
          <DropdownSeparator />
          <DropdownItem icon={LogOut} className="text-danger" onClick={() => { logout(); navigate('/login') }}>
            Sign out
          </DropdownItem>
        </Dropdown>
      </div>
    </header>
  )
}
