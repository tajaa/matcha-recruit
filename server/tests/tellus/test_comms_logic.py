from datetime import datetime, timezone
from uuid import uuid4

from app.tellus.services.comms_service import next_status, thread_to_model


def test_consumer_message_waits_for_business():
    assert next_status("consumer") == "waiting_brand"


def test_business_message_waits_for_consumer():
    assert next_status("brand") == "waiting_consumer"


def test_consumer_view_redacts_inbox_assignment():
    row = {
        "id": uuid4(), "report_id": None, "brand_name": "Shop", "consumer_display_name": "Alex",
        "last_message_at": datetime.now(timezone.utc), "created_at": datetime.now(timezone.utc),
        "assigned_member_id": uuid4(), "assigned_member_name": "Staff", "kind": "general",
        "status": "waiting_brand", "blocked_at": None,
    }
    view = thread_to_model(row, "consumer")
    assert view.assigned_member_id is None
    assert view.assigned_member_name is None


def test_brand_view_materializes_assignment():
    member_id = uuid4()
    row = {
        "id": uuid4(), "report_id": None, "brand_name": "Shop", "consumer_display_name": "Alex",
        "last_message_at": datetime.now(timezone.utc), "created_at": datetime.now(timezone.utc),
        "assigned_member_id": member_id, "assigned_member_name": "Staff", "kind": "general",
        "status": "waiting_brand", "blocked_at": None,
    }
    view = thread_to_model(row, "brand")
    assert view.assigned_member_id == member_id
    assert view.assigned_member_name == "Staff"
