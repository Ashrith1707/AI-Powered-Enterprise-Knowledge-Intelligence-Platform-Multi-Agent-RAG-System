/** Tiny toast system: <ToastProvider> + useToast().push('message', 'success') */
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useRef, useState } from 'react'

const ToastContext = createContext(null)

const ICONS = {
  success: [CheckCircle2, 'text-success'],
  error: [XCircle, 'text-danger'],
  warning: [AlertTriangle, 'text-warning'],
  info: [Info, 'text-primary'],
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const push = useCallback((message, type = 'info') => {
    const id = ++idRef.current
    setToasts((t) => [...t, { id, message, type }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200)
  }, [])

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-80 flex-col gap-2">
        <AnimatePresence>
          {toasts.map(({ id, message, type }) => {
            const [Icon, color] = ICONS[type] ?? ICONS.info
            return (
              <motion.div
                key={id}
                initial={{ opacity: 0, x: 40 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 40 }}
                className="pointer-events-auto flex items-start gap-2.5 rounded-xl border border-edge bg-surface p-3.5 shadow-lg"
              >
                <Icon className={`mt-0.5 h-4.5 w-4.5 shrink-0 ${color}`} />
                <p className="text-sm text-ink">{message}</p>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
