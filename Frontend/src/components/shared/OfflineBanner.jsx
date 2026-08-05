import { AnimatePresence, motion } from 'framer-motion'
import { WifiOff } from 'lucide-react'
import { useEffect, useState } from 'react'

export function OfflineBanner() {
  const [offline, setOffline] = useState(!navigator.onLine)

  useEffect(() => {
    const on = () => setOffline(false)
    const off = () => setOffline(true)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  return (
    <AnimatePresence>
      {offline && (
        <motion.div
          role="alert"
          initial={{ y: -40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -40, opacity: 0 }}
          className="fixed inset-x-0 top-0 z-[80] flex items-center justify-center gap-2 bg-danger px-4 py-1.5 text-xs font-medium text-white"
        >
          <WifiOff className="h-3.5 w-3.5" />
          You are offline — changes will fail until the connection returns.
        </motion.div>
      )}
    </AnimatePresence>
  )
}
