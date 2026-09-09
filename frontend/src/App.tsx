import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  IconAlertTriangle,
  IconArrowsDiagonal,
  IconArrowUp,
  IconCode,
  IconDatabase,
  IconSparkles,
  IconTrendingUp,
  IconX,
} from "@tabler/icons-react";
import {
  Card,
  Tab,
  drilldown,
  getAlerts,
  getClock,
  getHealth,
  patchClock,
  streamChat,
} from "./api";
import { LiveChart } from "./LiveChart";
import { chatColumnClass, displayAssistantText, shellClass } from "./chatText";

type Msg = {
  id: string;
  role: "user" | "assistant";
  text: string;
  cards: Card[];
  sources?: string[];
  metrics?: string[];
};

const ease = [0.22, 0.8, 0.28, 1] as const;

function fmt(v: unknown) {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toLocaleString();
  return String(v);
}

export default function App() {
  const [health, setHealth] = useState("connecting");
  const [clock, setClock] = useState("2015-09-14");
  const [range, setRange] = useState({ min: "2013-01-01", max: "2016-05-31" });
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [sqlOpen, setSqlOpen] = useState(false);
  const [originId, setOriginId] = useState<string | null>(null);
  const split = tabs.length > 0;
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const h = await getHealth();
        setHealth(h.seeded ? "connected" : "empty");
        const c = await getClock();
        setClock(c.demo_clock);
        setRange({ min: c.data_min, max: c.data_max });
        const a = await getAlerts();
        const intro =
          a.alerts.length > 0
            ? "I found a few things worth a look — tap a card to see the underlying rows."
            : "Nothing needs your attention right now. Ask me about sales or purchasing.";
        setMsgs([
          {
            id: "hello",
            role: "assistant",
            text: intro,
            cards: a.alerts,
          },
        ]);
      } catch {
        setHealth("offline");
      }
    })();
  }, []);

  useEffect(() => {
    const el = scroller.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [msgs, busy]);

  const chips = useMemo(() => {
    const last = [...msgs].reverse().find((m) => m.role === "assistant");
    if (!last) return [];
    if (last.cards.some((c) => c.category === "warning")) {
      return ["Why is that happening?", "Show overdue purchase orders", "How did last quarter look?"];
    }
    return ["How did we perform last quarter?", "Which region grew?", "Any overdue purchase orders?"];
  }, [msgs]);

  async function onClock(next: string) {
    setClock(next);
    try {
      await patchClock(next);
      const a = await getAlerts();
      setMsgs((m) => [
        ...m,
        {
          id: `clock-${next}`,
          role: "assistant",
          text: `Clock set to ${next}. Insights below are as of that date.`,
          cards: a.alerts,
        },
      ]);
    } catch (e) {
      setMsgs((m) => [
        ...m,
        {
          id: `clock-err-${Date.now()}`,
          role: "assistant",
          text: e instanceof Error ? e.message : "Could not change the clock.",
          cards: [],
        },
      ]);
    }
  }

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setDraft("");
    const history = msgs
      .map((m) => ({
        role: m.role,
        content: m.role === "assistant" ? displayAssistantText(m.text, m.cards.length > 0) : m.text,
      }))
      .filter((h) => h.content.trim().length > 0);
    const user: Msg = { id: `u-${Date.now()}`, role: "user", text: q, cards: [] };
    const asst: Msg = { id: `a-${Date.now()}`, role: "assistant", text: "", cards: [] };
    setMsgs((m) => [...m, user, asst]);
    setBusy(true);
    try {
      await streamChat(q, history, (ev) => {
        setMsgs((all) => {
          const copy = [...all];
          const last = copy[copy.length - 1];
          if (!last || last.role !== "assistant") return all;
          if (ev.event === "token") last.text += ev.data.text;
          if (ev.event === "card") last.cards = [...last.cards, ev.data];
          if (ev.event === "sources") last.sources = ev.data.display_sources;
          if (ev.event === "metrics_used") last.metrics = ev.data.metrics;
          if (ev.event === "error") last.text = ev.data.message;
          return copy;
        });
      });
    } catch {
      setMsgs((all) => {
        const copy = [...all];
        const last = copy[copy.length - 1];
        if (last) last.text = "The copilot could not reach the API. Check that the stack is running.";
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  async function openCard(card: Card) {
    if (!card.sql_executed) {
      setMsgs((m) => [
        ...m,
        {
          id: `drill-${Date.now()}`,
          role: "assistant",
          text: "That card has no query behind it, so I cannot open a dashboard.",
          cards: [],
        },
      ]);
      return;
    }
    try {
      const tab = await drilldown(card);
      setTabs((prev) => {
        const rest = prev.filter((t) => t.originId !== card.id);
        return [...rest, tab];
      });
      setActiveTab(tab.tab_id);
      setOriginId(card.id);
      setSqlOpen(false);
    } catch (e) {
      setMsgs((m) => [
        ...m,
        {
          id: `drill-${Date.now()}`,
          role: "assistant",
          text: e instanceof Error ? e.message : "Could not open those rows.",
          cards: [],
        },
      ]);
    }
  }

  function closeTab(id: string) {
    setTabs((prev) => {
      const next = prev.filter((t) => t.tab_id !== id);
      setActiveTab(next.at(-1)?.tab_id ?? null);
      if (next.length === 0) setOriginId(null);
      return next;
    });
  }

  const tab = tabs.find((t) => t.tab_id === activeTab) ?? tabs.at(-1);

  return (
    <div className="relative min-h-screen">
      <div className="ambient pointer-events-none absolute inset-x-0 top-0 h-40 overflow-hidden">
        <svg viewBox="0 0 800 180" preserveAspectRatio="none" className="h-full w-[140%] opacity-30">
          <path className="ambient-path" stroke="#E3A542" d="M0,60 C150,20 250,100 400,60 C550,20 650,100 800,60" />
          <path className="ambient-path p2" stroke="#2E6E62" d="M0,110 C150,150 250,80 400,110 C550,150 650,80 800,110" />
        </svg>
      </div>

      <div
        data-testid="chat-shell"
        className={`relative mx-auto flex min-h-screen gap-4 px-6 pb-8 pt-6 ${shellClass(split)}`}
      >
        <motion.section
          layout
          transition={{ duration: 0.55, ease }}
          className={`flex min-h-[calc(100vh-3rem)] flex-col ${chatColumnClass(split)}`}
        >
          <header className="relative z-10 mb-6 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-gold to-teal font-voice text-sm font-semibold text-ink">
                Z
              </div>
              <span className="text-sm text-text-mid">Zo-Pro Copilot</span>
            </div>
            <div className="flex items-center gap-3 text-xs text-text-low">
              <label className="flex items-center gap-2">
                As of
                <input
                  type="date"
                  value={clock}
                  min={range.min}
                  max={range.max}
                  onChange={(e) => onClock(e.target.value)}
                  className="rounded-md border border-white/10 bg-ink-1 px-2 py-1 font-mono text-[11px] text-text-mid outline-none focus:border-gold/40"
                />
              </label>
              <span className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-gold shadow-[0_0_0_3px_rgba(227,165,66,0.14)]" />
                {health === "connected" ? "WWI · sales + purchasing" : health}
              </span>
            </div>
          </header>

          <div ref={scroller} className="flex-1 space-y-[22px] overflow-y-auto pr-1">
            {msgs.map((m) => (
              <div key={m.id}>
                <div className={`flex gap-3 ${m.role === "user" ? "ml-auto max-w-[70%] flex-row-reverse" : "max-w-[86%]"}`}>
                  <div
                    className={`flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full border text-[13px] ${
                      m.role === "user"
                        ? "border-gold/30 bg-[rgba(227,165,66,0.14)] text-gold"
                        : "border-white/[0.08] bg-ink-2 text-text-mid"
                    }`}
                  >
                    {m.role === "user" ? "Y" : <IconSparkles size={15} />}
                  </div>
                  <div className="pt-0.5">
                    {m.role === "assistant" && <p className="mb-1 text-[11px] text-text-low">Copilot</p>}
                    {m.role === "assistant" ? (
                      displayAssistantText(m.text, m.cards.length > 0) ? (
                        <p className="font-voice text-base leading-relaxed text-text-hi">
                          {displayAssistantText(m.text, m.cards.length > 0)}
                        </p>
                      ) : null
                    ) : (
                      <p className="rounded-[14px_14px_4px_14px] border border-white/[0.08] bg-ink-1 px-3.5 py-2.5 text-[14.5px] text-text-mid">
                        {m.text}
                      </p>
                    )}
                    {m.metrics && m.metrics.length > 0 && (
                      <p className="mt-2 font-mono text-[11px] text-text-low">Using {m.metrics.join(", ")}</p>
                    )}
                    {m.sources && m.sources.length > 0 && (
                      <p className="mt-1 flex items-center gap-1 text-[11px] text-text-low">
                        <IconDatabase size={12} /> {m.sources.join(" · ")}
                      </p>
                    )}
                  </div>
                </div>
                {m.cards.map((card) => (
                  <div key={card.id} className="mt-3 pl-[42px]">
                    {card.kind === "chart" && card.chart ? (
                      <ChartCard card={card} active={originId === card.id} onOpen={() => openCard(card)} />
                    ) : (
                      <InsightCard card={card} active={originId === card.id} onOpen={() => openCard(card)} />
                    )}
                  </div>
                ))}
              </div>
            ))}
            {busy && <p className="pl-[42px] font-voice text-sm text-text-low">Looking at the tables…</p>}
          </div>

          <div className="mt-6">
            <form
              className="flex items-center gap-2.5 rounded-2xl border border-white/10 bg-ink-1 px-[18px] py-3"
              onSubmit={(e) => {
                e.preventDefault();
                send(draft);
              }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Ask about sales, purchasing, or a specific supplier or product…"
                className="flex-1 bg-transparent text-sm text-text-hi outline-none placeholder:text-text-low"
              />
              <button
                type="submit"
                className="flex h-8 w-8 items-center justify-center rounded-[9px] border border-gold/30 bg-[rgba(227,165,66,0.14)] text-gold"
                aria-label="Send"
              >
                <IconArrowUp size={15} />
              </button>
            </form>
            <div className="mt-2.5 flex flex-wrap gap-2">
              {chips.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => send(c)}
                  className="rounded-full border border-white/[0.08] px-2.5 py-1 text-[11.5px] text-text-low hover:border-white/20"
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        </motion.section>

        <AnimatePresence>
          {split && tab && (
            <motion.aside
              key="pane"
              data-testid="data-pane"
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 16 }}
              transition={{ duration: 0.5, ease }}
              className="mt-[52px] mb-2 flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-white/10 bg-ink-1"
            >
              <div className="flex gap-1 border-b border-white/[0.08] px-3 pt-3">
                {tabs.map((t) => (
                  <button
                    key={t.tab_id}
                    onClick={() => setActiveTab(t.tab_id)}
                    className={`rounded-t-lg px-3 py-2 text-[11.5px] ${
                      t.tab_id === tab.tab_id ? "bg-ink-2 text-text-hi" : "text-text-low"
                    }`}
                  >
                    {t.title}
                    <span
                      className="ml-2 text-text-low"
                      onClick={(e) => {
                        e.stopPropagation();
                        closeTab(t.tab_id);
                      }}
                    >
                      ×
                    </span>
                  </button>
                ))}
              </div>
              <motion.div
                className="border-b border-white/[0.08] px-[22px] py-4"
                layoutId={originId ? `extract-${originId}` : undefined}
              >
                <p className="mb-1.5 text-[11.5px] text-text-low">{tab.breadcrumb}</p>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-voice text-[19px] font-medium">{tab.title}</h3>
                  <button
                    className="flex h-[30px] w-[30px] items-center justify-center rounded-lg border border-white/[0.08] text-text-mid"
                    onClick={() => closeTab(tab.tab_id)}
                    aria-label="Close"
                  >
                    <IconX size={15} />
                  </button>
                </div>
                <button
                  className="mt-3 inline-flex items-center gap-1 text-xs text-[#589e90]"
                  onClick={() => setSqlOpen((v) => !v)}
                >
                  <IconCode size={14} /> View SQL
                </button>
                {sqlOpen && (
                  <pre className="mt-2.5 overflow-x-auto rounded-lg border border-white/[0.08] bg-ink p-3 font-mono text-xs leading-relaxed text-text-mid">
                    {tab.sql_executed}
                  </pre>
                )}
                {tab.kpis && tab.kpis.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-6">
                    {tab.kpis.map((k, i) => (
                      <div key={`${k.label}-${i}`}>
                        <span className="block font-mono text-[22px] text-text-hi">{k.value}</span>
                        <span className="text-[11px] text-text-low">{k.label}</span>
                      </div>
                    ))}
                  </div>
                )}
              </motion.div>
              <div className="border-b border-white/[0.08] px-[22px] py-4">
                {tab.chart ? (
                  <>
                    <p className="mb-2 text-[11px] text-text-low">
                      {[tab.chart.value_label, tab.chart.series?.[0]?.name].filter(Boolean).join(" vs ")} · from this query
                    </p>
                    <LiveChart chart={tab.chart} height={200} />
                  </>
                ) : (
                  <p className="text-[13px] text-text-low">Single total — no series to plot</p>
                )}
              </div>
              <div className="min-h-0 flex-1 overflow-auto px-[22px] py-2">
                <table className="w-full border-collapse text-[13px]">
                  <thead>
                    <tr>
                      {tab.columns.map((c) => (
                        <th
                          key={c.key}
                          className={`sticky top-0 bg-ink-1 px-2 py-2.5 text-[11px] font-medium text-text-low ${
                            c.kind === "num" ? "text-right" : "text-left"
                          }`}
                        >
                          {c.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tab.rows.map((row, i) => (
                      <tr key={i} className="hover:bg-ink-2">
                        {row.map((cell, j) => (
                          <td
                            key={j}
                            className={`relative border-b border-white/[0.08] px-2 py-2.5 ${
                              tab.columns[j]?.kind === "num"
                                ? "text-right font-mono text-text-hi"
                                : "text-text-mid"
                            }`}
                          >
                            {tab.flagged_row_indexes.includes(i) && j === 0 && (
                              <span className="absolute bottom-0 left-0 top-0 w-0.5 bg-ember" />
                            )}
                            {fmt(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function InsightCard({
  card,
  active,
  onOpen,
}: {
  card: Card;
  active: boolean;
  onOpen: () => void;
}) {
  const warning = card.category === "warning";
  const positive = card.category === "positive";
  const accent = warning ? "ember" : positive ? "gold" : "teal";
  return (
    <motion.button
      layoutId={`extract-${card.id}`}
      type="button"
      onClick={onOpen}
      className={`w-full max-w-[480px] rounded-[4px_12px_12px_4px] border bg-ink-1 px-4 py-3.5 text-left transition-colors hover:bg-ink-2 ${
        active ? "border-white/20" : "border-white/[0.08]"
      }`}
      style={{ borderLeftWidth: 2, borderLeftColor: warning ? "#C1502E" : positive ? "#E3A542" : "#2E6E62" }}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className={`flex items-center gap-2 text-[11.5px] font-medium text-${accent}`}>
          {warning ? (
            <IconAlertTriangle size={15} className="text-ember" />
          ) : (
            <IconTrendingUp size={15} className={positive ? "text-gold" : "text-teal"} />
          )}
          <span className={warning ? "text-ember" : positive ? "text-gold" : "text-text-low"}>{card.title}</span>
        </span>
        <IconArrowsDiagonal size={14} className="text-text-low" />
      </div>
      <p className="text-[13.5px] leading-relaxed text-text-mid">{card.text}</p>
      {card.metrics.length > 0 && (
        <div className="mt-2.5 flex gap-4">
          {card.metrics.map((m) => (
            <div key={m.label}>
              <span className="block font-mono text-[21px] text-text-hi">{m.value}</span>
              <span className="text-[11px] text-text-low">{m.label}</span>
            </div>
          ))}
        </div>
      )}
      {card.display_sources.length > 0 && (
        <p className="mt-2.5 flex items-center gap-1.5 border-t border-white/[0.08] pt-2 text-[11px] text-text-low">
          <IconDatabase size={12} /> {card.display_sources.join(" · ")}
        </p>
      )}
    </motion.button>
  );
}

function ChartCard({
  card,
  active,
  onOpen,
}: {
  card: Card;
  active: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`w-full max-w-[480px] rounded-xl border bg-ink-1 px-[18px] pb-3 pt-4 text-left hover:bg-ink-2 ${
        active ? "border-white/20" : "border-white/[0.08]"
      }`}
    >
      <div className="mb-2.5 flex items-center justify-between text-xs text-text-low">
        <span>{card.title}</span>
        <IconArrowsDiagonal size={14} />
      </div>
      {card.metrics.length > 0 && (
        <div className="mb-3 flex gap-4">
          {card.metrics.slice(0, 3).map((m) => (
            <div key={m.label}>
              <span className="block font-mono text-[18px] text-text-hi">{m.value}</span>
              <span className="text-[11px] text-text-low">{m.label}</span>
            </div>
          ))}
        </div>
      )}
      <LiveChart chart={card.chart!} height={132} />
    </button>
  );
}
