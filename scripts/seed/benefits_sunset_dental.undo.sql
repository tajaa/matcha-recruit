-- Undo for benefits_sunset_dental.sql. Child-before-parent: elections
-- reference plan/tier via ON DELETE RESTRICT, so they must go first.
-- Exceptions/renewal-risk/roster have no inbound FK from anything else this
-- pack wrote, so their order relative to each other doesn't matter.

DELETE FROM benefit_elections             WHERE id::text LIKE 'b09e11e5-0005-%';
DELETE FROM life_event_changes            WHERE id::text LIKE 'b09e11e5-0004-%';
DELETE FROM open_enrollment_periods       WHERE id::text LIKE 'b09e11e5-0003-%';
DELETE FROM benefit_plan_tiers            WHERE id::text LIKE 'b09e11e5-0002-%';
DELETE FROM benefit_plans                 WHERE id::text LIKE 'b09e11e5-0001-%';
DELETE FROM benefit_eligibility_exceptions WHERE id::text LIKE 'b09e11e5-0007-%';
DELETE FROM benefit_renewal_risk          WHERE id::text LIKE 'b09e11e5-0008-%';
DELETE FROM benefit_roster_entries        WHERE id::text LIKE 'b09e11e5-0006-%';
