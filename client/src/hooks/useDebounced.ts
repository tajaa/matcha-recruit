import { useEffect, useState } from 'react'

/**
 * The value, trailing-debounced by `ms`.
 *
 * Pairs with `useAsync`: put the debounced value in the deps array and a search
 * box stops issuing one request per keystroke. `useAsync` already discards
 * out-of-order responses, so the debounce is purely about not making the
 * requests — correctness is handled either way.
 *
 *     const debouncedSearch = useDebounced(search, 300)
 *     const { data } = useAsync(() => fetchThings(search), [debouncedSearch])
 *
 * Note the fn still closes over the LIVE value (it is read through a ref by
 * useAsync at call time); only the *trigger* is debounced.
 */
export function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])

  return debounced
}
