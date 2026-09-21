import { useState, useEffect } from 'react'

/**
 * useAircraft.js
 * ───────────────────────────────────────────────────────────────
 * Fetches aircraft & manuals registry from backend.
 * Default state is neutral (null) until selected or document uploaded.
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
    loading,
  }
}
