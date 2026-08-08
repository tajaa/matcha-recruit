"""Bounds on limit/offset for the list endpoints (item 3): negative or
oversized values must 422 instead of hitting the DB with a bad LIMIT/OFFSET.
"""

import pytest

LIST_ENDPOINTS = [
    "/api/artists",
    "/api/contributors",
    "/api/works",
    "/api/recordings",
    "/api/releases",
]


@pytest.mark.parametrize("path", LIST_ENDPOINTS)
@pytest.mark.parametrize("params", [{"limit": -1}, {"offset": -1}, {"limit": 201}])
def test_list_endpoint_rejects_out_of_bounds_pagination(client, path, params):
    resp = client.get(path, params=params)
    assert resp.status_code == 422


@pytest.mark.parametrize("path", LIST_ENDPOINTS)
def test_list_endpoint_accepts_max_limit(client, path):
    resp = client.get(path, params={"limit": 200, "offset": 0})
    assert resp.status_code == 200
