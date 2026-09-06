-- Undo for meal_break_timing.sql — removes the meal-period timing rows the
-- pack created. The requirement_key is unique to that pack (nothing else in
-- the catalog writes `meal_breaks:meal_break_timing`), so this deletes exactly
-- what was inserted and never touches the `meal_breaks:meal_break` rows it
-- cloned its scaffolding from.
--
-- If the extraction reviewer has since approved a
-- `meal_break_earliest_after_hours` row off one of these requirements, that
-- approved schedule_rule_extractions row survives this undo (it is keyed on
-- state, not on the requirement) and keeps enforcing — re-run the pack if the
-- catalog row is wanted back.

DELETE FROM jurisdiction_requirements
  WHERE requirement_key = 'meal_breaks:meal_break_timing';
