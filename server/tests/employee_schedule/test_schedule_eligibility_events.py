from app.matcha.services.scheduling.schedule_eligibility_events import (
    SOURCE_KIND,
    eligibility_event_mutation_error,
)


def test_projected_eligibility_events_are_not_manually_mutable():
    assert eligibility_event_mutation_error(SOURCE_KIND, action="resolved")
    assert eligibility_event_mutation_error(SOURCE_KIND, action="assigned")
    assert eligibility_event_mutation_error(None, action="resolved") is None
