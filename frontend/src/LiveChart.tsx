import type { ChartSpec } from "./api";

const TEAL = "#2E6E62";
const GOLD = "#E3A542";
const MUTED = "rgba(245,240,230,0.22)";

const SLICE = [TEAL, GOLD, "#4a8a7c", "#c4923a", MUTED, "#3d7468", "#d4a85a", "#5c9a8e"];

function n(v: number) {
  return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function LiveChart({ chart, height = 180 }: { chart: ChartSpec; height?: number }) {
  const labels = chart.labels || [];
  const values = chart.values || [];
  if (!values.length) return null;
  const hi = chart.highlight_index ?? 0;
  if (chart.type === "pie") return <Pie labels={labels} values={values} highlight={hi} />;
  if (chart.type === "line") return <Line labels={labels} values={values} series={chart.series} height={height} />;
  if (chart.type === "hbar") return <HBar labels={labels} values={values} series={chart.series} highlight={hi} height={height} />;
  return <VBar labels={labels} values={values} series={chart.series} highlight={hi} height={height} />;
}

function VBar({
  labels,
  values,
  series,
  highlight,
  height,
}: {
  labels: string[];
  values: number[];
  series?: { name: string; values: number[] }[];
  highlight: number;
  height: number;
}) {
  const extra = series?.[0]?.values || [];
  const max = Math.max(...values.map(Math.abs), ...extra.map(Math.abs), 1);
  const grouped = extra.length > 0;
  return (
    <div className="flex h-full items-end gap-1.5 px-1" style={{ height }}>
      {values.map((v, i) => (
        <div key={i} className="flex min-w-0 flex-1 flex-col items-center gap-1">
          <div className="flex w-full flex-1 items-end justify-center gap-0.5">
            <div
              className="rounded-t-[3px]"
              style={{
                width: grouped ? "38%" : "70%",
                height: `${Math.max(4, (Math.abs(v) / max) * 100)}%`,
                background: i === highlight ? GOLD : TEAL,
              }}
              title={`${labels[i]}: ${n(v)}`}
            />
            {grouped && extra[i] != null && (
              <div
                className="rounded-t-[3px]"
                style={{
                  width: "38%",
                  height: `${Math.max(4, (Math.abs(extra[i]) / max) * 100)}%`,
                  background: MUTED,
                }}
                title={`${series![0].name}: ${n(extra[i])}`}
              />
            )}
          </div>
          <span className="w-full truncate text-center font-mono text-[10px] text-text-low">{labels[i]}</span>
        </div>
      ))}
    </div>
  );
}

function HBar({
  labels,
  values,
  series,
  highlight,
  height,
}: {
  labels: string[];
  values: number[];
  series?: { name: string; values: number[] }[];
  highlight: number;
  height: number;
}) {
  const extra = series?.[0]?.values || [];
  const max = Math.max(...values.map(Math.abs), ...extra.map(Math.abs), 1);
  const grouped = extra.length > 0;
  return (
    <div className="space-y-2 overflow-auto py-1" style={{ maxHeight: height }}>
      {values.map((v, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-[32%] truncate text-right text-[11px] text-text-low">{labels[i]}</span>
          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="h-2 rounded-sm bg-white/[0.04]">
              <div
                className="h-full rounded-sm"
                style={{
                  width: `${Math.max(2, (Math.abs(v) / max) * 100)}%`,
                  background: i === highlight ? GOLD : TEAL,
                }}
              />
            </div>
            {grouped && extra[i] != null && (
              <div className="h-1.5 rounded-sm bg-white/[0.04]">
                <div
                  className="h-full rounded-sm"
                  style={{
                    width: `${Math.max(2, (Math.abs(extra[i]) / max) * 100)}%`,
                    background: MUTED,
                  }}
                />
              </div>
            )}
          </div>
          <span className="w-[18%] font-mono text-[10px] text-text-mid">{n(v)}</span>
        </div>
      ))}
    </div>
  );
}

function Line({
  labels,
  values,
  series,
  height,
}: {
  labels: string[];
  values: number[];
  series?: { name: string; values: number[] }[];
  height: number;
}) {
  const w = 420;
  const h = Math.max(120, height);
  const pad = { l: 8, r: 8, t: 10, b: 22 };
  const all = [...values, ...(series || []).flatMap((s) => s.values)];
  const lo = Math.min(0, ...all);
  const hi = Math.max(...all, 1);
  const span = hi - lo || 1;
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const x = (i: number, len: number) => pad.l + (len <= 1 ? innerW / 2 : (i / (len - 1)) * innerW);
  const y = (v: number) => pad.t + innerH - ((v - lo) / span) * innerH;
  const lines = [{ name: "", values, color: TEAL }, ...(series || []).map((s, i) => ({ ...s, color: i === 0 ? GOLD : MUTED }))];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-full w-full" role="img">
      {lines.map((ln) => {
        const pts = ln.values.map((v, i) => `${x(i, ln.values.length)},${y(v)}`).join(" ");
        return (
          <g key={ln.name || "main"}>
            <polyline fill="none" stroke={ln.color} strokeWidth="2" points={pts} />
            {ln.values.map((v, i) => (
              <circle key={i} cx={x(i, ln.values.length)} cy={y(v)} r="3" fill={ln.color}>
                <title>{`${labels[i] || ""} ${n(v)}`}</title>
              </circle>
            ))}
          </g>
        );
      })}
      {labels.map((lb, i) => (
        <text
          key={i}
          x={x(i, labels.length)}
          y={h - 6}
          textAnchor="middle"
          fill="#756D5E"
          fontSize="9"
          fontFamily="IBM Plex Mono, monospace"
        >
          {lb.slice(0, 10)}
        </text>
      ))}
      {series && series.length > 0 && (
        <text x={pad.l} y={12} fill="#756D5E" fontSize="9" fontFamily="Inter, sans-serif">
          teal primary · gold {series[0].name}
        </text>
      )}
    </svg>
  );
}

function polar(cx: number, cy: number, r: number, a: number) {
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)] as const;
}

function arc(cx: number, cy: number, r: number, a0: number, a1: number) {
  const [x0, y0] = polar(cx, cy, r, a0);
  const [x1, y1] = polar(cx, cy, r, a1);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`;
}

function Pie({ labels, values, highlight }: { labels: string[]; values: number[]; highlight: number }) {
  const total = values.reduce((s, v) => s + Math.max(0, v), 0) || 1;
  let a = -Math.PI / 2;
  const slices = values.map((v, i) => {
    const sweep = (Math.max(0, v) / total) * Math.PI * 2;
    const d = sweep < 1e-6 ? "" : arc(54, 54, 48, a, a + Math.max(sweep, 1e-6));
    a += sweep;
    return { d, i, v };
  });
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 108 108" className="h-[140px] w-[140px] shrink-0" role="img">
        {slices.map(
          (s) =>
            s.d && (
              <path key={s.i} d={s.d} fill={s.i === highlight ? GOLD : SLICE[s.i % SLICE.length]} opacity={s.i === highlight ? 1 : 0.9}>
                <title>{`${labels[s.i]}: ${n(s.v)}`}</title>
              </path>
            )
        )}
      </svg>
      <ul className="min-w-0 space-y-1 text-[11px] text-text-mid">
        {labels.map((lb, i) => (
          <li key={i} className="flex items-center gap-2">
            <span
              className="h-2 w-2 shrink-0 rounded-sm"
              style={{ background: i === highlight ? GOLD : SLICE[i % SLICE.length] }}
            />
            <span className="truncate">{lb}</span>
            <span className="ml-auto font-mono text-text-low">{n(values[i])}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
