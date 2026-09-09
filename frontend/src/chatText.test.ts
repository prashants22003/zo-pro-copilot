import { describe, expect, it } from "vitest";
import { displayAssistantText, isLeakedToolText, shellClass } from "./chatText";

describe("leaked tool text", () => {
  it("hides execute_sql JSON", () => {
    const text =
      '{"name": "execute_sql", "arguments": {"query": "SELECT SUM(t.transaction_amount) FROM purchasing.supplier_transactions t"}}';
    expect(isLeakedToolText(text)).toBe(true);
    expect(displayAssistantText(text, true)).toBe("");
    expect(displayAssistantText(text, false)).toMatch(/open a card/i);
  });

  it("keeps human language", () => {
    const text = "Line profit for March 2015 was 1.2 million.";
    expect(isLeakedToolText(text)).toBe(false);
    expect(displayAssistantText(text, false)).toBe(text);
  });

  it("uses a river-width shell when the pane is closed", () => {
    expect(shellClass(false)).toContain("max-w-river");
    expect(shellClass(true)).toContain("max-w-[1440px]");
  });
});
