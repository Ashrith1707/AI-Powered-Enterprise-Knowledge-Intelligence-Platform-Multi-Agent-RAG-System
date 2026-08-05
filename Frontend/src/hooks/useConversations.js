/**
 * Server-backed chat sessions (Module 4): conversations and messages persist
 * in PostgreSQL/SQLite via /api/conversations and survive any browser.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { chatApi } from '@/api/chat.api'

const KEY = ['conversations']

export function useConversations() {
  const qc = useQueryClient()
  const { data: chats = [], isLoading } = useQuery({ queryKey: KEY, queryFn: chatApi.list })

  const setChats = useCallback(
    (updater) => qc.setQueryData(KEY, (prev = []) => updater(prev)),
    [qc],
  )

  const create = useCallback(async () => {
    const convo = await chatApi.create()
    setChats((prev) => [{ ...convo, messages: convo.messages ?? [] }, ...prev])
    return convo.id
  }, [setChats])

  const appendMessage = useCallback(async (conversationId, message) => {
    const saved = await chatApi.addMessage(conversationId, message)
    setChats((prev) =>
      prev.map((c) =>
        c.id === conversationId
          ? {
              ...c,
              title: c.title === 'New conversation' && message.role === 'user'
                ? message.content.slice(0, 48)
                : c.title,
              updated_at: saved.created_at,
              messages: [...c.messages, saved],
            }
          : c,
      ),
    )
    return saved
  }, [setChats])

  const patchMutation = useMutation({
    mutationFn: ({ id, changes }) => chatApi.patch(id, changes),
    onSuccess: (updated) =>
      setChats((prev) => prev.map((c) => (c.id === updated.id ? { ...c, ...updated, messages: c.messages } : c))),
  })

  const rename = useCallback(
    (id, title) => patchMutation.mutate({ id, changes: { title } }),
    [patchMutation],
  )

  const togglePin = useCallback((id) => {
    const current = qc.getQueryData(KEY)?.find((c) => c.id === id)
    if (current) patchMutation.mutate({ id, changes: { pinned: !current.pinned } })
  }, [patchMutation, qc])

  const removeMutation = useMutation({
    mutationFn: chatApi.remove,
    onSuccess: (_data, id) => setChats((prev) => prev.filter((c) => c.id !== id)),
  })

  return {
    chats,
    isLoading,
    create,
    appendMessage,
    rename,
    togglePin,
    remove: removeMutation.mutate,
  }
}
