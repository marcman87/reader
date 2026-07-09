import React, { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { ChanHtml, ErrorBox } from '../components/shared'

export default function Board() {
  const { board } = useParams()
  const [threads, setThreads] = useState([])
  const [q, setQ] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const debounce = useRef(null)

  const load = (query) => {
    setBusy(true); setErr(null)
    api(`/chan/${board}/catalog`, { q: query })
      .then((d) => setThreads(d.threads))
      .catch(setErr)
      .finally(() => setBusy(false))
  }

  useEffect(() => { setQ(''); load('') }, [board]) // eslint-disable-line

  const onFilter = (v) => {
    setQ(v)
    clearTimeout(debounce.current)
    debounce.current = setTimeout(() => load(v), 300)
  }

  return (
    <main className="page page-wide">
      <div className="controls">
        <span className="meta" style={{ fontSize: 14 }}>/{board}/</span>
        <div className="grow">
          <input type="search" placeholder="Filter catalog (subject + text)…"
            value={q} onChange={(e) => onFilter(e.target.value)} />
        </div>
        <span className="meta">{threads.length} threads</span>
      </div>
      <ErrorBox err={err} />
      {busy && threads.length === 0 && <div className="empty">loading catalog…</div>}
      <div className="catalog">
        {threads.map((t) => (
          <Link key={t.no} to={`/4/${board}/thread/${t.no}`} className="card src-chan" style={{ color: 'inherit' }}>
            {t.media?.thumb && <img className="cat-thumb" src={t.media.thumb} alt="" loading="lazy" />}
            <div className="meta">R:{t.replies ?? 0} I:{t.images ?? 0}{t.sticky ? ' · pinned' : ''}</div>
            {t.sub && <div className="sub">{t.sub}</div>}
            <div className="excerpt"><ChanHtml html={t.com} /></div>
          </Link>
        ))}
      </div>
      {!busy && threads.length === 0 && !err && <div className="empty">no threads match</div>}
    </main>
  )
}
