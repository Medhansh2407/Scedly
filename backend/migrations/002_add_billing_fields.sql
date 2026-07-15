-- 002_add_billing_fields.sql
-- Adds Stripe / trial billing columns to the users table.
--
-- New users get these via the SQLModel defaults at insert time. This migration
-- backfills EXISTING rows so they also receive a 14-day Pro trial from "now",
-- and adds the Stripe linkage columns. Safe to run multiple times.
--
-- Plan model: a 14-day Pro trial that expires to FREE with NO auto-charge.
-- Stripe is only involved when a user actively subscribes.

ALTER TABLE users ADD COLUMN IF NOT EXISTS plan VARCHAR NOT NULL DEFAULT 'trial';
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMP;

-- Backfill trial end for existing users who don't have one yet:
-- give them 14 days from the moment this migration runs.
UPDATE users
SET trial_ends_at = NOW() + INTERVAL '14 days'
WHERE trial_ends_at IS NULL;

-- Indexes for fast lookup from Stripe webhooks (customer / subscription id).
CREATE INDEX IF NOT EXISTS ix_users_stripe_customer_id ON users (stripe_customer_id);
CREATE INDEX IF NOT EXISTS ix_users_stripe_subscription_id ON users (stripe_subscription_id);
