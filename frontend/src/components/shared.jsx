import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { ago, fmt } from '../api'

marked.setOptions({ breaks: true, gfm: true })

// External links open in a new tab
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A' && node.getAttribute('href')?.startsWith('http')) {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function Markdown({ text }) {
  if (!text) return null
  const html = DOMPurify.sanitize(marked.parse(text))
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
}

// Reddit-rendered HTML bodies (RSS feeds ship HTML, not markdown source)
export function RedditHtml({ html }) {
  if (!html) return null
  return <div className="md" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }} />
}

export function ChanHtml({ html }) {
  if (!html) return null
  const clean = DOMPurify.sanitize(html, { ADD_ATTR: ['class'] })
  const onClick = (e) => {
    const a = e.target.closest('a.quotelink')
    if (a) {
      e.preventDefault()
      const id = a.getAttribute('href')?.replace('#', '')
      document.getElementById(id)?.scrollIntoView({ block: 'center' })
    }
  }
  return <div className="chan-com" onClick={onClick}
    dangerouslySetInnerHTML={{ __html: clean }} />
}

function DashVideo({ src, poster }) {
  const ref = useRef(null)
  useEffect(() => {
    let player
    let cancelled = false
    import('dashjs').then((dashjs) => {
      if (cancelled || !ref.current) return
      player = dashjs.MediaPlayer().create()
      player.initialize(ref.current, src, false)
    })
    return () => { cancelled = true; try { player?.destroy() } catch { /* noop */ } }
  }, [src])
  return <video ref={ref} controls playsInline preload="metadata" poster={poster} />
}

export function Media({ media, thumb }) {
  const [idx, setIdx] = useState(0)
  if (!media) return null
  if (media.kind === 'image') {
    return <div className="media-wrap"><img src={media.url} alt="" loading="lazy" /></div>
  }
  if (media.kind === 'gallery' && media.items?.length) {
    const it = media.items[idx]
    return (
      <div className="media-wrap">
        <img src={it.url} alt="" />
        {media.items.length > 1 && (
          <div className="gallery-nav">
            <button className="btn" onClick={() => setIdx((idx - 1 + media.items.length) % media.items.length)}>‹ prev</button>
            <span className="idx">{idx + 1} / {media.items.length}</span>
            <button className="btn" onClick={() => setIdx((idx + 1) % media.items.length)}>next ›</button>
          </div>
        )}
      </div>
    )
  }
  if (media.kind === 'video') {
    return (
      <div className="media-wrap">
        {media.dash
          ? <DashVideo src={media.dash} poster={thumb} />
          : <video src={media.fallback} controls playsInline poster={thumb} />}
      </div>
    )
  }
  if (media.kind === 'rawvideo') {
    return <div className="media-wrap"><video src={media.url} controls playsInline loop /></div>
  }
  return null
}

export function PostCard({ post, expandMedia = false }) {
  const to = `/r/${post.subreddit}/comments/${post.id}`
  return (
    <article className="card src-reddit">
      <div className="post-row">
        <div className="post-body">
          <div className="meta">
            <Link to={`/r/${post.subreddit}`}>r/{post.subreddit}</Link>
            <span className="sep">·</span>u/{post.author}
            <span className="sep">·</span>{ago(post.created_utc)}
            {post.over_18 && <span className="tag nsfw">NSFW</span>}
            {post.link_flair_text && <span className="tag flair">{post.link_flair_text}</span>}
            {post.stickied && <span className="tag">pinned</span>}
          </div>
          <h3 className="post-title"><Link to={to}>{post.title}</Link></h3>
          <div className="meta">
            {post.score != null && <>▲ {fmt(post.score)}<span className="sep">·</span></>}
            <Link to={to}>{post.num_comments != null ? `${fmt(post.num_comments)} comments` : 'comments'}</Link>
            {post.media.kind === 'link' && post.url && (
              <><span className="sep">·</span>
                <a href={post.url} target="_blank" rel="noopener noreferrer">{post.domain}</a></>
            )}
          </div>
          {expandMedia && (post.selftext_html
            ? <RedditHtml html={post.selftext_html} />
            : post.selftext && <Markdown text={post.selftext} />)}
        </div>
        {!expandMedia && post.thumb && <img className="thumb" src={post.thumb} alt="" loading="lazy" />}
      </div>
      {expandMedia && <Media media={post.media} thumb={post.thumb} />}
    </article>
  )
}

export function Comment({ c }) {
  const [collapsed, setCollapsed] = useState(false)
  if (c.more) {
    return c.count > 0
      ? <div className="comment"><span className="meta">{c.count} more replies (open thread on reddit to expand)</span></div>
      : null
  }
  return (
    <div className={`comment${collapsed ? ' collapsed' : ''}`} id={`c-${c.id}`}>
      <div className="meta">
        <button className="c-toggle" onClick={() => setCollapsed(!collapsed)}>
          [{collapsed ? '+' : '−'}]
        </button>
        <span className={c.is_submitter ? 'op-badge' : c.distinguished ? 'mod-badge' : ''}>
          u/{c.author}
        </span>
        {c.score != null && <><span className="sep">·</span>▲ {fmt(c.score)}</>}
        <span className="sep">·</span>{ago(c.created_utc)}
      </div>
      {!collapsed && (c.body_html ? <RedditHtml html={c.body_html} /> : <Markdown text={c.body} />)}
      {!collapsed && c.replies?.map((r) => <Comment key={r.id} c={r} />)}
    </div>
  )
}

export function ErrorBox({ err }) {
  if (!err) return null
  return <div className="error-box">{String(err.message || err)}</div>
}
