import { useState, useEffect } from 'react'

/**
 * useAircraft.js
 * ───────────────────────────────────────────────────────────────
 * Fetches aircraft registry from backend. Manages selection state.
 */

export default function useAircraft() {
  const [aircraft, setAircraft] = useState([])
  const [selectedAircraft, setSelectedAircraft] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchAircraft = async () => {
      try {
        const res = await fetch('/api/aircraft')
        if (res.ok) {
          const data = await res.json()
          setAircraft(data)
          
          // Auto-select first available aircraft with PDF
          const defaultAC = data.find(ac => ac.pdf_available) || data[0]
          setSelectedAircraft(defaultAC)
        }
      } catch (e) {
        console.error('Failed to fetch aircraft registry:', e)
      } finally {
        setLoading(false)
      }
    }

    fetchAircraft()
  }, [])

  return {
    aircraft,
    selectedAircraft,
    setSelectedAircraft,
    loading
  }
}
