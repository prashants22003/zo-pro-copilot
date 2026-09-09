-- Post-restore helpers for Zo-Pro Copilot

CREATE OR REPLACE FUNCTION warehouse.on_hand_as_of(p_clock date)
RETURNS TABLE(stock_item_id integer, qty_on_hand numeric)
LANGUAGE sql
STABLE
AS $$
    SELECT h.stock_item_id,
           h.quantity_on_hand
           - COALESCE(SUM(t.quantity) FILTER (
                 WHERE t.transaction_occurred_when::date > p_clock
             ), 0) AS qty_on_hand
    FROM warehouse.stock_item_holdings h
    LEFT JOIN warehouse.stock_item_transactions t
      ON t.stock_item_id = h.stock_item_id
    GROUP BY h.stock_item_id, h.quantity_on_hand
$$;

GRANT EXECUTE ON FUNCTION warehouse.on_hand_as_of(date) TO purchase_agent_role, insight_role;
