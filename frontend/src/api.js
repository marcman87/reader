export async function api(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  const res = await fetch(`/api${path}${qs ? `?${qs}` : ''}`)
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* noop */ }
    // bare gateway errors (Cloudflare/proxy HTML) have no JSON detail
    throw new Error(detail || `${res.status} — upstream is slow or rate-limited; wait a moment and retry`)
  }
  return res.json()
}

export async function apiPost(path, params = {}) {
  const qs = new URLSearchParams(params).toString()
  const res = await fetch(`/api${path}${qs ? `?${qs}` : ''}`, { method: 'POST' })
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json()
}

export function ago(utc) {
  if (!utc) return ''
  const s = Math.max(1, Math.floor(Date.now() / 1000 - utc))
  const u = [[31536000, 'y'], [2592000, 'mo'], [86400, 'd'], [3600, 'h'], [60, 'm']]
  for (const [sec, label] of u) if (s >= sec) return `${Math.floor(s / sec)}${label}`
  return `${s}s`
}

export function fmt(n) {
  if (n == null) return ''
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}m`
  if (n >= 1e4) return `${(n / 1e3).toFixed(0)}k`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`
  return `${n}`
}
