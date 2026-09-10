BEGIN;

-- OI-1.2 read-path indexes.
-- Idempotent and safe to run repeatedly.

CREATE INDEX IF NOT EXISTS idx_activities_crop_cycle_created_at
    ON public.activities (crop_cycle_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_executions_activity_date
    ON public.activity_executions (activity_id, execution_date DESC);

CREATE INDEX IF NOT EXISTS idx_activity_execution_inputs_execution_created
    ON public.activity_execution_inputs (execution_id, created_at);

CREATE INDEX IF NOT EXISTS idx_activity_purpose_links_activity
    ON public.activity_purpose_links (activity_id);

CREATE INDEX IF NOT EXISTS idx_stock_transactions_external_activity
    ON public.stock_transactions (external_activity_id)
    WHERE external_activity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_crop_cycles_active_crop_name
    ON public.crop_cycles (lower(crop_name_en), planting_date DESC)
    WHERE status='ACTIVE';

COMMIT;
