import { cn } from '@/utils/cn'

const tones = {
  neutral: 'bg-surface-2 text-ink-2 border-edge',
  blue: 'bg-primary-soft text-primary border-transparent',
  green: 'bg-success/10 text-success border-transparent',
  amber: 'bg-warning/10 text-warning border-transparent',
  red: 'bg-danger-soft text-danger border-transparent',
}

export function Badge({ tone = 'neutral', className, ...props }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium',
        tones[tone],
        className,
      )}
      {...props}
    />
  )
}

/** Maps a document pipeline status to a colored badge. */
export function StatusBadge({ status }) {
  const map = {
    uploaded: { tone: 'neutral', label: 'Queued' },
    parsing: { tone: 'amber', label: 'Processing' },
    parsed: { tone: 'blue', label: 'Parsed' },
    indexed: { tone: 'green', label: 'Indexed' },
    failed: { tone: 'red', label: 'Failed' },
  }
  const { tone, label } = map[status] ?? { tone: 'neutral', label: status }
  return <Badge tone={tone}>{label}</Badge>
}
