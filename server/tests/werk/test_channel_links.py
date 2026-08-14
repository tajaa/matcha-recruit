from uuid import uuid4

from app.werk.services.channel_links import _append_suffix


def test_suffix_appends_with_ampersand_when_base_has_query():
    channel_id = uuid4()
    assert _append_suffix(
        f"/work/projects/{channel_id}?tab=chat", "?tipped=1"
    ) == f"/work/projects/{channel_id}?tab=chat&tipped=1"


def test_suffix_appends_path_without_corrupting_base():
    channel_id = uuid4()
    assert _append_suffix(
        f"/ops/channels/{channel_id}", "/job-postings/123"
    ) == f"/ops/channels/{channel_id}/job-postings/123"
