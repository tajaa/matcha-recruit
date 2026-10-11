"""Claude cache/turn contracts. All providers, downloads and persistence are fakes."""
import asyncio
import copy
import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import anthropic
import httpx2
import pytest
from cachetools import LRUCache

from app.config import load_settings
from app.core.services.ai_usage import compute_cost
from app.core.services.anthropic_messages import CLAUDE_HAIKU, CLAUDE_SONNET
from app.matcha.services.billing.model_pricing import claude_turn_cost
from app.matcha.services.matcha_work import turn_pipeline as pipeline
from app.matcha.services.matcha_work.ai_apply import _inject_slide_context
from app.matcha.services.matcha_work.matcha_work_ai import _claude, _images, _claude_thread as layout, provider
from app.matcha.services.matcha_work.matcha_work_ai._stream import ReplyStreamExtractor, partial_reply
from tests.matcha_work.test_skill_engine_claude import _message, _request, _image


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    load_settings()
    monkeypatch.setattr(_claude, '_NO_SYSTEM_ROLE', set())
    monkeypatch.setattr(_claude, '_NO_SCHEMA', set())
    monkeypatch.setattr(_claude, 'record_anthropic_response', AsyncMock())
    monkeypatch.setattr(_claude, 'record_claude_call', AsyncMock())
    monkeypatch.setattr(_claude, 'get_rate_limiter', lambda *_: SimpleNamespace(check_limit=AsyncMock()))
    _images._image_cache.clear()


def strip_cache(value):
    if isinstance(value, dict):
        return {k: strip_cache(v) for k, v in value.items() if k != 'cache_control'}
    if isinstance(value, list):
        return [strip_cache(v) for v in value]
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['plain', 'compliance', 'files', 'images', 'slide', 'blog', 'hr'])
async def test_next_turn_reuses_exact_prefix_across_date_and_state_changes(monkeypatch, scenario):
    engine = provider.GeminiProvider.__new__(provider.GeminiProvider)
    messages = [{'role': 'user', 'content': 'Please improve this'}]
    if scenario == 'files':
        messages[0]['files'] = [('notes.txt', 'Keep café open until 5 🫖')]
    if scenario == 'images':
        messages[0]['image_parts'] = [(_image('PNG'), 'image/png')]
    state = {'slides': [{'title': 'Before', 'bullets': ['Original']}]} if scenario == 'slide' else {}
    if scenario == 'slide':
        _inject_slide_context(messages, state, 0)
    kwargs = dict(current_state=state, company_context='Company', stable_context='Grounding' if scenario == 'compliance' else '',
                  turn_context='RAG turn 1', context_summary='Earlier summary', slide_index=0 if scenario == 'slide' else None,
                  blog_mode_state='Blog state' if scenario == 'blog' else None, hr_pilot_mode=scenario == 'hr',
                  history_from=0, valid_fields=['slides'], skill='presentation' if scenario == 'slide' else 'chat')
    monkeypatch.setattr(provider, 'date', SimpleNamespace(today=lambda: date(2026, 10, 10)))
    before = await engine._claude_thread_request(messages=messages, **kwargs)
    messages = copy.deepcopy(messages)
    messages += [{'role': 'assistant', 'content': 'Done'}, {'role': 'user', 'content': 'Thanks'}]
    monkeypatch.setattr(provider, 'date', SimpleNamespace(today=lambda: date(2026, 10, 11)))
    after = await engine._claude_thread_request(messages=messages, **{**kwargs, 'current_state': {'new': 'state'}, 'turn_context': 'RAG turn 2'})
    assert before.system(structured=True) == after.system(structured=True)
    assert strip_cache(before.history) == strip_cache(after.history[:len(before.history)])
    assert before.turn_context != after.turn_context
    assert '2026-10-10' not in json.dumps(before.system(structured=True))
    for request in (before, after):
        params = _claude.request_params(request, model=CLAUDE_HAIKU, effort='medium', system_role=True, structured=True)
        controls = []
        def visit(value):
            if isinstance(value, dict):
                if 'cache_control' in value:
                    controls.append(value['cache_control'])
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(params)
        assert 1 <= len(controls) <= 4
        assert all(c == layout.CACHE_CONTROL for c in controls)
        assert params['messages'][-1]['role'] == 'system'
    if scenario == 'slide':
        assert 'EDITING Slide' not in json.dumps(before.history)
        assert 'EDITING Slide' in before.turn_context


@pytest.mark.parametrize('count,summary,start', [(0,None,0),(40,None,0),(60,None,0),(61,None,20),(79,None,20),(80,None,40),
                                                (31,30,15),(49,30,15),(71,50,35),(100,30,60)])
def test_history_window(count, summary, start):
    assert layout.claude_history_start(count, summary) == start


@pytest.mark.parametrize('skill,grounded,expected', [('chat',False,'medium'),('chat',True,'high'),('presentation',False,'high')])
def test_effort_depends_on_thread_shape(skill, grounded, expected):
    assert layout.thread_effort(current_skill=skill, grounded=grounded) == expected


@pytest.mark.parametrize('encoded,expected', [('{}',{}), ('{"slides":[]}', {'slides':[]}), ('oops',{}), ('[]',{}), ('',{}), (None,{})])
def test_updates_json_roundtrip(encoded, expected):
    parsed = json.loads(layout.engine_reply_text(json.dumps({'reply':'Hello', 'updates_json':encoded})))
    assert parsed == {'reply':'Hello','updates':expected}


@pytest.mark.parametrize('raw', ['not json', '[]', '{"reply":"Hi"}'])
def test_non_schema_reply_passes_through(raw):
    assert layout.engine_reply_text(raw) == raw


class Client:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))
    def with_options(self, **kwargs):
        return self
    async def create(self, **params):
        self.calls.append(copy.deepcopy(params))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def bad_request(message):
    return anthropic.BadRequestError(message, response=httpx2.Response(400, request=httpx2.Request('POST','https://api.anthropic.com/v1/messages')), body={'error': message})


@pytest.mark.asyncio
@pytest.mark.parametrize('feature', ['system', 'schema', 'both'])
async def test_feature_rejection_retries_and_is_memoized(monkeypatch, feature):
    errors = ([bad_request("role 'system' is not supported")] if feature in ('system','both') else [])
    errors += ([bad_request('output_config schema rejected')] if feature in ('schema','both') else [])
    client = Client([*errors, _message('{"reply":"Ready"}'), _message('{"reply":"Again"}')])
    monkeypatch.setattr(_claude, 'get_async_client', lambda: client)
    request = _request()
    pristine = copy.deepcopy(request)
    for _ in range(2):
        await _claude.call_claude_thread(request, model=CLAUDE_HAIKU, effort='medium', timeout_seconds=3)
    assert len(client.calls) == len(errors)+2
    assert request == pristine
    last = client.calls[-1]
    if feature in ('system','both'):
        assert last['messages'][-1]['role'] == 'user'
        blocks = last['messages'][-1]['content']
        assert 'cache_control' in blocks[-2] and 'cache_control' not in blocks[-1]
        assert blocks[-1]['text'].startswith('<turn_context>')
    if feature in ('schema','both'):
        assert 'format' not in last['output_config']
        assert 'exactly one JSON object' in last['system'][0]['text']


@pytest.mark.asyncio
async def test_unrelated_bad_request_is_not_retried(monkeypatch):
    client = Client([bad_request('invalid image')])
    monkeypatch.setattr(_claude, 'get_async_client', lambda: client)
    with pytest.raises(_claude.ClaudeCallFailed):
        await _claude.call_claude_thread(_request(), model=CLAUDE_HAIKU, effort='medium', timeout_seconds=3)
    assert len(client.calls) == 1


def test_refusal_and_cutoff_are_visible():
    assert json.loads(_claude.reply_text('',stop_reason='refusal',structured=True))['reply'] == _claude.REFUSAL_REPLY
    raw = '{"mode":"general","reply":"Partial \\u00e9'
    assert json.loads(_claude.reply_text(raw, stop_reason='max_tokens', structured=True))['reply'] == 'Partial é' + _claude.CUT_OFF_NOTE


@pytest.mark.parametrize('step', [1,2,3,7,1000])
def test_reply_extractor_chunk_boundaries(step):
    reply = 'café 🫖\n"quotes" \\ slash /\tend'
    raw = json.dumps({'nested':{'reply':'ignore'},'updates_json':'{"reply":"also ignore"}','reply':reply})
    extractor = ReplyStreamExtractor()
    result = ''.join(extractor.feed(raw[i:i+step]) for i in range(0,len(raw),step))
    assert result == reply == extractor.reply
    assert extractor.done
    assert extractor.feed('more') == ''
    assert partial_reply('{"reply":"unfinished') == 'unfinished'
    assert partial_reply('{"mode":"general"') is None


@pytest.mark.parametrize('model', [CLAUDE_HAIKU, CLAUDE_SONNET])
@pytest.mark.parametrize('tokens', [100_000,100_001])
def test_usage_and_cost_agree_with_ledger(model, tokens):
    message = _message('{}', usage={'input_tokens':tokens-3000,'output_tokens':1000,'cache_read_input_tokens':1000,
                                   'cache_creation_input_tokens':2000,'cache_creation':{'ephemeral_5m_input_tokens':500,'ephemeral_1h_input_tokens':1500}})
    usage = _claude._usage(message, model)
    assert usage['prompt_tokens'] == tokens-1000
    assert usage['total_tokens'] == tokens
    assert usage['cache_write_1h_tokens'] == 1500
    expected = compute_cost('anthropic', model, tokens, 1000, None, 1000, 2000, 1500)
    assert usage['cost_dollars'] == pytest.approx(expected, abs=0.000001)
    cost_5m = claude_turn_cost(model, input_tokens=0, cache_read_tokens=0, cache_write_tokens=1000, cache_write_1h_tokens=0, output_tokens=0)
    cost_1h = claude_turn_cost(model, input_tokens=0, cache_read_tokens=0, cache_write_tokens=1000, cache_write_1h_tokens=1000, output_tokens=0)
    assert cost_1h == cost_5m * Decimal('1.6')


@pytest.mark.asyncio
async def test_compaction_reuses_turn_prefix_and_bills(monkeypatch):
    client = Client([_message('{"reply":"Summary","updates_json":"{}"}')])
    monkeypatch.setattr(_claude, 'get_async_client', lambda: client)
    turn = _claude.ClaudeTurnRef(_request(), CLAUDE_HAIKU, 'high', True)
    monkeypatch.setattr(pipeline.doc_svc, 'get_thread_message_count', AsyncMock(return_value=31))
    save = AsyncMock()
    bill = AsyncMock()
    monkeypatch.setattr(pipeline.doc_svc, 'save_context_summary', save)
    thread_id = uuid4()
    await pipeline._maybe_compact(thread_id, None, None, claude_turn=turn, assistant_reply='Saved reply', bill=bill)
    save.assert_awaited_once_with(thread_id, 'Summary', 31)
    bill.assert_awaited_once()
    sent = client.calls[0]
    assert sent['system'] == turn.request.system(structured=True)
    assert sent['messages'][:len(turn.request.history)] == turn.request.history
    assert sent['messages'][-2]['content'][0]['text'] == 'Saved reply'
    params = _claude.request_params(turn.request, model=turn.model, effort=turn.effort, structured=True, system_role=True)
    for key in ('thinking','model','output_config'):
        assert sent[key] == params[key]
    assert thread_id not in pipeline._compacting_threads


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', [RuntimeError('down'), _message('',usage=None), _message('{"reply":"')])
async def test_compaction_failure_is_nonfatal(monkeypatch, outcome):
    client = Client([outcome])
    monkeypatch.setattr(_claude, 'get_async_client', lambda: client)
    summary, _ = await _claude.summarize_thread(_claude.ClaudeTurnRef(_request(),CLAUDE_HAIKU,'medium',False),'reply')
    assert summary is None


@pytest.mark.asyncio
async def test_image_cache_hits_concurrent_fetch_and_preserves_gemini(monkeypatch):
    raw = _image('BMP', size=(2100, 1000))
    calls = []
    monkeypatch.setattr(_images, '_is_trusted_image_url', lambda _: True)
    def fetch(url):
        calls.append(url)
        return raw, 'image/bmp'
    monkeypatch.setattr(_images, '_fetch_image_bytes', fetch)
    messages = [{'image_urls':['https://cdn.test/image.bmp']} for _ in range(21)]
    await _images.fetch_image_parts_for_messages(messages)
    assert len(calls) == 1
    assert messages[0]['image_parts'] == [(raw,'image/bmp')]
    stable = messages[0]['claude_image_parts']
    assert stable == messages[-1]['claude_image_parts']
    assert stable[0][1] == 'image/jpeg'
    again = [{'image_urls':['https://cdn.test/image.bmp']}]
    await _images.fetch_image_parts_for_messages(again)
    assert again[0]['claude_image_parts'] == stable and len(calls) == 1


@pytest.mark.asyncio
async def test_image_cache_retries_failure_and_checks_trust(monkeypatch):
    monkeypatch.setattr(_images,'_is_trusted_image_url',lambda url: url != 'untrusted')
    attempts = iter([None, (_image('PNG'), 'image/png')])
    monkeypatch.setattr(_images,'_fetch_image_bytes',lambda _: next(attempts))
    messages = [{'image_urls':['untrusted', 'trusted', None]}]
    await _images.fetch_image_parts_for_messages(messages)
    assert 'image_parts' not in messages[0]
    await _images.fetch_image_parts_for_messages(messages)
    assert len(messages[0]['image_parts']) == 1
    await _images.fetch_image_parts_for_messages([])


def test_slide_rewrite_preserves_all_attachment_metadata():
    entry = {'role':'user','content':'Make it green','files':[('file','text')],'image_parts':[(b'png','image/png')],'extra':1}
    messages = [entry]
    state = {'slides':[{'title':'Chart','bullets':['Revenue'], 'speaker_notes':'Notes'}]}
    _inject_slide_context(messages,state,0)
    assert messages[0] is entry
    assert entry['original_content'] == 'Make it green'
    assert entry['files'] and entry['image_parts'] and entry['extra'] == 1
    before = entry['content']
    _inject_slide_context(messages,state,0)
    assert entry['content'] == before


@pytest.mark.asyncio
@pytest.mark.parametrize('count,summary,fetch_start,history_from', [(35,None,0,0),(51,30,15,0),(100,100,80,5)])
async def test_route_fetches_window_keeps_files_on_messages_and_bills_compaction(monkeypatch, count, summary, fetch_start, history_from):
    from datetime import datetime, timezone
    from app.matcha.routes.matcha_work import messaging
    from app.matcha.models.matcha_work.matcha_work import SendMessageRequest
    from app.matcha.services.matcha_work import matcha_work_ai

    thread_id, company_id, user_id = uuid4(), uuid4(), uuid4()
    thread = {'id':thread_id,'company_id':company_id,'current_state':{},'version':0,'status':'active','title':'Chat'}
    user = SimpleNamespace(id=user_id, role='client')
    rows = [{'role':'user' if i%2 == 0 else 'assistant','content':str(i),'metadata':None} for i in range(count-fetch_start)]
    for i in (0,len(rows)-1):
        rows[i]['metadata'] = json.dumps({'attachments':[{'kind':'file','filename':f'file-{i}.txt','text':f'text-{i}','url':f'https://cdn.test/{i}'}]})
    captured = []
    async def prepare(tc):
        captured.append(tc)
        tc.user_msg = {'id':uuid4(),'thread_id':thread_id,'role':'user','content':'Latest','created_at':datetime.now(timezone.utc)}
    monkeypatch.setattr(messaging,'get_client_company_id',AsyncMock(return_value=company_id))
    monkeypatch.setattr(messaging.doc_svc,'get_thread',AsyncMock(return_value=thread))
    monkeypatch.setattr(messaging,'_run_quota_gate',AsyncMock())
    monkeypatch.setattr(messaging,'_prepare_attachments',prepare)
    monkeypatch.setattr(messaging.doc_svc,'get_thread_message_count',AsyncMock(return_value=count))
    get_messages = AsyncMock(return_value=rows)
    monkeypatch.setattr(messaging.doc_svc,'get_thread_messages_from',get_messages)
    monkeypatch.setattr(messaging.doc_svc,'get_context_summary',AsyncMock(return_value=('Summary' if summary else None,summary)))
    monkeypatch.setattr(messaging.doc_svc,'get_company_profile_for_ai',AsyncMock(return_value={}))
    monkeypatch.setattr(messaging,'_build_company_context',lambda _: 'Company')
    monkeypatch.setattr(messaging,'_fetch_project_meta',AsyncMock(return_value=None))
    monkeypatch.setattr(messaging,'_inject_recruiting_project_context',AsyncMock(side_effect=lambda ctx,*a,**k:ctx+'Recruiting'))
    monkeypatch.setattr(matcha_work_ai,'fetch_image_parts_for_messages',AsyncMock())
    monkeypatch.setattr(messaging,'get_ai_provider',lambda:object())
    async def empty(tc):
        if False:
            yield ''
    for stage in ('_run_hard_stop_gates','_run_huume_dispatch','_inject_mode_contexts','_generate_turn'):
        monkeypatch.setattr(messaging,stage,empty)
    turn_ref = object()
    async def persist(tc):
        tc.ai_resp = SimpleNamespace(claude_turn=turn_ref)
        tc.assistant_msg = {**tc.user_msg,'id':uuid4(),'role':'assistant','content':'Audited reply'}
        tc.current_state = {}
        tc.current_version = 0
    monkeypatch.setattr(messaging,'_audit_and_persist',persist)
    compact, record = AsyncMock(), AsyncMock()
    monkeypatch.setattr(messaging,'_maybe_compact',compact)
    monkeypatch.setattr(messaging,'_record_turn_usage',record)
    background = []
    monkeypatch.setattr(messaging,'_track_background_task',background.append)
    response = await messaging.send_message_stream(thread_id,SendMessageRequest(content='Latest'),user)
    frames = [frame async for frame in response.body_iterator]
    await asyncio.gather(*background)
    assert any('"type": "complete"' in frame for frame in frames)
    tc = captured[0]
    get_messages.assert_awaited_once_with(thread_id,fetch_start)
    assert tc.history_from == history_from
    assert tc.msg_dicts[0]['files'] == [('file-0.txt','text-0')]
    assert tc.claude_ctx == 'CompanyRecruiting'
    assert '=== ATTACHED FILES ===' in tc.ctx and tc.ctx.endswith('Recruiting')
    assert len(tc.file_context_parts) == (2 if len(rows)<=20 else 1)
    assert len(tc.file_attachment_refs) == len(tc.file_context_parts)
    assert compact.await_args.kwargs['claude_turn'] is turn_ref
    assert compact.await_args.kwargs['assistant_reply'] == 'Audited reply'
    await compact.await_args.kwargs['bill']({'total_tokens':100})
    assert record.await_args.kwargs['operation'] == 'compaction'
    assert record.await_args.kwargs['company_id'] == company_id


@pytest.mark.asyncio
async def test_usage_records_precomputed_cache_cost(monkeypatch):
    usage = {'total_tokens':10,'cost_dollars':0.123,'estimated':False,'model':CLAUDE_HAIKU}
    log = AsyncMock()
    monkeypatch.setattr(pipeline.doc_svc,'log_token_usage_event',log)
    await pipeline._record_turn_usage(thread_id=uuid4(),company_id=uuid4(),user_id=uuid4(),user_role='admin',final_usage=usage,operation='compaction')
    assert log.await_args.kwargs['cost_dollars'] == 0.123
    assert log.await_args.kwargs['operation'] == 'compaction'


@pytest.mark.parametrize('raw', ['{"reply":"Finished sentence","updates_json":"{}"}', '{}', ''])
def test_even_valid_or_empty_json_reports_cutoff(raw):
    result = json.loads(_claude.reply_text(raw,stop_reason='max_tokens',structured=True))
    assert result['reply'].endswith(_claude.CUT_OFF_NOTE)


def test_image_cache_evicts_least_recent_bytes(monkeypatch):
    monkeypatch.setattr(_images,'_image_cache',LRUCache(maxsize=8,getsizeof=lambda parts:sum(len(p[0]) for p in parts)))
    monkeypatch.setattr(_images,'_fetch_image_bytes',lambda url:(url.encode(),'image/png'))
    monkeypatch.setattr(_claude,'normalize_image',lambda data,**kw:(data,'image/png'))
    for url in ['aa','bb','aa','cc']:
        _images._cached_image(url)
    assert set(_images._image_cache) == {'aa','cc'}
    assert _images._image_cache.currsize == 8
    assert not _images._image_pending


@pytest.mark.asyncio
async def test_history_query_clamps_offset_and_uses_unique_order(monkeypatch):
    from contextlib import asynccontextmanager
    from app.matcha.services.matcha_work.matcha_work_document import messages
    conn = SimpleNamespace(fetch=AsyncMock(return_value=[{'role':'user','content':'hello'}]))
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr(messages,'get_connection',connection)
    tid = uuid4()
    rows = await messages.get_thread_messages_from(tid,-1)
    sql, *args = conn.fetch.await_args.args
    assert 'ORDER BY created_at ASC, id ASC' in sql
    assert args == [tid,0]
    assert rows == [{'role':'user','content':'hello'}]


@pytest.mark.asyncio
@pytest.mark.parametrize('count,checkpoint', [(29,None),(45,30)])
async def test_compaction_threshold_keeps_recent_summary(monkeypatch,count,checkpoint):
    monkeypatch.setattr(pipeline.doc_svc,'get_thread_message_count',AsyncMock(return_value=count))
    summarize = AsyncMock()
    monkeypatch.setattr(_claude,'summarize_thread',summarize)
    await pipeline._maybe_compact(uuid4(),None,checkpoint,claude_turn=object())
    summarize.assert_not_awaited()
