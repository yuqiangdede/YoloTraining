import { Navigate } from 'react-router-dom'

/** Legacy route component retained only for stale bookmarks. */
export function AssetsPage() { return <Navigate to="/datasets" replace /> }
