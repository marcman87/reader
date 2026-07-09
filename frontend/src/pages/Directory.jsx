import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiPost, fmt } from '../api'
import { useNsfw } from '../App'
import { ErrorBox } from '../components/shared'

const PAGE = 50

export default function Directory() {
  const [nsfw] = useNsfw()
  const [tab, setTab] = useState('reddit')
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [boards, setBoards] = useState([])
  const [live, setLive] = useState(null)   // live reddit lookup results
  const [status, setStatus] = useState(null)
  const [err, setErr] = useState(null)
  const debounce = useRef(null)

  const loadLocal = async (query, offset = 0) => {
    const data = await api('/directory', { q: query, nsfw, limit: PAGE, offset })
    setTotal(data.total)
    setRows(offset ? (prev) => [...prev, ...data.subreddits] : data.subreddits)
    if (offset) setRows((prev) => prev) // no-op guard
  }

  useEffect(() => {
    setErr(null)
    if (tab === 'reddit') {
      loadLocal(q).catch(setErr)
    } else {
      api('/chan/boards', { nsfw }).then((d) => setBoards(d.boards)).catch(setErr)
    }
  }, [tab, nsfw]) // eslint-disable-line

  useEffect(() => {
    api('/directory/status').then(setStatus).catch(() => {})
    const iv = setInterval(() => {
      api('/directory/status').then((s) => {
        setStatus(s)
        if (!s.running) clearInterval(iv)
      }).catch(() => {})
    }, 5000)
    return () => clearInterval(iv)
  }, [])

  const onSearch = (v) => {
    setQ(v)
    setLive(null)
    clearTimeout(debounce.current)
    debounce.current = setTimeout(() => loadLocal(v).catch(setErr), 250)
  }

  const liveLookup = async () => {
    setErr(null)
    try {
      const d = await api('/reddit/subreddits/search', { q, nsfw })
      setLive(d.subreddits)
      loadLocal(q).catch(() => {}) // results were upserted; refresh local
    } catch (e) { setErr(e) }
  }

  const crawl = async (mode) => {
    setErr(null)
    try {
      const r = await apiPost('/directory/crawl', { mode })
      setStatus(r)
      const iv = setInterval(() => {
        api('/directory/status').then((s) => {
          setStatus(s)
          if (!s.running) { clearInterval(iv); loadLocal(q).catch(() => {}) }
        })
      }, 4000)
    } catch (e) { setErr(e) }
  }

  const loadMore = async () => {
    const data = await api('/directory', { q, nsfw, limit: PAGE, offset: rows.length })
    setRows([...rows, ...data.subreddits])
  }

  const d = status?.directory
  return (
    <main className="page">
      <div className="controls">
        <div className="seg">
          <button className={tab === 'reddit' ? 'on' : ''} onClick={() => setTab('reddit')}>REDDIT</button>
          <button className={tab === 'chan' ? 'on' : ''} onClick={() => setTab('chan')}>4CHAN</button>
        </div>
        {tab === 'reddit' && (
          <>
            <div className="grow">
              <input type="search" placeholder="Filter local directory… (r/name or title)"
                value={q} onChange={(e) => onSearch(e.target.value)} />
            </div>
            <button className="btn" onClick={liveLookup} disabled={!q}>Search Reddit</button>
          </>
        )}
      </div>
      <ErrorBox err={err} />

      {tab === 'reddit' && (
        <>
          {d && (
            <div className="stats">
              indexed <b>{fmt(d.total)}</b> subreddits ({fmt(d.nsfw)} nsfw)
              {status?.running && <> — crawl <b>{status.mode}</b> running: {status.queries_done} queries, {fmt(status.upserted)} upserted</>}
              {status?.error && <> — last crawl error: {status.error}</>}
            </div>
          )}
          <div className="controls">
            <button className="btn" disabled={status?.running} onClick={() => crawl('seed')}>Seed (~3k, 1 min)</button>
            <button className="btn" disabled={status?.running} onClick={() => crawl('prefix')}>Prefix crawl (~30–60k, ~40 min)</button>
            <button className="btn" disabled={status?.running} onClick={() => crawl('deep')}>Deep crawl (hours)</button>
          </div>

          {live && (
            <>
              <h2 className="section">Live Reddit results</h2>
              <div className="dirlist">
                {live.map((s) => <SubRow key={`live-${s.name}`} s={s} />)}
              </div>
              <h2 className="section">Local directory</h2>
            </>
          )}
          <div className="dirlist">
            {rows.map((s) => <SubRow key={s.name} s={s} />)}
          </div>
          {rows.length === 0 && <div className="empty">
            Directory is empty. Run Seed to populate, or import an Arctic Shift dump (see README).
          </div>}
          {rows.length < total && (
            <button className="btn load-more" onClick={loadMore}>
              load more ({fmt(total - rows.length)} remaining)
            </button>
          )}
        </>
      )}

      {tab === 'chan' && (
        <div className="dirlist">
          {boards.map((b) => (
            <Link key={b.board} to={`/4/${b.board}`} className="card src-chan" style={{ color: 'inherit' }}>
              <span className="name">/{b.board}/</span>
              <span className="desc">{b.title}</span>
              {!b.worksafe && <span className="tag nsfw">NSFW</span>}
            </Link>
          ))}
          {boards.length === 0 && !err && <div className="empty">loading boards…</div>}
        </div>
      )}
    </main>
  )
}

function SubRow({ s }) {
  return (
    <Link to={`/r/${s.name}`} className="card src-reddit" style={{ color: 'inherit' }}>
      <span className="name">r/{s.name}</span>
      <span className="subs">{fmt(s.subscribers)}</span>
      <span className="desc">{s.title || s.description}</span>
      {!!s.over18 && <span className="tag nsfw">NSFW</span>}
    </Link>
  )
}
