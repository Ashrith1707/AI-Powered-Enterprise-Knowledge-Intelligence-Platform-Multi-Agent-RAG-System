/** Animated stage tracker fed by the REAL backend status field. */
import { motion } from 'framer-motion'
import { Check, Loader2, X } from 'lucide-react'
import { cn } from '@/utils/cn'
import { PIPELINE_STAGES, stageIndex } from '@/utils/constants'

export function PipelineTracker({ status }) {
  const failed = status === 'failed'
  const current = failed ? PIPELINE_STAGES.length : stageIndex(status)
  const done = status === 'indexed'

  return (
    <div className="flex items-center gap-1.5" role="list" aria-label="Processing pipeline">
      {PIPELINE_STAGES.map((stage, i) => {
        const isDone = done || i < current
        const isActive = !done && !failed && i === current
        return (
          <div key={stage.key} role="listitem" className="flex items-center gap-1.5">
            <div className="flex items-center gap-1">
              <span
                className={cn(
                  'flex h-4.5 w-4.5 items-center justify-center rounded-full text-[9px]',
                  isDone && 'bg-success text-white',
                  isActive && 'bg-primary text-white',
                  !isDone && !isActive && 'bg-surface-2 text-muted',
                  failed && i === current - 0 && 'bg-surface-2',
                )}
              >
                {isDone ? (
                  <Check className="h-2.5 w-2.5" />
                ) : isActive ? (
                  <Loader2 className="h-2.5 w-2.5 animate-spin" />
                ) : (
                  i + 1
                )}
              </span>
              <span
                className={cn(
                  'hidden text-[10px] font-medium sm:inline',
                  isDone ? 'text-success' : isActive ? 'text-primary' : 'text-muted',
                )}
              >
                {stage.label}
              </span>
            </div>
            {i < PIPELINE_STAGES.length - 1 && (
              <motion.span
                className={cn('h-px w-4 sm:w-6', isDone ? 'bg-success' : 'bg-edge')}
                initial={false}
                animate={{ opacity: 1 }}
              />
            )}
          </div>
        )
      })}
      {failed && (
        <span className="ml-1 flex items-center gap-1 text-[10px] font-medium text-danger">
          <X className="h-3 w-3" /> Failed
        </span>
      )}
    </div>
  )
}
