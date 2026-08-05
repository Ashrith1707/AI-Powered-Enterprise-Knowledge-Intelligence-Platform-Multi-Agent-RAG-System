import {
  BarChart3, Bot, FileText, LayoutDashboard, MessageSquareText,
  ScanSearch, Settings, Sparkles, UploadCloud,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/utils/cn'
import { useHealth } from '@/hooks/useAnalytics'

export const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/analytics', label: 'Analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'Knowledge Base',
    items: [
      { to: '/upload', label: 'Upload', icon: UploadCloud },
      { to: '/documents', label: 'Documents', icon: FileText },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { to: '/ask', label: 'Ask AI', icon: MessageSquareText },
      { to: '/search', label: 'Semantic Search', icon: ScanSearch },
      { to: '/reports', label: 'Reports', icon: Sparkles },
    ],
  },
  {
    label: 'System',
    items: [{ to: '/settings', label: 'Settings', icon: Settings }],
  },
]

export function Sidebar({ onNavigate }) {
  const { data: health } = useHealth()

  return (
    <div className="flex h-full flex-col">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-5 pb-6 pt-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-[#6d5ae0] shadow-md">
          <Bot className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-sm font-semibold leading-none text-ink">KnowledgeIQ</p>
          <p className="mt-1 text-[10px] uppercase tracking-widest text-muted">Enterprise AI</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-5 overflow-y-auto px-3">
        {NAV_SECTIONS.map((section) => (
          <div key={section.label}>
            <p className="mb-1.5 px-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
              {section.label}
            </p>
            {section.items.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    'group mb-0.5 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors',
                    isActive
                      ? 'bg-primary-soft text-primary'
                      : 'text-ink-2 hover:bg-surface-2 hover:text-ink',
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* Backend status */}
      <div className="m-3 rounded-xl border border-edge bg-surface-2/60 p-3">
        <div className="flex items-center gap-2">
          <span className={cn('h-2 w-2 rounded-full', health ? 'bg-success' : 'bg-danger')} />
          <p className="text-xs font-medium text-ink-2">
            {health ? 'Backend online' : 'Backend offline'}
          </p>
        </div>
        <p className="mt-1 text-[11px] text-muted">
          {{
            ok: `Gemini connected (${health?.llm_model ?? 'gemini'})`,
            invalid_key: 'Gemini key INVALID — Ask AI disabled',
            quota_exceeded: 'Gemini quota exceeded',
            not_configured: 'Gemini key not set — Ask AI disabled',
          }[health?.llm_status] ?? (health ? 'Gemini unavailable' : 'Checking Gemini…')}
        </p>
      </div>
    </div>
  )
}
