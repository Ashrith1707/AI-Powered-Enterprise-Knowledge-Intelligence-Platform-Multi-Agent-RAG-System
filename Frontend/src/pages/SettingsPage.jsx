import {
  Bell, Bot, Database, Info, KeyRound, Moon, Palette, Server, Shield, Sun,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/components/ui/toast'
import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/context/ThemeContext'
import { useHealth } from '@/hooks/useAnalytics'
import { useDocuments } from '@/hooks/useDocuments'
import { cn } from '@/utils/cn'
import { formatBytes } from '@/utils/format'

function Section({ icon: Icon, title, description, children }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-primary-soft p-2"><Icon className="h-4 w-4 text-primary" /></div>
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()
  const { user } = useAuth()
  const { data: health } = useHealth()
  const { data: docs } = useDocuments()
  const { push } = useToast()

  const storage = (docs ?? []).reduce((s, d) => s + d.file_size, 0)

  return (
    <div>
      <PageHeader title="Settings" description="Workspace configuration and system status." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Section icon={Palette} title="Appearance" description="Theme preference is stored per browser.">
          <div className="flex gap-3">
            {[
              { key: 'light', icon: Sun, label: 'Light' },
              { key: 'dark', icon: Moon, label: 'Dark' },
            ].map(({ key, icon: Icon, label }) => (
              <button
                key={key}
                onClick={() => setTheme(key)}
                aria-pressed={theme === key}
                className={cn(
                  'flex flex-1 flex-col items-center gap-2 rounded-xl border-2 p-4 transition-colors',
                  theme === key ? 'border-primary bg-primary-soft' : 'border-edge hover:border-primary/40',
                )}
              >
                <Icon className={cn('h-5 w-5', theme === key ? 'text-primary' : 'text-muted')} />
                <span className={cn('text-xs font-medium', theme === key ? 'text-primary' : 'text-ink-2')}>{label}</span>
              </button>
            ))}
          </div>
        </Section>

        <Section icon={Bot} title="AI & RAG engine" description="Live status from the backend health endpoint.">
          <div className="space-y-2.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted">Backend</span>
              <Badge tone={health ? 'green' : 'red'}>{health ? 'online' : 'offline'}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted">Gemini LLM</span>
              <Badge tone={health?.llm_status === 'ok' ? 'green'
                : health?.llm_status === 'invalid_key' ? 'red' : 'amber'}>
                {health?.llm_status?.replace('_', ' ') ?? 'checking'}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted">Environment</span>
              <Badge>{health?.env ?? '—'}</Badge>
            </div>
            {health && !health.llm_configured && (
              <p className="rounded-lg bg-warning/10 p-2.5 leading-relaxed text-warning">
                {health.llm_detail}
              </p>
            )}
          </div>
        </Section>

        <Section icon={KeyRound} title="API access" description="How this UI talks to the platform.">
          <div className="space-y-2.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted">Base URL</span>
              <code className="rounded bg-surface-2 px-2 py-0.5 font-mono text-ink">/api → localhost:8000</code>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted">Interactive docs</span>
              <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
                className="font-medium text-primary hover:underline">Swagger UI ↗</a>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted">Authentication</span>
              <Badge tone="amber">demo session</Badge>
            </div>
            <p className="text-muted">
              JWT endpoints are pending on the backend (TODO.md) — the token interceptor is already wired.
            </p>
          </div>
        </Section>

        <Section icon={Database} title="Storage" description="Computed from live document data.">
          <div className="space-y-2.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted">Documents stored</span>
              <span className="font-semibold text-ink">{docs?.length ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted">Disk used (originals)</span>
              <span className="font-semibold text-ink">{formatBytes(storage)}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${Math.min(100, (storage / (500 * 1024 * 1024)) * 100)}%` }} />
            </div>
            <p className="text-muted">Shown against a 500 MB reference quota (display only).</p>
          </div>
        </Section>

        <Section icon={Bell} title="Notifications" description="In-app toasts for uploads, deletions and reports.">
          <Button variant="secondary" size="sm" onClick={() => push('This is how notifications look', 'info')}>
            Send test notification
          </Button>
        </Section>

        <Section icon={Shield} title="Security" description="Session and data controls.">
          <div className="space-y-2.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted">Signed in as</span>
              <span className="font-medium text-ink">{user?.email}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted">Role</span>
              <Badge tone="blue">{user?.role}</Badge>
            </div>
            <p className="text-muted">
              Session data lives only in this browser. Manage or clear it from your Profile page.
            </p>
          </div>
        </Section>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-primary-soft p-2"><Server className="h-4 w-4 text-primary" /></div>
            <div>
              <CardTitle>System information</CardTitle>
              <CardDescription>About this deployment</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Platform', health?.app ?? 'Enterprise Knowledge Intelligence'],
            ['Frontend', 'React 18 · Vite · Tailwind v4'],
            ['Backend', 'FastAPI · SQLAlchemy · LangChain'],
            ['Retrieval', 'FAISS · Gemini embeddings · RAG'],
          ].map(([k, v]) => (
            <div key={k} className="rounded-xl border border-edge p-3">
              <p className="text-muted">{k}</p>
              <p className="mt-1 font-medium text-ink">{v}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <p className="mt-4 flex items-start gap-1.5 text-[11px] text-muted">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Final Year Project — AI-Powered Enterprise Knowledge Intelligence Platform using Multi-Agent AI and RAG.
      </p>
    </div>
  )
}
