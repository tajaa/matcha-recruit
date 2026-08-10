from app.tellus.services.comms_service import next_status


def test_consumer_message_waits_for_business():
    assert next_status("consumer") == "waiting_brand"


def test_business_message_waits_for_consumer():
    assert next_status("brand") == "waiting_consumer"
