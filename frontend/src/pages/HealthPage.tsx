import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '../api/client'

export function HealthPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 10_000,
  })

  return (
    <main>
      <h1>Gas Station Wars</h1>
      <h2>Backend health</h2>
      {isLoading && <p>Checking backend...</p>}
      {isError && <p role="alert">Backend unreachable: {String(error)}</p>}
      {data && (
        <ul>
          <li>Overall: {data.status}</li>
          <li>Database: {data.database}</li>
          <li>Redis: {data.redis}</li>
        </ul>
      )}
    </main>
  )
}
