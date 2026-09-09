-- Applied after data load. Local demo passwords only.

CREATE SCHEMA IF NOT EXISTS copilot;

CREATE TABLE IF NOT EXISTS copilot.settings (
    key text PRIMARY KEY,
    value text NOT NULL
);

INSERT INTO copilot.settings (key, value)
VALUES ('demo_clock', '2015-09-14')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS copilot.alerts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id text NOT NULL,
    category text NOT NULL CHECK (category IN ('warning', 'positive')),
    text text NOT NULL,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_tables text[] NOT NULL DEFAULT '{}',
    display_sources text[] NOT NULL DEFAULT '{}',
    sql_executed text NOT NULL DEFAULT '',
    subject_key text NOT NULL DEFAULT '',
    as_of date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS alerts_as_of_unresolved_idx
    ON copilot.alerts (as_of)
    WHERE NOT resolved;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sales_agent_role') THEN
        CREATE ROLE sales_agent_role LOGIN PASSWORD 'sales_agent_local';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'purchase_agent_role') THEN
        CREATE ROLE purchase_agent_role LOGIN PASSWORD 'purchase_agent_local';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'insight_role') THEN
        CREATE ROLE insight_role LOGIN PASSWORD 'insight_agent_local';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA sales, warehouse, application TO sales_agent_role;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO sales_agent_role;
GRANT SELECT ON warehouse.stock_items TO sales_agent_role;
GRANT SELECT ON application.cities, application.state_provinces, application.countries, application.people TO sales_agent_role;
GRANT SELECT ON application.delivery_methods, application.payment_methods TO sales_agent_role;

GRANT USAGE ON SCHEMA purchasing, warehouse, application TO purchase_agent_role;
GRANT SELECT ON ALL TABLES IN SCHEMA purchasing TO purchase_agent_role;
GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO purchase_agent_role;
GRANT SELECT ON application.cities, application.state_provinces, application.countries, application.people TO purchase_agent_role;
GRANT SELECT ON application.delivery_methods, application.payment_methods, application.transaction_types TO purchase_agent_role;

GRANT USAGE ON SCHEMA sales, purchasing, warehouse, application, copilot TO insight_role;
GRANT SELECT ON ALL TABLES IN SCHEMA sales, purchasing, warehouse, application TO insight_role;
GRANT SELECT, INSERT, UPDATE ON copilot.alerts TO insight_role;
GRANT SELECT, UPDATE ON copilot.settings TO insight_role;

ALTER ROLE sales_agent_role SET statement_timeout = '5s';
ALTER ROLE purchase_agent_role SET statement_timeout = '5s';
ALTER ROLE insight_role SET statement_timeout = '15s';
