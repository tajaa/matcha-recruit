-- Undo for sb553_components.sql. Catalog data only — no company_id, no
-- tenant-side requirement_compliance_status rows are touched (those are
-- created live by reconcile_component_status the first time a tenant opens
-- the checklist, and clean up on their own once the components disappear).

DELETE FROM requirement_components WHERE id::text LIKE '5b553c00-%';
