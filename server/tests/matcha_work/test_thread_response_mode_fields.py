"""Guard: every ThreadMode column is declared on the thread response models.

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_thread_response_mode_fields.py -q

The serializers spread `**{m.column: ...}` from THREAD_MODES; Pydantic v2's
default extra="ignore" silently drops any column the model doesn't declare.
huume_mode shipped undeclared and the client could never see the mode after
a reload — this test makes that failure loud for the next mode too.
"""

from app.matcha.models.matcha_work.matcha_work import ThreadDetailResponse, ThreadListItem
from app.matcha.services.matcha_work.matcha_work_modes import THREAD_MODES


def test_all_mode_columns_on_list_item():
    missing = [m.column for m in THREAD_MODES if m.column not in ThreadListItem.model_fields]
    assert missing == []


def test_all_mode_columns_on_detail_response():
    missing = [m.column for m in THREAD_MODES if m.column not in ThreadDetailResponse.model_fields]
    assert missing == []


def test_mode_columns_default_false():
    # A row predating a given mode column must deserialize with it off, never error.
    for model in (ThreadListItem, ThreadDetailResponse):
        for m in THREAD_MODES:
            assert model.model_fields[m.column].default is False
