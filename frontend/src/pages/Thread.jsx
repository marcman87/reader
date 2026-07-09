import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { Comment, ErrorBox, PostCard } from '../components/shared'

const CSORTS = [['confidence', 'best'], ['top', 'top'], ['new', 'new'], ['controversial', 'controversial'], ['old', 'old'], ['qa', 'q&a']]

export default function Thread() {
  const { sub, id } = useParams()
  const [sort, setSort] = useState('confidence')
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setErr(null); setData(null)
    api(`/reddit/comments/${sub}/${id}`, { sort }).then(setData).catch(setErr)
  }, [sub, id, sort])

  return (
    <main className="page">
      <ErrorBox err={err} />
      {!data && !err && <div className="empty">loading thread…</div>}
      {data && (
        <>
          <PostCard post={data.post} expandMedia />
          <div className="controls">
            <span className="meta">comments</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {CSORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          {data.comments.map((c) => <Comment key={c.id} c={c} />)}
          {data.comments.length === 0 && <div className="empty">no comments yet</div>}
        </>
      )}
    </main>
  )
}
