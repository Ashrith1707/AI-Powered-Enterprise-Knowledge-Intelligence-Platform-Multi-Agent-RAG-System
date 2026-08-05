import { motion } from 'framer-motion'
import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}>
        <div className="mx-auto mb-5 w-fit rounded-3xl bg-primary-soft p-5">
          <Compass className="h-10 w-10 text-primary" />
        </div>
        <p className="text-5xl font-bold tracking-tight text-ink">404</p>
        <p className="mt-2 text-sm text-muted">This page doesn't exist in the knowledge base.</p>
        <Link to="/"><Button className="mt-6">Back to Dashboard</Button></Link>
      </motion.div>
    </div>
  )
}
