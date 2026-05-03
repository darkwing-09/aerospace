import { useState, useCallback, useRef } from 'react'

/**
 * useChat.js
 * ───────────────────────────────────────────────────────────────
 * Manages conversation state and SSE streaming connection.
 * Detects [PAGE_REF:N] tokens to trigger PDF sync.
 * 
 * CRITICAL: SSE messages are delimited by double newlines (\n\n).
 * Each message looks like: "data: <payload>\n\n"
 * We buffer partial reads and only process complete messages.
 */

export default function useChat(aircraftId, onPageRef) {
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const fullResponseRef = useRef('')

  const clearChat = useCallback(() => setMessages([]), [])

  const sendMessage = async (content) => {
    if (!content.trim() || !aircraftId) return

    const userMsg = { role: 'user', content }
    const updatedMessages = [...messages, userMsg]
    setMessages(updatedMessages)
    setIsStreaming(true)
    fullResponseRef.current = ''

    // Placeholder for AI response
    const aiMsg = { role: 'assistant', content: '', isStreaming: true }
    setMessages(prev => [...prev, aiMsg])

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          aircraft_id: aircraftId,
          messages: updatedMessages
        })
      })

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let sseBuffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        // Append new chunk to buffer
        sseBuffer += decoder.decode(value, { stream: true })
        
        // Split on double-newline (SSE message boundary)
        const parts = sseBuffer.split('\n\n')
        
        // Last element may be incomplete — keep it in buffer
        sseBuffer = parts.pop() || ''

        for (const part of parts) {
          const trimmedPart = part.trim()
          if (!trimmedPart.startsWith('data: ')) continue
          
          // Extract payload after "data: "
          const payload = trimmedPart.substring(6)
          const trimmedPayload = payload.trim()

          // ── Control tokens ────────────────────────────────────
          if (trimmedPayload === '[DONE]') {
            setIsStreaming(false)
            setMessages(prev => {
              const next = [...prev]
              if (next.length > 0) {
                next[next.length - 1] = { 
                  ...next[next.length - 1], 
                  isStreaming: false 
                }
              }
              return next
            })
            continue
          }

          if (trimmedPayload.startsWith('[PAGE_REF:')) {
            const match = trimmedPayload.match(/\[PAGE_REF:(\d+)\]/)
            if (match) {
              const pageNum = parseInt(match[1])
              setMessages(prev => {
                const next = [...prev]
                if (next.length > 0) {
                  next[next.length - 1] = {
                    ...next[next.length - 1],
                    page_ref: pageNum
                  }
                }
                return next
              })
              if (onPageRef) onPageRef(pageNum)
            }
            continue
          }

          if (trimmedPayload.startsWith('[ERROR:')) {
            const match = trimmedPayload.match(/\[ERROR:(.*)\]/)
            const errMsg = match ? match[1] : 'Unknown error'
            setMessages(prev => {
              const next = [...prev]
              if (next.length > 0) {
                next[next.length - 1] = {
                  ...next[next.length - 1],
                  content: fullResponseRef.current + `\n\n⚠️ ERROR: ${errMsg}`,
                  isStreaming: false
                }
              }
              return next
            })
            setIsStreaming(false)
            continue
          }

          // ── Content token ─────────────────────────────────────
          // Unescape newlines that were escaped for SSE transport
          const token = payload.replace(/\\n/g, '\n')
          fullResponseRef.current += token
          
          const currentContent = fullResponseRef.current
          setMessages(prev => {
            const next = [...prev]
            if (next.length > 0) {
              next[next.length - 1] = {
                ...next[next.length - 1],
                content: currentContent
              }
            }
            return next
          })
        }
      }
    } catch (err) {
      console.error('[useChat] Stream error:', err)
      setMessages(prev => {
        const next = [...prev]
        if (next.length > 0) {
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: "⚠️ Connection to AeroMind backend failed. Ensure backend is running on port 8000.",
            isStreaming: false
          }
        }
        return next
      })
      setIsStreaming(false)
    }
  }

  return {
    messages,
    sendMessage,
    isStreaming,
    clearChat
  }
}
