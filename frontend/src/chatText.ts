const TOOL_NAME =
  /"name"\s*:\s*"(execute_sql|sales_agent|purchase_agent|get_live_alerts|cross_domain_query)"/;

export function isLeakedToolText(text: string): boolean {
  const t = (text || "").trim();
  if (!t) return false;
  if (TOOL_NAME.test(t)) return true;
  if (/^\s*```/.test(t) && /select[\s\S]+from/i.test(t)) return true;
  if (/^\s*select\s+/i.test(t) && /\bfrom\b/i.test(t)) return true;
  return false;
}

export function displayAssistantText(text: string, hasCards: boolean): string {
  if (!isLeakedToolText(text)) return text;
  if (hasCards) return "";
  return "I looked that up — open a card for the numbers.";
}

export function shellClass(split: boolean): string {
  return split ? "max-w-[1440px]" : "max-w-river justify-center";
}

export function chatColumnClass(split: boolean): string {
  return split ? "w-[min(480px,38%)] shrink-0" : "w-full";
}
