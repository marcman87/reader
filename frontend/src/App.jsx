import React, { createContext, useContext, useState } from 'react'
import { NavLink, Route, Routes, Link } from 'react-router-dom'
import Directory from './pages/Directory'
import Listing from './pages/Listing'
import Thread from './pages/Thread'
import Board from './pages/Board'
import ChanThread from './pages/ChanThread'
import Search from './pages/Search'

const NsfwCtx = createContext(['sfw', () => {}])
export const useNsfw = () => useContext(NsfwCtx)

const MODES = [
  ['sfw', 'SFW'],
  ['nsfw', 'NSFW'],
  ['all', 'ALL'],
]

export default function App() {
  const [nsfw, setNsfwState] = useState(() => localStorage.getItem('nsfw') || 'sfw')
  const setNsfw = (v) => { localStorage.setItem('nsfw', v); setNsfwState(v) }

  return (
    <NsfwCtx.Provider value={[nsfw, setNsfw]}>
      <header className="topbar">
        <Link to="/" className="brand">READER</Link>
        <nav className="topnav">
          <NavLink to="/" end>directory</NavLink>
          <NavLink to="/search">search</NavLink>
        </nav>
        <div className="spacer" />
        <div className="seg nsfw" role="radiogroup" aria-label="Content filter">
          {MODES.map(([v, label]) => (
            <button key={v} data-v={v} className={nsfw === v ? 'on' : ''}
              aria-checked={nsfw === v} role="radio"
              onClick={() => setNsfw(v)}>{label}</button>
          ))}
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Directory />} />
        <Route path="/search" element={<Search />} />
        <Route path="/r/:sub" element={<Listing />} />
        <Route path="/r/:sub/comments/:id" element={<Thread />} />
        <Route path="/4/:board" element={<Board />} />
        <Route path="/4/:board/thread/:no" element={<ChanThread />} />
      </Routes>
    </NsfwCtx.Provider>
  )
}
