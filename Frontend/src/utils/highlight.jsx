/** Wraps query terms in <mark> for search snippets and page previews. */
export function highlightTerms(text, query) {
  if (!query || !text) return text
  const terms = [...new Set(query.toLowerCase().match(/[a-z0-9]{3,}/g) ?? [])]
  if (!terms.length) return text
  const re = new RegExp(`\\b(${terms.join('|')})`, 'gi')
  return text.split(re).map((part, i) =>
    terms.includes(part.toLowerCase())
      ? <mark key={i} className="rounded-sm bg-primary/20 px-0.5 text-inherit">{part}</mark>
      : part,
  )
}
