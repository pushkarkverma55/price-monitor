import { useEffect, useMemo, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer,
} from 'recharts'

const inr = (n) => (n == null ? '—' : '₹' + n.toLocaleString('en-IN'))
const CHART_COLORS = ['#38bdf8', '#f472b6', '#a3e635', '#fbbf24', '#c084fc', '#34d399', '#fb7185', '#818cf8']

function shortTitle(p) {
  const bits = []
  if (p.model_line) bits.push(p.model_line)
  const s = p.specs || {}
  if (s.cpu) bits.push(s.cpu)
  if (s.ram_gb) bits.push(s.ram_gb + 'GB')
  if (s.storage) bits.push(s.storage)
  return bits.length ? bits.join(' · ') : (p.title || p.asin).slice(0, 60)
}

function Delta({ now, prev }) {
  if (now == null || prev == null || now === prev) return <span className="text-slate-500">—</span>
  const d = now - prev
  return (
    <span className={d < 0 ? 'text-emerald-400' : 'text-rose-400'}>
      {d < 0 ? '▼' : '▲'} {inr(Math.abs(d))}
    </span>
  )
}

export default function App() {
  const [catalog, setCatalog] = useState(null)
  const [history, setHistory] = useState({})
  const [err, setErr] = useState(null)
  const [q, setQ] = useState('')
  const [ram, setRam] = useState('all')
  const [storage, setStorage] = useState('all')
  const [cpuFam, setCpuFam] = useState('all')
  const [selected, setSelected] = useState([]) // asins charted

  useEffect(() => {
    Promise.all([
      fetch('./data/catalog.json').then((r) => r.json()),
      fetch('./data/history.json').then((r) => r.json()),
    ])
      .then(([c, h]) => {
        setCatalog(c)
        setHistory(h)
        const firstGroup = c.products[0]?.group
        setSelected(c.products.filter((p) => p.group === firstGroup).map((p) => p.asin).slice(0, 6))
      })
      .catch((e) => setErr(String(e)))
  }, [])

  const products = catalog?.products ?? []
  const ramOptions = useMemo(() => [...new Set(products.map((p) => p.specs?.ram_gb).filter(Boolean))].sort((a, b) => a - b), [products])
  const storageOptions = useMemo(() => [...new Set(products.map((p) => p.specs?.storage).filter(Boolean))].sort(), [products])
  const cpuFamOptions = useMemo(() => [...new Set(products.map((p) => p.specs?.cpu_family).filter(Boolean))].sort(), [products])

  const filtered = useMemo(() => products.filter((p) => {
    if (q && !(p.title || '').toLowerCase().includes(q.toLowerCase())) return false
    if (ram !== 'all' && p.specs?.ram_gb !== Number(ram)) return false
    if (storage !== 'all' && p.specs?.storage !== storage) return false
    if (cpuFam !== 'all' && p.specs?.cpu_family !== cpuFam) return false
    return true
  }), [products, q, ram, storage, cpuFam])

  const groups = useMemo(() => {
    const m = new Map()
    for (const p of filtered) {
      if (!m.has(p.group)) m.set(p.group, [])
      m.get(p.group).push(p)
    }
    return [...m.entries()].map(([g, ps]) => [g, ps.sort((a, b) => (a.price ?? 1e9) - (b.price ?? 1e9))])
      .sort((a, b) => b[1].length - a[1].length)
  }, [filtered])

  const chartData = useMemo(() => {
    const byTs = new Map()
    for (const asin of selected) {
      for (const [ts, price] of history[asin] ?? []) {
        const day = ts * 1000
        if (!byTs.has(day)) byTs.set(day, { ts: day })
        byTs.get(day)[asin] = price
      }
    }
    return [...byTs.values()].sort((a, b) => a.ts - b.ts)
  }, [selected, history])

  const toggle = (asin) => setSelected((s) => (s.includes(asin) ? s.filter((x) => x !== asin) : [...s, asin]))
  const byAsin = useMemo(() => Object.fromEntries(products.map((p) => [p.asin, p])), [products])

  if (err) return <div className="p-10 text-rose-400 font-mono text-sm">Failed to load data: {err}</div>
  if (!catalog) return <div className="p-10 text-slate-400 animate-pulse">Loading price data…</div>

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-white">Laptop Price Monitor <span className="text-sky-400">· Amazon.in</span></h1>
        <p className="text-sm text-slate-400 mt-1">
          {products.length} products tracked · updated {new Date(catalog.generated_at * 1000).toLocaleString('en-IN')}
        </p>
      </header>

      {/* trend chart */}
      <section className="bg-slate-900 rounded-xl p-4 mb-6 border border-slate-800">
        <h2 className="text-sm font-semibold text-slate-300 mb-2">
          Price history {selected.length ? `(${selected.length} selected)` : '— tick products below to chart them'}
        </h2>
        <div className="h-72">
          <ResponsiveContainer>
            <LineChart data={chartData}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey="ts" type="number" domain={['dataMin', 'dataMax']} scale="time"
                tickFormatter={(t) => new Date(t).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                stroke="#475569" fontSize={12} />
              <YAxis tickFormatter={(v) => '₹' + (v / 1000).toFixed(1) + 'k'} stroke="#475569" fontSize={12}
                domain={[(min) => Math.floor((min - 2000) / 1000) * 1000, (max) => Math.ceil((max + 2000) / 1000) * 1000]}
                width={60} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                labelFormatter={(t) => new Date(t).toLocaleString('en-IN')}
                formatter={(v, name) => [inr(v), shortTitle(byAsin[name] ?? { asin: name })]} />
              <Legend formatter={(name) => <span className="text-xs">{shortTitle(byAsin[name] ?? { asin: name })}</span>} />
              {selected.map((asin, i) => (
                <Line key={asin} dataKey={asin} stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  dot={{ r: 3 }} strokeWidth={2} connectNulls isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* filters */}
      <section className="flex flex-wrap gap-2 mb-4 text-sm">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title…"
          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 w-56 placeholder-slate-500 focus:outline-none focus:border-sky-500" />
        {[['RAM', ram, setRam, ramOptions.map((r) => [r, r + 'GB'])],
          ['Storage', storage, setStorage, storageOptions.map((s) => [s, s])],
          ['CPU', cpuFam, setCpuFam, cpuFamOptions.map((c) => [c, c])]].map(([label, val, set, opts]) => (
          <select key={label} value={val} onChange={(e) => set(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 focus:outline-none">
            <option value="all">{label}: all</option>
            {opts.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        ))}
        <span className="self-center text-slate-500 ml-auto">{filtered.length} shown</span>
      </section>

      {/* variant groups */}
      {groups.map(([g, ps]) => (
        <section key={g} className="mb-5 bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <div className="px-4 py-2 bg-slate-800/60 flex items-baseline gap-2">
            <h3 className="font-semibold text-slate-100">{ps[0].brand} {ps[0].model_line || ps[0].title?.slice(0, 40)}</h3>
            <span className="text-xs text-slate-400">{ps.length} variant{ps.length > 1 ? 's' : ''}</span>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 border-b border-slate-800">
                <th className="px-4 py-2 w-8"></th>
                <th className="py-2">Configuration</th>
                <th className="py-2 text-right">Price</th>
                <th className="py-2 text-right">Δ last</th>
                <th className="py-2 text-right">Min–Max</th>
                <th className="py-2 text-right">Rating</th>
                <th className="py-2 text-right pr-4">Stock</th>
              </tr>
            </thead>
            <tbody>
              {ps.map((p) => (
                <tr key={p.asin} className="border-b border-slate-800/60 hover:bg-slate-800/30">
                  <td className="px-4 py-2">
                    <input type="checkbox" checked={selected.includes(p.asin)} onChange={() => toggle(p.asin)}
                      className="accent-sky-500" />
                  </td>
                  <td className="py-2">
                    <a href={p.url} target="_blank" rel="noreferrer" className="hover:text-sky-400" title={p.title}>
                      {shortTitle(p)}
                    </a>
                  </td>
                  <td className="py-2 text-right font-semibold text-white">{inr(p.price)}
                    {p.mrp && p.price && p.mrp > p.price && (
                      <span className="block text-[11px] font-normal text-slate-500 line-through">{inr(p.mrp)}</span>
                    )}
                  </td>
                  <td className="py-2 text-right"><Delta now={p.price} prev={p.prev_price} /></td>
                  <td className="py-2 text-right text-slate-400 text-xs">
                    {p.min_price === p.max_price ? inr(p.min_price) : `${inr(p.min_price)} – ${inr(p.max_price)}`}
                  </td>
                  <td className="py-2 text-right text-amber-300">
                    {p.rating ? `★ ${p.rating}` : '—'}
                    {p.ratings_count ? <span className="text-slate-500 text-xs"> ({p.ratings_count})</span> : null}
                  </td>
                  <td className="py-2 text-right pr-4">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${/in stock/i.test(p.availability || '')
                      ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
                      {p.availability || 'unknown'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}

      <footer className="text-xs text-slate-600 mt-8">
        Data scraped every 6h from Amazon.in · history accumulates from first tracking day · personal use
      </footer>
    </div>
  )
}
