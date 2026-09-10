import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Card, Tab } from "./api";
import { streamChat } from "./api";

const sampleCard: Card = {
  id: "card-1",
  kind: "insight",
  category: "info",
  title: "Line profit",
  text: "Tap to see the rows behind 1,200,000 line profit.",
  metrics: [{ value: "1,200,000", label: "line profit" }],
  display_sources: ["Sales.InvoiceLines"],
  sql_executed: "SELECT SUM(il.line_profit) AS profit FROM sales.invoice_lines il",
  chart: null,
};

const sampleTab: Tab = {
  tab_id: "tab-card-1",
  title: "Line profit",
  breadcrumb: "Sales.InvoiceLines",
  sql_executed: sampleCard.sql_executed,
  columns: [{ key: "profit", label: "profit", kind: "num" }],
  rows: [[1200000]],
  flagged_row_indexes: [0],
  kpis: [{ value: "1,200,000", label: "line profit" }],
  chart: null,
  originId: "card-1",
};

vi.mock("framer-motion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("framer-motion")>();
  return {
    ...actual,
    AnimatePresence: ({ children }: { children: unknown }) => children,
  };
});

vi.mock("./api", () => ({
  getHealth: vi.fn(async () => ({ ok: true, postgres: "ready", seeded: true, demo_clock: "2015-09-14" })),
  getClock: vi.fn(async () => ({
    demo_clock: "2015-09-14",
    data_min: "2013-01-01",
    data_max: "2016-05-31",
  })),
  getAlerts: vi.fn(async () => ({ alerts: [sampleCard], demo_clock: "2015-09-14" })),
  patchClock: vi.fn(),
  streamChat: vi.fn(),
  drilldown: vi.fn(async () => sampleTab),
}));

describe("dashboard pane", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not show the data pane until a card is clicked", async () => {
    render(<App />);
    await screen.findByText(/tap a card/i);
    expect(screen.queryByTestId("data-pane")).toBeNull();
    const shell = screen.getByTestId("chat-shell");
    expect(shell.className).toContain("max-w-river");
  });

  it("opens the pane on card click and closes it with the last tab", async () => {
    const user = userEvent.setup();
    render(<App />);
    const card = await screen.findByRole("button", { name: /line profit/i });
    await user.click(card);
    const pane = await screen.findByTestId("data-pane");
    expect(pane).toBeTruthy();
    expect(screen.getByText(/single total/i)).toBeTruthy();
    await user.click(screen.getByLabelText("Close"));
    await waitFor(() => {
      expect(screen.queryByTestId("data-pane")).toBeNull();
    });
  });
});

describe("chat waiting state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a human status instead of a SQL cue", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.mocked(streamChat).mockImplementation(async (_message, _history, onEvent) => {
      onEvent({ event: "status", data: { text: "I’ll check sales as of the demo clock." } });
      await gate;
      onEvent({ event: "token", data: { text: "March line profit came to 1,200,000." } });
      onEvent({ event: "done", data: { message_id: "m" } });
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText(/tap a card/i);
    await user.type(screen.getByPlaceholderText(/ask about sales/i), "March profit");
    await user.click(screen.getByLabelText("Send"));
    expect(await screen.findByText(/check sales as of the demo clock/i)).toBeTruthy();
    expect(screen.queryByText(/looking at the tables/i)).toBeNull();
    release();
    expect(await screen.findByText(/march line profit came to/i)).toBeTruthy();
    expect(screen.queryByText(/check sales as of the demo clock/i)).toBeNull();
  });
});
