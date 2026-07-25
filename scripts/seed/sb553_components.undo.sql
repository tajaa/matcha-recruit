-- Undo for sb553_components.sql. Catalog data only — no company_id, no
-- tenant-side requirement_compliance_status rows are touched (those are
-- created live by reconcile_component_status the first time a tenant opens
-- the checklist, and clean up on their own once the components disappear).
--
-- Deletes by (jurisdiction, regulation_key, component_key) rather than a
-- pinned id prefix — the pack no longer writes pinned ids (see its own
-- header note on why pinned UUIDs assumed a single CA catalog match).

DELETE FROM requirement_components rc
USING jurisdiction_requirements jr, jurisdictions j
WHERE rc.jurisdiction_requirement_id = jr.id
  AND jr.jurisdiction_id = j.id
  AND j.state = 'CA' AND j.level = 'state' AND COALESCE(j.country_code, 'US') = 'US'
  AND jr.regulation_key = 'workplace_violence_prevention'
  AND rc.component_key IN (
      'written_plan', 'annual_training', 'violent_incident_log',
      'hazard_assessment', 'annual_review'
  );
