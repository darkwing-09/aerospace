import { useState, useCallback, useRef } from 'react'

/**
 * useChat.js
 * ───────────────────────────────────────────────────────────────
 * Multi-Agent SSE Streaming Hook:
 * - Parses [AGENT_STATUS], [AGENT_STEP], [VISUAL_REF], [EVAL_REPORT], [PAGE_REF]
 * - Provides live agent HUD telemetry without tech jargon
 * - Streams token-by-token response with zero latency
 */

export default function useChat(aircraftId, onPageRef) {
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [agentStatus, setAgentStatus] = useState(null)
  const [dagPlan, setDagPlan] = useState(null)
  const [mathSteps, setMathSteps] = useState([])
  const abortRef = useRef(null)

  const clearChat = useCallback(() => {
    setMessages([])
    setAgentStatus(null)
    setDagPlan(null)
    setMathSteps([])
  }, [])

  const sendMessage = async (content) => {
    if (!content.trim()) return

    const targetAircraftId = aircraftId || 'default'

    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller

    const userMsg = { role: 'user', content }
    const updatedMessages = [...messages, userMsg]

    // Add user message + empty assistant placeholder
    const startTime = Date.now()
    const aiMsg = {
      role: 'assistant',
      content: '',
      isStreaming: true,
      visualRefs: [],
      mathSteps: [],
      thoughts: [],
      thinkingDuration: 0,
      evaluation: null,
    }
    setMessages([...updatedMessages, aiMsg])
    setIsStreaming(true)
    setDagPlan(null)
    setAgentStatus({
      agent: 'supervisor',
      title: 'Mission Commander SLM',
      action: 'Decomposing tactical objectives and planning dynamic execution DAG...',
      stage: 'planning',
    })
    setMathSteps([])

    let fullResponse = ''
    let currentVisualRefs = []
    let currentMathSteps = []
    let currentThoughts = []
    let currentEvaluation = null

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          aircraft_id: targetAircraftId,
          messages: updatedMessages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      })

      if (!response.ok) {
        throw new Error(`Server returned status ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let sseBuffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        sseBuffer += decoder.decode(value, { stream: true })
        const parts = sseBuffer.split('\n\n')
        sseBuffer = parts.pop() || ''

        for (const part of parts) {
          if (!part) continue
          const lines = part.split('\n')
          for (const rawLine of lines) {
            if (!rawLine.startsWith('data: ')) continue
            const payload = rawLine.substring(6)

            // ── Control Tokens ────────────────────────────────────
            if (payload.trim() === '[DONE]') {
              const elapsed = ((Date.now() - startTime) / 1000).toFixed(1)
              setIsStreaming(false)
              setAgentStatus(null)
              setMessages((prev) => {
                const next = [...prev]
                if (next.length > 0) {
                  next[next.length - 1] = {
                    ...next[next.length - 1],
                    isStreaming: false,
                    thinkingDuration: next[next.length - 1].thinkingDuration || elapsed,
                  }
                }
                return next
              })
              continue
            }

            if (payload.startsWith('[DAG_PLAN:')) {
              try {
                const jsonStr = payload.replace(/^\[DAG_PLAN:/, '').replace(/\]$/, '')
                const planObj = JSON.parse(jsonStr)
                setDagPlan(planObj)
              } catch (e) {}
              continue
            }

            if (payload.startsWith('[AGENT_THOUGHT:')) {
              try {
                const jsonStr = payload.replace(/^\[AGENT_THOUGHT:/, '').replace(/\]$/, '')
                const thoughtObj = JSON.parse(jsonStr)
                currentThoughts.push(thoughtObj)
                setMessages((prev) => {
                  const next = [...prev]
                  if (next.length > 0) {
                    next[next.length - 1] = {
                      ...next[next.length - 1],
                      thoughts: [...currentThoughts],
                    }
                  }
                  return next
                })
              } catch (e) {}
              continue
            }

            if (payload.startsWith('[AGENT_STATUS:')) {
              try {
                const jsonStr = payload.replace(/^\[AGENT_STATUS:/, '').replace(/\]$/, '')
                const statusObj = JSON.parse(jsonStr)
                setAgentStatus(statusObj)
              } catch (e) {}
              continue
            }

            if (payload.startsWith('[AGENT_STEP:')) {
              try {
                const jsonStr = payload.replace(/^\[AGENT_STEP:/, '').replace(/\]$/, '')
                const stepObj = JSON.parse(jsonStr)
                currentMathSteps.push(stepObj)
                setMathSteps([...currentMathSteps])
                setMessages((prev) => {
                  const next = [...prev]
                  if (next.length > 0) {
                    next[next.length - 1] = {
                      ...next[next.length - 1],
                      mathSteps: [...currentMathSteps],
                    }
                  }
                  return next
                })
              } catch (e) {}
              continue
            }

            if (payload.startsWith('[VISUAL_REF:')) {
              try {
                const jsonStr = payload.replace(/^\[VISUAL_REF:/, '').replace(/\]$/, '')
                const visualObj = JSON.parse(jsonStr)
                currentVisualRefs.push(visualObj)
                setMessages((prev) => {
                  const next = [...prev]
                  if (next.length > 0) {
                    next[next.length - 1] = {
                      ...next[next.length - 1],
                      visualRefs: [...currentVisualRefs],
                    }
                  }
                  return next
                })
              } catch (e) {}
              continue
            }

            if (payload.startsWith('[EVAL_REPORT:')) {
              try {
                const jsonStr = payload.replace(/^\[EVAL_REPORT:/, '').replace(/\]$/, '')
                currentEvaluation = JSON.parse(jsonStr)
                setMessages((prev) => {
                  const next = [...prev]
                  if (next.length > 0) {
                    next[next.length - 1] = {
                      ...next[next.length - 1],
                      evaluation: currentEvaluation,
                    }
                  }
                  return next
                })
              } catch (e) {}
              continue
            }

            if (payload.startsWith('[PAGE_REF:')) {
              const match = payload.match(/\[PAGE_REF:(\d+)\]/)
              if (match) {
                const pageNum = parseInt(match[1])
                setMessages((prev) => {
                  const next = [...prev]
                  if (next.length > 0) {
                    next[next.length - 1] = {
                      ...next[next.length - 1],
                      page_ref: pageNum,
                    }
                  }
                  return next
                })
                if (onPageRef) onPageRef(pageNum)
              }
              continue
            }

            if (payload.startsWith('[ERROR:')) {
              const match = payload.match(/\[ERROR:(.*)\]/)
              const errMsg = match ? match[1] : 'Unknown model error'
              setMessages((prev) => {
                const next = [...prev]
                if (next.length > 0) {
                  next[next.length - 1] = {
                    ...next[next.length - 1],
                    content: fullResponse + `\n\n⚠️ SYSTEM ERROR: ${errMsg}`,
                    isStreaming: false,
                  }
                }
                return next
              })
              setIsStreaming(false)
              setAgentStatus(null)
              continue
            }

            // ── Text Token (Preserve Spaces & Newlines) ───────────
            const token = payload.replace(/\\n/g, '\n')
            fullResponse += token

            const snapshot = fullResponse
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1)
            setMessages((prev) => {
              const next = [...prev]
              if (next.length > 0) {
                next[next.length - 1] = {
                  ...next[next.length - 1],
                  content: snapshot,
                  visualRefs: currentVisualRefs,
                  mathSteps: currentMathSteps,
                  thoughts: currentThoughts,
                  thinkingDuration: elapsed,
                  evaluation: currentEvaluation,
                }
              }
              return next
            })
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      console.error('[useChat] Stream error:', err)
      setMessages((prev) => {
        const next = [...prev]
        if (next.length > 0) {
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: '⚠️ Connection to AeroMind defense server lost. Please verify backend is running.',
            isStreaming: false,
          }
        }
        return next
      })
      setIsStreaming(false)
      setAgentStatus(null)
    } finally {
      setIsStreaming(false)
      abortRef.current = null
      setMessages((prev) => {
        if (prev.length > 0 && prev[prev.length - 1].isStreaming) {
          const next = [...prev]
          next[next.length - 1] = {
            ...next[next.length - 1],
            isStreaming: false,
          }
          return next
        }
        return prev
      })
    }
  }

  return {
    messages,
    sendMessage,
    isStreaming,
    agentStatus,
    dagPlan,
    mathSteps,
    clearChat,
  }
}
