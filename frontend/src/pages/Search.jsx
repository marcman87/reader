import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmt } from '../api'
import { useNsfw } from '../App'
import { ErrorBox, PostCard } from '../components/shared'

const SORTS = ['relevance', 'hot', 'top', 'new', 'comments']
const TIMES = ['all', 'year', 'month', 'week', 'day', 'hour']

export default function Search() {
  const [nsfw] = useNsfw()
  const [q, setQ] = useState('')
  const [scope, setScope] = useState('')       // '' = all of reddit, else subreddit name
  const [type, setType] = useState('posts')    // posts | subreddits
  const [sort, setSort] = useState('relevance')
  const [t, setT] = useState('all')
  const [posts, setPosts] = useState([])
  const [subs, setSubs] = useState([])
  const [after, setAfter] = useState(null)
  const [busy, setBusy] = useState(false)
  const [ran, setRan] = useState(false)
  const [err, setErr] = useState(null)

  const run = async (reset = true) => {
    if (!q.trim()) return
    setBusy(true); setErr(null); setRan(true)
    try {
      if (type === 'posts') {
        const d = await api('/reddit/search', {
          q, subreddit: scope || undefined, sort, t, nsfw,
          after: reset ? undefined : after,
        })
        setPosts(reset ? d.posts : [...posts, ...d.posts])
        setAfter(d.after)
        setSubs([])
      } else {
        const d = await api('/reddit/subreddits/search', { q, nsfw })
        setSubs(d.subreddits)
        setPosts([]); setAfter(null)
      }
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <main className="page">
      <div className="controls">
        <div className="grow">
          <input type="search" placeholder="Search Reddit…" value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run()} />
        </div>
        <button className="btn primary" onClick={() => run()} disabled={busy || !q.trim()}>
          {busy ? '…' : 'Search'}
        </button>
      </div>
      <div className="controls">
        <div className="seg">
          <button className={type === 'posts' ? 'on' : ''} onClick={() => setType('posts')}>POSTS</button>
          <button className={type === 'subreddits' ? 'on' : ''} onClick={() => setType('subreddits')}>SUBREDDITS</button>
        </div>
        {type === 'posts' && (
          <>
            <input type="text" style={{ width: 180 }} placeholder="limit to r/… (optional)"
              value={scope} onChange={(e) => setScope(e.target.value.replace(/^r\//, ''))} />
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map((s) => <option key={s}>{s}</option>)}
            </select>
            <select value={t} onChange={(e) => setT(e.target.value)}>
              {TIMES.map((x) => <option key={x}>{x}</option>)}
            </select>
          </>
        )}
        <span className="meta">filter: {nsfw}</span>
      </div>
      <ErrorBox err={err} />

      {posts.map((p) => <PostCard key={p.id} post={p} />)}
      {subs.map((s) => (
        <Link key={s.name} to={`/r/${s.name}`} className="card src-reddit dirlist" style={{ color: 'inherit', display: 'flex', gap: 12 }}>
          <span className="name">r/{s.name}</span>
          <span className="subs">{fmt(s.subscribers)}</span>
          <span className="desc">{s.title || s.description}</span>
          {!!s.over18 && <span className="tag nsfw">NSFW</span>}
        </Link>
      ))}
      {ran && !busy && posts.length === 0 && subs.length === 0 && !err &&
        <div className="empty">no results under the current filter</div>}
      {type === 'posts' && after && (
        <button className="btn load-more" disabled={busy} onClick={() => run(false)}>load more</button>
      )}
      <p className="meta" style={{ marginTop: 30 }}>
        4chan has no search API — open a board from the directory and use the catalog filter there.
      </p>
    </main>
  )
}
