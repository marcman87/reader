import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ago } from '../api'
import { api } from '../api'
import { ChanHtml, ErrorBox } from '../components/shared'

function ChanMedia({ media }) {
  const [full, setFull] = useState(false)
  if (!media) return null
  if (media.kind === 'video') {
    return (
      <div className="chan-media">
        {full
          ? <video src={media.url} controls autoPlay playsInline loop />
          : <img src={media.thumb} alt="" style={{ cursor: 'pointer' }} onClick={() => setFull(true)} />}
        <div className="meta">{media.filename}</div>
      </div>
    )
  }
  return (
    <div className="chan-media">
      <img src={full ? media.url : media.thumb} alt=""
        style={{ cursor: 'pointer' }} onClick={() => setFull(!full)} loading="lazy" />
      <div className="meta">{media.filename} {media.w}×{media.h}</div>
    </div>
  )
}

export default function ChanThread() {
  const { board, no } = useParams()
  const [posts, setPosts] = useState([])
  const [err, setErr] = useState(null)

  const load = () => {
    setErr(null)
    api(`/chan/${board}/thread/${no}`).then((d) => setPosts(d.posts)).catch(setErr)
  }
  useEffect(load, [board, no]) // eslint-disable-line

  const op = posts[0]
  return (
    <main className="page">
      <div className="controls">
        <Link to={`/4/${board}`} className="meta">← /{board}/</Link>
        <div className="spacer" />
        <button className="btn" onClick={load}>refresh</button>
        <span className="meta">{posts.length} posts</span>
      </div>
      <ErrorBox err={err} />
      {op?.sub && <h3 className="post-title" style={{ marginTop: 0 }}>{op.sub}</h3>}
      {posts.map((p) => (
        <article key={p.no} id={`p${p.no}`} className="card src-chan chan-post">
          <div className="meta">
            <span style={{ color: 'var(--chan)' }}>{p.name}</span>
            {p.trip && <span className="sep">{p.trip}</span>}
            <span className="sep">·</span>No.{p.no}
            <span className="sep">·</span>{ago(p.time)}
            {p.sticky && <span className="tag">pinned</span>}
            {p.closed && <span className="tag">closed</span>}
          </div>
          <ChanMedia media={p.media} />
          <ChanHtml html={p.com} />
        </article>
      ))}
      {posts.length === 0 && !err && <div className="empty">loading thread…</div>}
    </main>
  )
}
