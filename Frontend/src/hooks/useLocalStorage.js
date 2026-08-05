import { useCallback, useState } from 'react'

export function useLocalStorage(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw ? JSON.parse(raw) : initial
    } catch {
      return initial
    }
  })

  const set = useCallback(
    (next) => {
      setValue((prev) => {
        const resolved = typeof next === 'function' ? next(prev) : next
        localStorage.setItem(key, JSON.stringify(resolved))
        return resolved
      })
    },
    [key],
  )

  return [value, set]
}

/** Pin/unpin document ids, persisted per browser. */
export function usePinnedDocuments() {
  const [pinned, setPinned] = useLocalStorage('eki.pinned', [])
  const toggle = (id) =>
    setPinned((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  return { pinned, toggle, isPinned: (id) => pinned.includes(id) }
}
