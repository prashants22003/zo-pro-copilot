export type Metric = { value: string; label: string };
export type ChartSpec = {
  type: string;
  labels: string[];
  values: number[];
  value_label?: string;
  highlight_index?: number;
  series?: { name: string; values: number[] }[];
};
export type Card = {
  id: string;
  kind: "insight" | "chart";
  category: "warning" | "positive" | "info";
  title: string;
  text: string;
  metrics: Metric[];
  display_sources: string[];
  sql_executed: string;
  subject_key?: string | null;
  chart: ChartSpec | null;
};
export type Tab = {
  tab_id: string;
  title: string;
  breadcrumb: string;
  sql_executed: string;
  columns: { key: string; label: string; kind: string }[];
  rows: unknown[][];
  flagged_row_indexes: number[];
  kpis?: { value: string; label: string }[];
  chart?: ChartSpec | null;
  originId: string;
};

export type ChatEvent =
  | { event: "token"; data: { text: string } }
  | { event: "card"; data: Card }
  | { event: "sources"; data: { display_sources: string[] } }
  | { event: "metrics_used"; data: { metrics: string[] } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: { message_id: string } };

function apiUrl(path: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
  if (!base) return `/api${path}`;
  return `${base}${path}`;
}

async function readSSE(
  res: Response,
  onEvent: (ev: ChatEvent) => void
): Promise<void> {
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const block of parts) {
      const lines = block.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent({ event, data: JSON.parse(data) } as ChatEvent);
    }
  }
}

export async function getHealth() {
  const r = await fetch(apiUrl("/health"));
  return r.json() as Promise<{
    ok: boolean;
    postgres: string;
    seeded: boolean;
    demo_clock: string | null;
  }>;
}

export async function getClock() {
  const r = await fetch(apiUrl("/clock"));
  return r.json() as Promise<{
    demo_clock: string;
    data_min: string;
    data_max: string;
  }>;
}

export async function patchClock(demo_clock: string) {
  const r = await fetch(apiUrl("/clock"), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ demo_clock }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getAlerts() {
  const r = await fetch(apiUrl("/alerts"));
  return r.json() as Promise<{ alerts: Card[]; demo_clock: string }>;
}

export async function streamChat(
  message: string,
  history: { role: string; content: string }[],
  onEvent: (ev: ChatEvent) => void
) {
  const r = await fetch(apiUrl("/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!r.ok) throw new Error("Chat request failed");
  await readSSE(r, onEvent);
}

export async function drilldown(card: Card): Promise<Tab> {
  const r = await fetch(apiUrl("/drilldown"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sql_executed: card.sql_executed,
      title: card.title,
      origin_card_id: card.id,
      subject_key: card.subject_key || undefined,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  const data = (await r.json()) as Tab;
  data.originId = card.id;
  return data;
}
