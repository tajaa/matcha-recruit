import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/** The tabs are lazy: a section link's target does not exist until its tab mounts. */
export function useHashScroll() {
  const { hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash])
}
