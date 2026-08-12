import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { Comment, ErrorBox, PostCard } from '../components/shared'

export default function Thread() {
  const { sub, id } = useParams()
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setErr(null); setData(null)
    api(`/reddit/comments/${sub}/${id}`).then(setData).catch(setErr)
  }, [sub, id])

  return (
    <main className="page">
      <ErrorBox err={err} />
      {!data && !err && <div className="empty">loading thread…</div>}
      {data && (
        <>
          <PostCard post={data.post} expandMedia />
          <div className="controls">
            <span className="meta">comments (feed order — scores and reply nesting aren't in RSS)</span>
          </div>
          {data.comments.map((c) => <Comment key={c.id} c={c} />)}
          {data.comments.length === 0 && <div className="empty">no comments yet</div>}
        </>
      )}
    </main>
  )
}
