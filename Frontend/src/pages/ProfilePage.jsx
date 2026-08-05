import { motion } from 'framer-motion'
import { Clock, FileText, Keyboard, LogOut, MessageSquareText, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/shared/PageHeader'
import { ConfirmDialog } from '@/components/shared/States'
import { Badge, StatusBadge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/components/ui/toast'
import { useAuth } from '@/context/AuthContext'
import { useConversations } from '@/hooks/useConversations'
import { useDocuments } from '@/hooks/useDocuments'
import { formatRelative } from '@/utils/format'
import { useState } from 'react'

const SHORTCUTS = [
  ['Ctrl / Cmd + K', 'Open command palette'],
  ['Enter', 'Send question (Ask AI)'],
  ['Shift + Enter', 'New line in question'],
  ['Esc', 'Close dialogs, drawers and palette'],
]

export default function ProfilePage() {
  const { user, logout } = useAuth()
  const { data: docs } = useDocuments()
  const { chats } = useConversations()
  const { push } = useToast()
  const navigate = useNavigate()
  const [confirmClear, setConfirmClear] = useState(false)

  const recentDocs = (docs ?? []).slice(0, 5)
  const recentChats = [...chats]
    .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
    .slice(0, 5)

  const clearLocalData = () => {
    ;['eki.chats', 'eki.pinned', 'eki.recentSearches'].forEach((k) => localStorage.removeItem(k))
    setConfirmClear(false)
    push('Local workspace data cleared', 'success')
    setTimeout(() => window.location.reload(), 600)
  }

  return (
    <div>
      <PageHeader title="Profile" description="Your account, activity and preferences." />

      {/* Identity card */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <Card className="overflow-hidden">
          <div className="h-20 bg-gradient-to-r from-primary via-[#4f6fdd] to-[#6d5ae0]" />
          <CardContent className="-mt-8 flex flex-wrap items-end gap-4">
            <span className="flex h-16 w-16 items-center justify-center rounded-2xl border-4 border-surface bg-gradient-to-br from-primary to-[#6d5ae0] text-xl font-bold text-white shadow-lg">
              {user?.initials}
            </span>
            <div className="flex-1 pb-1">
              <p className="text-base font-semibold capitalize text-ink">{user?.name}</p>
              <p className="text-xs text-muted">{user?.email}</p>
            </div>
            <div className="flex items-center gap-2 pb-1">
              <Badge tone="blue">{user?.role}</Badge>
              <Button variant="secondary" size="sm" onClick={() => { logout(); navigate('/login') }}>
                <LogOut className="h-3.5 w-3.5" /> Sign out
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Recent uploads</CardTitle>
              <CardDescription>Latest documents you added</CardDescription>
            </div>
            <FileText className="h-4 w-4 text-muted" />
          </CardHeader>
          <CardContent>
            {recentDocs.length === 0 ? (
              <p className="text-xs text-muted">No uploads yet.</p>
            ) : (
              <ul className="space-y-2.5">
                {recentDocs.map((d) => (
                  <li key={d.id} className="flex items-center gap-2 text-xs">
                    <span className="min-w-0 flex-1 truncate text-ink">{d.filename}</span>
                    <StatusBadge status={d.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Recent chats</CardTitle>
              <CardDescription>Stored in this browser</CardDescription>
            </div>
            <MessageSquareText className="h-4 w-4 text-muted" />
          </CardHeader>
          <CardContent>
            {recentChats.length === 0 ? (
              <p className="text-xs text-muted">No conversations yet — try Ask AI.</p>
            ) : (
              <ul className="space-y-2.5">
                {recentChats.map((c) => (
                  <li key={c.id}>
                    <button onClick={() => navigate('/ask')}
                      className="flex w-full items-center gap-2 text-left text-xs hover:text-primary">
                      <Clock className="h-3 w-3 shrink-0 text-muted" />
                      <span className="min-w-0 flex-1 truncate text-ink">{c.title}</span>
                      <span className="shrink-0 text-[10px] text-muted">{formatRelative(c.updated_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Keyboard shortcuts</CardTitle>
              <CardDescription>Work faster</CardDescription>
            </div>
            <Keyboard className="h-4 w-4 text-muted" />
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {SHORTCUTS.map(([keys, action]) => (
                <li key={keys} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-muted">{action}</span>
                  <kbd className="rounded border border-edge bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-2">
                    {keys}
                  </kbd>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      {/* Danger zone */}
      <Card className="mt-4 border-danger/40">
        <CardHeader>
          <div>
            <CardTitle className="text-danger">Danger zone</CardTitle>
            <CardDescription>
              Removes chats, pins and recent searches stored in this browser. Documents on the server are not affected.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <Button variant="danger-ghost" size="sm" onClick={() => setConfirmClear(true)}>
            <Trash2 className="h-3.5 w-3.5" /> Clear local workspace data
          </Button>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        onConfirm={clearLocalData}
        title="Clear local data?"
        description="All conversations, pinned documents and recent searches in this browser will be removed. Server-side documents are untouched."
        confirmLabel="Clear data"
      />
    </div>
  )
}
