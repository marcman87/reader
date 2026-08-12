import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, fmt } from '../api'
import { useNsfw } from '../App'
import { ErrorBox, PostCard } from '../components/shared'

const SORTS = ['hot', 'new', 'top', 'rising']
const TIMES = ['hour', 'day', 'week', 'month', 'year', 'all']

export default function Listing() {
  const { sub } = useParams()
  const [nsfw] = useNsfw()
  const [sort, setSort] = useState('hot')
  const [t, setT] = useState('day')
  const [posts, setPosts] = useState([])
  const [after, setAfter] = useState(null)
  const [about, setAbout] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = async (reset) => {
    setBusy(true); setErr(null)
    try {
      const d = await api('/reddit/listing', {
        subreddit: sub, sort, t, nsfw, after: reset ? undefined : after,
      })
      setPosts(reset ? d.posts : [...posts, ...d.posts])
      setAfter(d.after)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  useEffect(() => { load(true) }, [sub, sort, t, nsfw]) // eslint-disable-line
  useEffect(() => {
    api(`/reddit/r/${sub}/about`).then(setAbout).catch(() => {})
  }, [sub])

  return (
    <main className="page">
      <div className="meta" style={{ marginBottom: 4 }}>
        r/{sub}{about && <>
          {about.subscribers != null && <> <span className="sep">·</span>{fmt(about.subscribers)} subscribers</>}
          {about.over18 ? <span className="tag nsfw">NSFW</span> : null}</>}
      </div>
      {about?.description && <p style={{ color: 'var(--muted)', margin: '2px 0 0', fontSize: 13.5 }}>{about.description}</p>}
      <div className="controls">
        <select value={sort} onChange={(e) => setSort(e.target.value)}>
          {SORTS.map((s) => <option key={s}>{s}</option>)}
        </select>
        {sort === 'top' && (
          <select value={t} onChange={(e) => setT(e.target.value)}>
            {TIMES.map((x) => <option key={x}>{x}</option>)}
          </select>
        )}
      </div>
      <ErrorBox err={err} />
      {posts.map((p) => <PostCard key={p.id} post={p} />)}
      {posts.length === 0 && !busy && !err && <div className="empty">nothing here under the current filter</div>}
      {after && <button className="btn load-more" disabled={busy} onClick={() => load(false)}>
        {busy ? 'loading…' : 'load more'}
      </button>}
    </main>
  )
}
