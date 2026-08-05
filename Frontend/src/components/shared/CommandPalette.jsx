/** Ctrl/Cmd+K command palette: navigation, quick actions, recent documents. */
import { AnimatePresence, motion } from 'framer-motion'
import { CornerDownLeft, FileText, Moon, Search, Sun, UploadCloud } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { useTheme } from '@/context/ThemeContext'
import { useDocuments } from '@/hooks/useDocuments'
import { NAV_SECTIONS } from '@/layouts/Sidebar'
import { cn } from '@/utils/cn'

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()
  const { theme, toggle } = useTheme()
  const { data: docs } = useDocuments({ enabled: open })

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
        setQuery('')
        setActive(0)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30)
  }, [open])

  const items = useMemo(() => {
    const q = query.toLowerCase()
    const nav = NAV_SECTIONS.flatMap((s) => s.items).map((i) => ({
      id: `nav-${i.to}`,
      icon: i.icon,
      label: `Go to ${i.label}`,
      run: () => navigate(i.to),
    }))
    const actions = [
      { id: 'act-upload', icon: UploadCloud, label: 'Upload documents…', run: () => navigate('/upload') },
      {
        id: 'act-theme',
        icon: theme === 'dark' ? Sun : Moon,
        label: `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`,
        run: toggle,
      },
    ]
    const recent = (docs ?? []).slice(0, 6).map((d) => ({
      id: `doc-${d.id}`,
      icon: FileText,
      label: d.filename,
      hint: d.category,
      run: () => navigate(`/documents?q=${encodeURIComponent(d.filename)}`),
    }))
    const all = [...actions, ...nav, ...recent]
    return q ? all.filter((i) => i.label.toLowerCase().includes(q)) : all
  }, [query, docs, navigate, theme, toggle])

  const select = (item) => {
    setOpen(false)
    item.run()
  }

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    if (e.key === 'Enter' && items[active]) { e.preventDefault(); select(items[active]) }
  }

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[70] flex items-start justify-center pt-[14vh]"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        >
          <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={() => setOpen(false)} />
          <motion.div
            role="dialog" aria-modal="true" aria-label="Command palette"
            className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-edge bg-surface shadow-2xl"
            initial={{ opacity: 0, scale: 0.97, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: -8 }}
            transition={{ duration: 0.15 }}
          >
            <div className="flex items-center gap-2.5 border-b border-edge px-4">
              <Search className="h-4 w-4 text-muted" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => { setQuery(e.target.value); setActive(0) }}
                onKeyDown={onKeyDown}
                placeholder="Search pages, actions, documents…"
                aria-label="Command search"
                className="h-12 flex-1 bg-transparent text-sm text-ink placeholder:text-muted focus:outline-none"
              />
              <kbd className="rounded border border-edge bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">ESC</kbd>
            </div>
            <ul className="max-h-72 overflow-y-auto p-1.5" role="listbox">
              {items.length === 0 && (
                <li className="px-3 py-6 text-center text-sm text-muted">No results for “{query}”</li>
              )}
              {items.map((item, i) => (
                <li key={item.id} role="option" aria-selected={i === active}>
                  <button
                    onMouseEnter={() => setActive(i)}
                    onClick={() => select(item)}
                    className={cn(
                      'flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm',
                      i === active ? 'bg-primary-soft text-primary' : 'text-ink-2',
                    )}
                  >
                    <item.icon className="h-4 w-4 shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {item.hint && <span className="text-[10px] text-muted">{item.hint}</span>}
                    {i === active && <CornerDownLeft className="h-3.5 w-3.5 shrink-0 opacity-60" />}
                  </button>
                </li>
              ))}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}
