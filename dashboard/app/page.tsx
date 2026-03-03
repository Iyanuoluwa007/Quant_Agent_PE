'use client';

import { useState, useEffect } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, BarChart, Bar, Cell, ScatterChart, Scatter,
  ReferenceLine, Legend,
} from 'recharts';

// ── Types ────────────────────────────────────────────────────────

interface DemoData {
  meta: any;
  performance: any;
  positions: any[];
  recent_trades: any[];
  risk: any;
  intelligence: any;
  etf_review: any;
}

// ── Helpers ──────────────────────────────────────────────────────

const fmt = (n: number, dec = 2) => n.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
const fmtUsd = (n: number) => '$' + fmt(n);
const fmtPct = (n: number) => (n >= 0 ? '+' : '') + fmt(n) + '%';
const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
};
const fmtTime = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
};
const pnlColor = (n: number) => n >= 0 ? 'text-emerald-400' : 'text-red-400';
const sleeveName = (s: string) => s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());

// ── Subcomponents ────────────────────────────────────────────────

function KpiCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="card p-4">
      <div className="section-label mb-2">{label}</div>
      <div className={`mono text-xl font-semibold tabular ${color || 'text-slate-100'}`}>
        {value}
      </div>
      {sub && <div className="mono text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

function SectionHeader({ id, label, badge }: { id: string; label: string; badge?: string }) {
  return (
    <div id={id} className="flex items-center gap-3 mb-4 pt-2">
      <div className="section-label text-xs">{label}</div>
      <div className="flex-1 h-px bg-gradient-to-r from-slate-700/60 to-transparent" />
      {badge && <span className="badge badge-muted">{badge}</span>}
    </div>
  );
}

function NavDot({ id, label, active }: { id: string; label: string; active: boolean }) {
  return (
    <a
      href={`#${id}`}
      className={`flex items-center gap-2 px-3 py-1.5 text-xs transition-colors hover:text-slate-200 ${active ? 'text-slate-200' : 'text-slate-500'}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-blue-400' : 'bg-slate-600'}`} />
      <span className="mono tracking-wide">{label}</span>
    </a>
  );
}

// ── Custom Tooltip ───────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card p-2 text-xs mono border-slate-600">
      <div className="text-slate-400 mb-1">{label}</div>
      {payload.map((p: any, i: number) => (
        <div key={i} className="flex gap-2">
          <span style={{ color: p.color }}>{p.name}:</span>
          <span className="text-slate-200">{typeof p.value === 'number' ? fmt(p.value) : p.value}</span>
        </div>
      ))}
    </div>
  );
}

// ── Main Dashboard ───────────────────────────────────────────────

export default function Dashboard() {
  const [data, setData] = useState<DemoData | null>(null);
  const [activeSection, setActiveSection] = useState('overview');
  const [posSort, setPosSort] = useState<'sleeve' | 'pnl' | 'value'>('sleeve');

  useEffect(() => {
    fetch('/demo_data.json')
      .then(r => r.json())
      .then(setData)
      .catch(console.error);
  }, []);

  // Track active section on scroll
  useEffect(() => {
    const sections = ['overview', 'performance', 'positions', 'risk', 'etf-review'];
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(e => {
          if (e.isIntersecting) setActiveSection(e.target.id);
        });
      },
      { rootMargin: '-20% 0px -60% 0px' }
    );
    sections.forEach(id => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [data]);

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="mono text-sm text-slate-500">Loading demo data...</div>
      </div>
    );
  }

  const { meta, performance: perf, positions, recent_trades, risk, intelligence, etf_review } = data;

  // Sort positions
  const sortedPositions = [...positions].sort((a, b) => {
    if (posSort === 'pnl') return b.pnl_pct - a.pnl_pct;
    if (posSort === 'value') return b.market_value - a.market_value;
    return a.sleeve.localeCompare(b.sleeve);
  });

  const totalInvested = positions.reduce((s: number, p: any) => s + p.market_value, 0);
  const totalPnl = positions.reduce((s: number, p: any) => s + p.pnl, 0);

  return (
    <div className="min-h-screen">
      {/* ═══ TOP BAR ═══ */}
      <header className="sticky top-0 z-50 border-b border-slate-800/80 backdrop-blur-md bg-surface-0/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 bg-emerald-400 pulse-dot" />
            <span className="mono text-sm font-semibold tracking-wider text-slate-200">
              QUANT AGENT
            </span>
            <span className="mono text-xs text-slate-500 hidden sm:inline">v{meta.version}</span>
          </div>

          <nav className="hidden md:flex items-center">
            {[
              ['overview', 'Overview'],
              ['performance', 'Performance'],
              ['positions', 'Book'],
              ['risk', 'Risk'],
              ['etf-review', 'ETF Review'],
            ].map(([id, label]) => (
              <NavDot key={id} id={id} label={label} active={activeSection === id} />
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <span className="badge badge-amber">Demo Mode</span>
            <span className="badge badge-muted hidden sm:inline-flex">Simulated</span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-8">

        {/* ═══ 1. OVERVIEW ═══ */}
        <section id="overview" className="fade-up stagger-1">
          <div className="card p-5 mb-6 relative overflow-hidden">
            <div className="absolute inset-0 grid-bg opacity-[0.04]" />
            <div className="relative">
              <h1 className="text-lg font-semibold text-slate-100 mb-1">
                Quant Agent Public Edition
              </h1>
              <p className="text-sm text-slate-400 max-w-2xl leading-relaxed">
                Multi-strategy AI trading system with regime-aware risk management,
                Claude confidence calibration, and quantitative portfolio construction.
                Three independent strategy sleeves with deterministic risk governance.
              </p>
              <div className="flex flex-wrap items-center gap-3 mt-4">
                <span className="badge badge-amber">No Live Trading</span>
                <span className="badge badge-blue">Paper-Traded Results</span>
                <span className="badge badge-muted">Broker: {meta.broker}</span>
                <span className="mono text-xs text-slate-500">
                  Last updated: {fmtDate(meta.last_updated)} {fmtTime(meta.last_updated)} UTC
                </span>
              </div>
            </div>
          </div>

          {/* KPI Row */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <KpiCard
              label="Portfolio Value"
              value={fmtUsd(perf.current_value)}
              sub={`${fmtPct(perf.total_return_pct)} from ${fmtUsd(meta.initial_capital)}`}
              color={pnlColor(perf.total_return_pct)}
            />
            <KpiCard
              label="Max Drawdown"
              value={fmtPct(perf.max_drawdown_pct)}
              sub="Peak to trough"
              color="text-red-400"
            />
            <KpiCard
              label="Sharpe Ratio"
              value={fmt(perf.sharpe_ratio)}
              sub={`Sortino: ${fmt(perf.sortino_ratio)}`}
            />
            <KpiCard
              label="Win Rate"
              value={perf.win_rate_pct + '%'}
              sub={`${perf.total_trades} trades`}
            />
            <KpiCard
              label="Profit Factor"
              value={fmt(perf.profit_factor)}
              sub={`Calmar: ${fmt(perf.calmar_ratio)}`}
            />
            <KpiCard
              label="Regime"
              value={risk.regime}
              sub={`VIX ${fmt(risk.vix_level, 1)} | Beta ${fmt(risk.portfolio_beta)}`}
              color="text-blue-400"
            />
          </div>
        </section>

        {/* ═══ 2. PERFORMANCE ═══ */}
        <section id="performance" className="fade-up stagger-2">
          <SectionHeader id="performance-h" label="Performance" badge={`${perf.equity_curve.length} data points`} />

          {/* Equity Curve */}
          <div className="card p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
              <span className="section-label">Equity Curve</span>
              <span className="mono text-xs text-slate-500">Sep 2025 - Feb 2026</span>
            </div>
            <div style={{ height: 280 }}>
              <ResponsiveContainer>
                <AreaChart data={perf.equity_curve} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                  <defs>
                    <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v: string) => {
                      const d = new Date(v);
                      return d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
                    }}
                    tick={{ fontSize: 10, fill: '#64748b' }}
                    axisLine={{ stroke: '#1e293b' }}
                    tickLine={false}
                  />
                  <YAxis
                    domain={['dataMin - 2000', 'dataMax + 1000']}
                    tickFormatter={(v: number) => '$' + (v / 1000).toFixed(0) + 'k'}
                    tick={{ fontSize: 10, fill: '#64748b' }}
                    axisLine={false}
                    tickLine={false}
                    width={50}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <ReferenceLine y={100000} stroke="#334155" strokeDasharray="4 4" label="" />
                  <Area
                    type="monotone"
                    dataKey="value"
                    name="Portfolio"
                    stroke="#10b981"
                    strokeWidth={1.5}
                    fill="url(#eqGrad)"
                    dot={false}
                    activeDot={{ r: 3, fill: '#10b981', stroke: '#060a12', strokeWidth: 2 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Returns */}
            <div className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="section-label">Daily Returns (Last 5)</span>
              </div>
              <div style={{ height: 160 }}>
                <ResponsiveContainer>
                  <BarChart data={perf.daily_returns} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" tickFormatter={(v: string) => fmtDate(v)} tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={(v: number) => v + '%'} tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip content={<ChartTooltip />} />
                    <ReferenceLine y={0} stroke="#334155" />
                    <Bar dataKey="pct" name="Return" radius={[1, 1, 0, 0]}>
                      {perf.daily_returns.map((_: any, i: number) => (
                        <Cell key={i} fill={perf.daily_returns[i].pct >= 0 ? '#10b981' : '#ef4444'} fillOpacity={0.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Sleeve Allocation */}
            <div className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="section-label">Sleeve Allocation Over Time</span>
              </div>
              <div style={{ height: 160 }}>
                <ResponsiveContainer>
                  <AreaChart data={perf.sleeve_allocation_history} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(v: string) => {
                        const d = new Date(v);
                        return d.toLocaleDateString('en-GB', { month: 'short' });
                      }}
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis tickFormatter={(v: number) => v + '%'} tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} width={35} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="long_term" name="Long-Term" stackId="1" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.5} />
                    <Area type="monotone" dataKey="mid_term" name="Mid-Term" stackId="1" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.5} />
                    <Area type="monotone" dataKey="short_term" name="Short-Term" stackId="1" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.5} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Performance by Sleeve */}
          <div className="grid grid-cols-3 gap-3 mt-4">
            {Object.entries(intelligence.accuracy_by_sleeve).map(([sleeve, stats]: [string, any]) => (
              <div key={sleeve} className="card p-3">
                <div className="section-label mb-2">{sleeveName(sleeve)}</div>
                <div className="grid grid-cols-3 gap-2 mono text-xs">
                  <div>
                    <div className="text-slate-500 mb-0.5">Win Rate</div>
                    <div className={pnlColor(stats.win_rate - 50)}>{stats.win_rate}%</div>
                  </div>
                  <div>
                    <div className="text-slate-500 mb-0.5">Avg Return</div>
                    <div className={pnlColor(stats.avg_return)}>{fmtPct(stats.avg_return)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 mb-0.5">Trades</div>
                    <div className="text-slate-300">{stats.trades}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ═══ 3. POSITIONS & TRADES ═══ */}
        <section id="positions" className="fade-up stagger-3">
          <SectionHeader id="positions-h" label="Positions & Trades" badge="Sanitized Demo Data" />

          {/* Positions Table */}
          <div className="card mb-4 overflow-hidden">
            <div className="flex items-center justify-between p-3 border-b border-slate-800/60">
              <div className="flex items-center gap-3">
                <span className="section-label">Open Positions</span>
                <span className="mono text-xs text-slate-500">{positions.length} active</span>
              </div>
              <div className="flex gap-1">
                {(['sleeve', 'pnl', 'value'] as const).map(s => (
                  <button
                    key={s}
                    onClick={() => setPosSort(s)}
                    className={`mono text-xs px-2 py-0.5 transition-colors ${posSort === s ? 'text-blue-400 bg-blue-400/10' : 'text-slate-500 hover:text-slate-300'}`}
                  >
                    {s === 'pnl' ? 'P&L' : s === 'value' ? 'Value' : 'Sleeve'}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Sleeve</th>
                    <th className="num">Qty</th>
                    <th className="num">Avg Price</th>
                    <th className="num">Current</th>
                    <th className="num">Mkt Value</th>
                    <th className="num">P&L</th>
                    <th className="num">P&L %</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPositions.map((p, i) => (
                    <tr key={i}>
                      <td className="font-semibold text-slate-200">{p.ticker}</td>
                      <td>
                        <span className={`badge ${
                          p.sleeve === 'short_term' ? 'badge-amber' :
                          p.sleeve === 'mid_term' ? 'badge-blue' : 'badge-green'
                        }`}>
                          {p.sleeve.replace('_term', '')}
                        </span>
                      </td>
                      <td className="num">{fmt(p.quantity, 1)}</td>
                      <td className="num">{fmtUsd(p.avg_price)}</td>
                      <td className="num">{fmtUsd(p.current_price)}</td>
                      <td className="num text-slate-300">{fmtUsd(p.market_value)}</td>
                      <td className={`num ${pnlColor(p.pnl)}`}>{(p.pnl >= 0 ? '+$' : '-$') + fmt(Math.abs(p.pnl))}</td>
                      <td className={`num ${pnlColor(p.pnl_pct)}`}>{fmtPct(p.pnl_pct)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={5} className="text-slate-400 font-medium">Total Invested</td>
                    <td className="num text-slate-200 font-medium">{fmtUsd(totalInvested)}</td>
                    <td className={`num font-medium ${pnlColor(totalPnl)}`}>{(totalPnl >= 0 ? '+$' : '-$') + fmt(Math.abs(totalPnl))}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Trades Table */}
          <div className="card overflow-hidden">
            <div className="flex items-center gap-3 p-3 border-b border-slate-800/60">
              <span className="section-label">Recent Trades</span>
              <span className="mono text-xs text-slate-500">Last 10</span>
            </div>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Action</th>
                    <th>Ticker</th>
                    <th className="num">Qty</th>
                    <th className="num">Fill Price</th>
                    <th>Sleeve</th>
                    <th className="num">Conf</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {recent_trades.map((t: any, i: number) => (
                    <tr key={i}>
                      <td className="text-slate-400 whitespace-nowrap">{fmtDate(t.timestamp)} {fmtTime(t.timestamp)}</td>
                      <td>
                        <span className={`badge ${t.action === 'BUY' ? 'badge-green' : 'badge-red'}`}>
                          {t.action}
                        </span>
                      </td>
                      <td className="font-semibold text-slate-200">{t.ticker}</td>
                      <td className="num">{fmt(t.quantity, 1)}</td>
                      <td className="num">{fmtUsd(t.fill_price)}</td>
                      <td>
                        <span className={`badge ${
                          t.sleeve === 'short_term' ? 'badge-amber' :
                          t.sleeve === 'mid_term' ? 'badge-blue' : 'badge-green'
                        }`}>
                          {t.sleeve.replace('_term', '')}
                        </span>
                      </td>
                      <td className="num">{(t.confidence * 100).toFixed(0)}%</td>
                      <td className="text-slate-400 text-xs max-w-[200px] truncate" title={t.reason}>{t.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ═══ 4. RISK & GOVERNANCE ═══ */}
        <section id="risk" className="fade-up stagger-4">
          <SectionHeader id="risk-h" label="Risk & Governance" badge={`Regime: ${risk.regime}`} />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
            {/* Risk State */}
            <div className="card p-4">
              <div className="section-label mb-3">Current State</div>
              <div className="space-y-2.5 mono text-xs">
                {[
                  ['Regime', risk.regime, 'text-blue-400'],
                  ['VIX', fmt(risk.vix_level, 1), ''],
                  ['Risk Multiplier', fmt(risk.risk_multiplier, 2) + 'x', ''],
                  ['Vol Scalar', fmt(risk.vol_scalar, 3), ''],
                  ['Portfolio Beta', fmt(risk.portfolio_beta, 2), ''],
                  ['Beta Range', `[${risk.beta_target_range[0]} - ${risk.beta_target_range[1]}]`, 'text-slate-400'],
                  ['Exposure', fmt(risk.total_exposure_pct, 1) + '%', ''],
                  ['Cash Reserve', fmt(risk.cash_reserve_pct, 1) + '%', risk.cash_reserve_pct >= 15 ? 'text-emerald-400' : 'text-red-400'],
                ].map(([label, val, color], i) => (
                  <div key={i} className="flex justify-between">
                    <span className="text-slate-500">{label}</span>
                    <span className={color || 'text-slate-300'}>{val}</span>
                  </div>
                ))}
                <div className="flex justify-between pt-2 border-t border-slate-800/60">
                  <span className="text-slate-500">Kill Switch</span>
                  <span className={risk.kill_switch_active ? 'text-red-400 font-semibold' : 'text-emerald-400'}>
                    {risk.kill_switch_active ? 'ACTIVE' : 'Inactive'}
                  </span>
                </div>
              </div>
            </div>

            {/* Risk Limits */}
            <div className="card p-4">
              <div className="section-label mb-3">Governance Limits</div>
              <div className="space-y-2 mono text-xs">
                {[
                  ['Max Daily Trades', `${risk.limits.max_daily_trades}`],
                  ['Max Daily Loss', `${risk.limits.max_daily_loss_pct}%`],
                  ['Max Exposure', `${risk.limits.max_exposure_pct}%`],
                  ['Min Cash Reserve', `${risk.limits.min_cash_reserve_pct}%`],
                  ['Max Sector Conc.', `${risk.limits.max_sector_concentration_pct}%`],
                  ['Max Corr. Overlap', `${risk.limits.max_correlation_overlap}`],
                  ['Conf. Threshold (S)', `${(risk.limits.confidence_threshold_short * 100).toFixed(0)}%`],
                  ['Conf. Threshold (M/L)', `${(risk.limits.confidence_threshold_mid_long * 100).toFixed(0)}%`],
                  ['Kill Switch', `-${risk.kill_switch_threshold_pct}% drawdown`],
                ].map(([label, val], i) => (
                  <div key={i} className="flex justify-between">
                    <span className="text-slate-500">{label}</span>
                    <span className="text-slate-300">{val}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Check Counters */}
            <div className="card p-4">
              <div className="section-label mb-3">Risk Check Counters</div>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <div className="text-xs text-slate-500 mono mb-1">Today</div>
                  <div className="flex items-end gap-2">
                    <span className="mono text-2xl font-semibold text-emerald-400">{risk.checks_passed_today}</span>
                    <span className="mono text-xs text-slate-500 pb-0.5">passed</span>
                  </div>
                  <div className="flex items-end gap-2 mt-1">
                    <span className="mono text-2xl font-semibold text-red-400">{risk.checks_blocked_today}</span>
                    <span className="mono text-xs text-slate-500 pb-0.5">blocked</span>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 mono mb-1">All-Time</div>
                  <div className="flex items-end gap-2">
                    <span className="mono text-2xl font-semibold text-slate-300">{risk.checks_passed_total}</span>
                    <span className="mono text-xs text-slate-500 pb-0.5">passed</span>
                  </div>
                  <div className="flex items-end gap-2 mt-1">
                    <span className="mono text-2xl font-semibold text-slate-400">{risk.checks_blocked_total}</span>
                    <span className="mono text-xs text-slate-500 pb-0.5">blocked</span>
                  </div>
                </div>
              </div>
              <div className="mono text-xs text-slate-500">
                Block rate: {((risk.checks_blocked_total / (risk.checks_passed_total + risk.checks_blocked_total)) * 100).toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Blocked Trades */}
          <div className="card overflow-hidden">
            <div className="flex items-center gap-3 p-3 border-b border-slate-800/60">
              <span className="section-label">Recent Blocked Trades</span>
              <span className="mono text-xs text-slate-500">Deterministic risk engine rejections</span>
            </div>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Action</th>
                    <th>Ticker</th>
                    <th>Sleeve</th>
                    <th>Block Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {risk.blocked_examples.map((b: any, i: number) => (
                    <tr key={i}>
                      <td className="text-slate-400 whitespace-nowrap">{fmtDate(b.timestamp)} {fmtTime(b.timestamp)}</td>
                      <td><span className="badge badge-red">{b.action}</span></td>
                      <td className="font-semibold text-slate-200">{b.ticker}</td>
                      <td>
                        <span className={`badge ${
                          b.sleeve === 'short_term' ? 'badge-amber' : 'badge-blue'
                        }`}>
                          {b.sleeve.replace('_term', '')}
                        </span>
                      </td>
                      <td className="text-red-300/80 text-xs">{b.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Intelligence / Meta-Model */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
            <div className="card p-4">
              <div className="section-label mb-3">Meta-Model (Claude Trust)</div>
              <div className="space-y-2 mono text-xs">
                {[
                  ['Trust Level', intelligence.meta_model.trust_level.toUpperCase(), 'text-blue-400'],
                  ['Claude Weight', (intelligence.meta_model.claude_weight * 100).toFixed(0) + '%', ''],
                  ['Position Multiplier', intelligence.meta_model.position_multiplier + 'x', ''],
                  ['Predictions Evaluated', intelligence.meta_model.predictions_evaluated, ''],
                  ['Recent Accuracy', intelligence.meta_model.recent_accuracy_pct + '%', pnlColor(intelligence.meta_model.recent_accuracy_pct - 50)],
                  ['Brier Score', intelligence.meta_model.brier_score, ''],
                ].map(([label, val, color], i) => (
                  <div key={i} className="flex justify-between">
                    <span className="text-slate-500">{label}</span>
                    <span className={color || 'text-slate-300'}>{val}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 p-2 bg-surface-2 border border-slate-800/60 text-xs text-slate-400">
                Meta-model dynamically adjusts Claude&apos;s influence based on prediction accuracy.
                Lower accuracy = reduced position sizes + higher reliance on quantitative signals.
              </div>
            </div>

            <div className="card p-4">
              <div className="section-label mb-3">Confidence Calibration</div>
              <div style={{ height: 180 }}>
                <ResponsiveContainer>
                  <ScatterChart margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="predicted"
                      name="Predicted"
                      type="number"
                      domain={[0, 1]}
                      tickFormatter={(v: number) => (v * 100) + '%'}
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      axisLine={false}
                      label={{ value: 'Predicted', position: 'bottom', offset: -2, fill: '#64748b', fontSize: 10 }}
                    />
                    <YAxis
                      dataKey="actual"
                      name="Actual"
                      type="number"
                      domain={[0, 1]}
                      tickFormatter={(v: number) => (v * 100) + '%'}
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      axisLine={false}
                      width={40}
                      label={{ value: 'Actual', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 10 }}
                    />
                    <Tooltip
                      content={({ active, payload }: any) => {
                        if (!active || !payload?.length) return null;
                        const d = payload[0]?.payload;
                        return (
                          <div className="card p-2 mono text-xs border-slate-600">
                            <div className="text-slate-400 mb-1">{d.range} ({d.count} samples)</div>
                            <div>Predicted: <span className="text-blue-400">{(d.predicted * 100).toFixed(0)}%</span></div>
                            <div>Actual: <span className="text-emerald-400">{(d.actual * 100).toFixed(0)}%</span></div>
                          </div>
                        );
                      }}
                    />
                    {/* Perfect calibration line */}
                    <ReferenceLine
                      segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
                      stroke="#334155"
                      strokeDasharray="4 4"
                    />
                    <Scatter
                      data={intelligence.calibration.bins}
                      fill="#3b82f6"
                      stroke="#1d4ed8"
                      strokeWidth={1}
                      r={5}
                    />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <div className="text-xs text-slate-500 text-center mt-1 mono">
                Dots near the diagonal = well-calibrated predictions
              </div>
            </div>
          </div>
        </section>

        {/* ═══ 5. ETF REVIEW ═══ */}
        <section id="etf-review" className="fade-up stagger-5">
          <SectionHeader id="etf-h" label="Quarterly ETF Review" badge={etf_review.approval_status} />

          <div className="card p-4 mb-4">
            <div className="flex flex-wrap items-center gap-4 mb-3">
              <div>
                <div className="section-label mb-1">Last Review</div>
                <div className="mono text-sm text-slate-300">{fmtDate(etf_review.last_review_date)}</div>
              </div>
              <div>
                <div className="section-label mb-1">Next Due</div>
                <div className="mono text-sm text-slate-300">{etf_review.next_review_due}</div>
              </div>
              <div>
                <div className="section-label mb-1">Status</div>
                <span className="badge badge-green">{etf_review.status.replace('_', ' ')}</span>
              </div>
            </div>
            <div className="text-sm text-slate-400 leading-relaxed">
              {etf_review.market_outlook}
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="flex items-center gap-3 p-3 border-b border-slate-800/60">
              <span className="section-label">ETF Recommendations</span>
              <span className="mono text-xs text-slate-500">8 holdings reviewed</span>
            </div>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ETF</th>
                    <th>Action</th>
                    <th className="num">Confidence</th>
                    <th>Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {etf_review.recommendations.map((r: any, i: number) => (
                    <tr key={i}>
                      <td className="font-semibold text-slate-200">{r.ticker}</td>
                      <td>
                        <span className={`badge ${
                          r.action === 'KEEP' ? 'badge-green' :
                          r.action === 'SWAP' ? 'badge-red' :
                          r.action === 'REDUCE' ? 'badge-amber' :
                          'badge-blue'
                        }`}>
                          {r.action}
                        </span>
                      </td>
                      <td className="num">{(r.confidence * 100).toFixed(0)}%</td>
                      <td className="text-slate-400 text-xs max-w-[350px]">{r.reasoning}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ═══ FOOTER ═══ */}
        <footer className="border-t border-slate-800/60 pt-6 pb-10 mt-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-1.5 h-1.5 bg-emerald-400 pulse-dot" />
              <span className="mono text-xs text-slate-500 tracking-wide">
                QUANT AGENT v{meta.version} PUBLIC EDITION
              </span>
            </div>
            <div className="mono text-xs text-slate-600 text-center">
              Simulated data only. No live trading. No real account data exposed.
            </div>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="mono text-xs text-slate-500 hover:text-blue-400 transition-colors"
            >
              GitHub Repository &rarr;
            </a>
          </div>
        </footer>
      </main>
    </div>
  );
}
