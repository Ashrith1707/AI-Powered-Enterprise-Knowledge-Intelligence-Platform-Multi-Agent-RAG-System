import { forwardRef } from 'react'
import { cn } from '@/utils/cn'

export const Input = forwardRef(function Input({ className, ...props }, ref) {
  return (
    <input
      ref={ref}
      className={cn(
        'h-9.5 w-full rounded-lg border border-edge bg-surface px-3 text-sm text-ink',
        'placeholder:text-muted transition-colors',
        'focus:border-primary focus:outline-none focus:ring-2 focus:ring-[var(--ring)]',
        className,
      )}
      {...props}
    />
  )
})

export function Label({ className, ...props }) {
  return <label className={cn('mb-1.5 block text-xs font-medium text-ink-2', className)} {...props} />
}

export function FieldError({ children }) {
  if (!children) return null
  return <p className="mt-1 text-xs text-danger">{children}</p>
}
