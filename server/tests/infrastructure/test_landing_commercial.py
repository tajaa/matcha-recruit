"""Commercial uploads/publishing use mocked storage and DB collaborators only."""
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.core.models.landing_media import CommercialUploadRequest, SchedulingCommercial
from app.core.services import landing_media as service
from app.core.routes.content import landing_media as routes

URL = 'https://media.example.com/landing/scheduling-commercial/desktop_video/' + 'a' * 32 + '.mp4'


@pytest.fixture
def storage(monkeypatch):
    client = Mock()
    client.generate_presigned_post.return_value = {'url': 'https://bucket.s3.amazonaws.com', 'fields': {'key': 'signed'}}
    client.head_object.return_value = {'ContentLength': 100, 'ContentType': 'video/mp4'}
    fake = SimpleNamespace(s3_client=client, bucket='public-bucket', cloudfront_domain='media.example.com')
    monkeypatch.setattr(service, 'get_storage', lambda: fake)
    return fake


def request(**patch):
    return CommercialUploadRequest(**{'slot': 'desktop_video', 'filename': 'film.mp4', 'content_type': 'video/mp4', 'size': 100, **patch})


def test_signed_post_is_bounded_and_public_bucket_only(storage):
    result = service.prepare_commercial_upload(request())
    call = storage.s3_client.generate_presigned_post.call_args.kwargs
    assert call['Bucket'] == 'public-bucket'
    assert call['Key'].startswith('landing/scheduling-commercial/desktop_video/')
    assert ['content-length-range', 100, 100] in call['Conditions']
    assert {'Content-Type': 'video/mp4'} in call['Conditions']
    assert {'x-amz-server-side-encryption': 'AES256'} in call['Conditions']
    assert call['ExpiresIn'] == 900
    assert result['asset_url'] == 'https://media.example.com/' + call['Key']


@pytest.mark.parametrize('patch', [
    {'filename': 'film.mov'}, {'content_type': 'text/html'},
    {'slot': 'desktop_poster', 'filename': 'poster.png', 'content_type': 'image/png', 'size': 6 * 1024 * 1024},
    {'slot': 'captions', 'filename': 'captions.vtt', 'content_type': 'text/vtt', 'size': 2 * 1024 * 1024},
])
def test_rejected_upload_does_not_sign(storage, patch):
    with pytest.raises(HTTPException): service.prepare_commercial_upload(request(**patch))
    storage.s3_client.generate_presigned_post.assert_not_called()


@pytest.mark.parametrize('size', [0, -1, 151 * 1024 * 1024])
def test_upload_request_size_bounds(size):
    with pytest.raises(ValidationError): request(size=size)


def test_cannot_enable_without_desktop():
    with pytest.raises(ValidationError): SchedulingCommercial(enabled=True)
    assert not SchedulingCommercial().enabled


def test_requires_cdn(storage):
    storage.cloudfront_domain = ''
    with pytest.raises(HTTPException) as error: service.prepare_commercial_upload(request())
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_verified_upload_uses_owned_key(storage):
    await service.verify_commercial_asset('desktop_video', URL, expected_size=100, expected_type='video/mp4')
    storage.s3_client.head_object.assert_called_once_with(Bucket='public-bucket', Key=URL.split('media.example.com/')[1])


@pytest.mark.asyncio
@pytest.mark.parametrize('url', [URL.replace('media.example.com', 'evil.example.com'), URL.replace('desktop_video', 'mobile_video'), URL + '?extra=1', URL.replace('a' * 32, '../secret')])
async def test_rejects_foreign_or_wrong_slot_before_storage(storage, url):
    with pytest.raises(HTTPException): await service.verify_commercial_asset('desktop_video', url)
    storage.s3_client.head_object.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('head', [{'ContentLength': 0, 'ContentType': 'video/mp4'}, {'ContentLength': 100, 'ContentType': 'text/html'}, {'ContentLength': 151 * 1024 * 1024, 'ContentType': 'video/mp4'}])
async def test_invalid_uploaded_object(storage, head):
    storage.s3_client.head_object.return_value = head
    with pytest.raises(HTTPException): await service.verify_commercial_asset('desktop_video', URL)


@pytest.mark.asyncio
async def test_incomplete_upload_never_publishes(storage, monkeypatch):
    storage.s3_client.head_object.return_value = {'ContentLength': 0}
    connection = Mock()
    monkeypatch.setattr(routes, 'get_connection', connection)
    with pytest.raises(HTTPException): await routes.save_scheduling_commercial(SchedulingCommercial(enabled=True, desktop_video_url=URL), current_user=None)
    connection.assert_not_called()


@pytest.mark.asyncio
async def test_settings_patch_preserves_other_landing_fields(storage, monkeypatch):
    statements = []
    class Conn:
        async def execute(self, *args): statements.append(args)
    @asynccontextmanager
    async def connection(): yield Conn()
    monkeypatch.setattr(routes, 'get_connection', connection)
    settings = SchedulingCommercial(enabled=True, desktop_video_url=URL)
    result = await routes.save_scheduling_commercial(settings, current_user=None)
    assert result['value']['desktop_video_url'] == URL
    assert 'platform_settings.value || EXCLUDED.value' in statements[0][0]
    assert json.loads(statements[0][1])['enabled'] is True
    statements.clear()
    await routes.update_landing_media({'hero_video_url': None, 'scheduling_commercial': {'enabled': False}}, current_user=None)
    assert 'scheduling_commercial' not in json.loads(statements[0][1])
    assert 'platform_settings.value || EXCLUDED.value' in statements[0][0]


@pytest.mark.parametrize('method,path,body', [
    ('post','upload', {'slot': 'desktop_video','filename':'film.mp4','content_type':'video/mp4','size':100}),
    ('post','complete', {'slot': 'desktop_video','filename':'film.mp4','content_type':'video/mp4','size':100,'asset_url':URL}),
    ('put','', {'enabled':False}),
])
def test_commercial_mutations_require_admin(method, path, body):
    app = FastAPI()
    app.include_router(routes.admin_router, prefix='/api/admin')
    suffix = '/' + path if path else ''
    response = TestClient(app).request(method, '/api/admin/landing-media/scheduling-commercial' + suffix, json=body)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_disabled_settings_can_be_saved_during_s3_outage(monkeypatch):
    storage = Mock(side_effect=RuntimeError('offline'))
    monkeypatch.setattr(service, 'get_storage', storage)
    await service.verify_commercial_settings(SchedulingCommercial(enabled=False, desktop_video_url=URL))
    storage.assert_not_called()
