"""Reply streaming transport, recovery boundaries and accounting."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import anthropic
import httpx2
import pytest

from app.core.services.anthropic_messages import CLAUDE_HAIKU
from app.matcha.models.matcha_work.matcha_work import SendMessageRequest
from app.matcha.services.matcha_work import turn_pipeline as pipeline
from app.matcha.services.matcha_work.matcha_work_ai import _claude, provider
from tests.matcha_work.test_claude_thread_cache import Client, isolate  # noqa: F401
from tests.matcha_work.test_skill_engine_claude import _message, _request


class Stream:
    def __init__(self, chunks, *, error=None, stall=False):
        self.chunks, self.error, self.stall = chunks, error, stall
        self.current_message_snapshot = _message('{"reply":"Hello 🫖","updates_json":"{}"}')
        self.closed = False
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        self.closed = True
    @property
    def text_stream(self):
        async def events():
            for chunk in self.chunks:
                yield chunk
            if self.stall:
                await asyncio.sleep(10)
            if self.error:
                raise self.error
        return events()
    async def get_final_message(self):
        return self.current_message_snapshot


class StreamingClient(Client):
    def __init__(self, stream):
        super().__init__([stream.current_message_snapshot])
        self.stream = stream
        self.stream_params = None
        self.beta.messages.stream = self.open
    def open(self, **params):
        self.stream_params = params
        return self.stream


@pytest.mark.asyncio
async def test_stream_decodes_reply_only_and_keeps_request_cache(monkeypatch):
    raw = json.dumps({'nested':{'reply':'ignore'},'reply':'Hello 🫖','updates_json':'{}'})
    stream = Stream(list(raw))
    client = StreamingClient(stream)
    monkeypatch.setattr(_claude,'get_async_client',lambda:client)
    monkeypatch.delenv('MATCHA_WORK_CLAUDE_STREAMING', raising=False)
    deltas = []
    result = await _claude.call_claude_thread(_request(),model=CLAUDE_HAIKU,effort='medium',timeout_seconds=3,on_reply_delta=deltas.append)
    assert ''.join(deltas) == 'Hello 🫖'
    assert json.loads(result.text)['reply'] == 'Hello 🫖'
    assert client.stream_params == _claude.request_params(_request(),model=CLAUDE_HAIKU,effort='medium',system_role=True,structured=True)
    assert not client.calls and stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('setting', ['false','0','off','no'])
async def test_stream_kill_switch_uses_create(monkeypatch, setting):
    client = StreamingClient(Stream([]))
    monkeypatch.setattr(_claude,'get_async_client',lambda:client)
    monkeypatch.setenv('MATCHA_WORK_CLAUDE_STREAMING',setting)
    deltas = []
    await _claude.call_claude_thread(_request(),model=CLAUDE_HAIKU,effort='medium',timeout_seconds=3,on_reply_delta=deltas.append)
    assert client.stream_params is None and len(client.calls) == 1
    assert not deltas


@pytest.mark.asyncio
@pytest.mark.parametrize('partial', [False,True])
async def test_provider_fallback_only_before_first_delta(monkeypatch, partial):
    engine = provider.GeminiProvider.__new__(provider.GeminiProvider)
    fallback = AsyncMock(return_value=provider.AIResponse('Gemini'))
    monkeypatch.setattr(engine,'_gemini_fallback',fallback)
    usage = {'prompt_tokens':3, 'total_tokens':4}
    async def call(*args, on_reply_delta=None, **kwargs):
        if partial:
            on_reply_delta('Hi')
        raise _claude.ClaudeCallFailed('connection failed',usage)
    monkeypatch.setattr(provider,'call_claude_thread',call)
    monkeypatch.setattr(provider,'record_claude_call',AsyncMock())
    deltas = []
    if partial:
        with pytest.raises(_claude.ClaudeCallFailed) as exc:
            await engine._generate_claude(_request(),CLAUDE_HAIKU,'medium',fallback=(),on_reply_delta=deltas.append)
        assert exc.value.usage == usage
        fallback.assert_not_awaited()
        assert deltas == ['Hi']
    else:
        result = await engine._generate_claude(_request(),CLAUDE_HAIKU,'medium',fallback=(),on_reply_delta=deltas.append)
        assert result.assistant_reply == 'Gemini'
        fallback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('timeout', [False,True])
async def test_partial_stream_failure_carries_usage_and_closes(monkeypatch, timeout):
    error = anthropic.APIConnectionError(request=httpx2.Request('POST','https://api.anthropic.com/v1/messages'))
    stream = Stream(['{"reply":"Hi'], error=error if not timeout else None, stall=timeout)
    monkeypatch.setattr(_claude,'get_async_client',lambda:StreamingClient(stream))
    with pytest.raises(_claude.ClaudeCallFailed) as exc:
        await asyncio.wait_for(_claude.call_claude_thread(_request(),model=CLAUDE_HAIKU,effort='medium',timeout_seconds=3,on_reply_delta=lambda _:None),timeout=0.01)
    assert exc.value.usage['prompt_tokens'] == 100
    assert stream.closed


def make_turn(generate, *, hr=False):
    tc = pipeline.TurnContext(thread_id=uuid4(),company_id=uuid4(),current_user=SimpleNamespace(id=uuid4(),role='client'),
                              body=SendMessageRequest(content='Hi'),thread={'current_state':{}})
    tc.ai_provider = SimpleNamespace(generate=generate,estimate_usage=AsyncMock(return_value={'total_tokens':10,'estimated':True}))
    tc.msg_dicts = [{'role':'user','content':'Hi'}]
    tc.hr_pilot_mode_active = hr
    return tc


@pytest.mark.asyncio
@pytest.mark.parametrize('hr', [False,True])
async def test_pipeline_coalesces_deltas_and_preserves_final_response(hr):
    chunks = ['a']*210 + [' 🫖']
    authoritative = provider.AIResponse('Final audited response')
    async def generate(*a, on_reply_delta=None, **kw):
        assert (on_reply_delta is None) is hr
        if on_reply_delta:
            for chunk in chunks:
                on_reply_delta(chunk)
        return authoritative
    tc = make_turn(generate,hr=hr)
    async def collect():
        return [json.loads(frame[len('data: '):]) async for frame in pipeline._generate_turn(tc)]
    events = await asyncio.wait_for(collect(), timeout=0.5)
    deltas = [event['text'] for event in events if event['type']=='delta']
    assert ''.join(deltas) == ('' if hr else ''.join(chunks))
    assert len(deltas) <= 2
    assert tc.ai_resp is authoritative


@pytest.mark.asyncio
async def test_pipeline_partial_failure_bills_once_then_errors(monkeypatch):
    usage = {'total_tokens':4,'estimated':False}
    async def generate(*a,on_reply_delta=None,**kw):
        on_reply_delta('Partial')
        raise _claude.ClaudeCallFailed('Interrupted',usage)
    bill = AsyncMock()
    monkeypatch.setattr(pipeline,'_record_turn_usage',bill)
    tc = make_turn(generate)
    frames = []
    with pytest.raises(_claude.ClaudeCallFailed):
        async for frame in pipeline._generate_turn(tc):
            frames.append(frame)
    assert any('"type": "delta"' in f for f in frames)
    bill.assert_awaited_once()
    assert bill.await_args.kwargs['final_usage'] is usage


@pytest.mark.asyncio
async def test_disconnect_after_last_delta_still_schedules_accounting(monkeypatch):
    async def generate(*a,on_reply_delta=None,**kw):
        on_reply_delta('Done')
        return provider.AIResponse('Done',token_usage={'total_tokens':4})
    finalizer = AsyncMock()
    monkeypatch.setattr(pipeline,'_finalize_cancelled_turn',finalizer)
    tasks = []
    monkeypatch.setattr(pipeline,'_track_background_task',tasks.append)
    tc = make_turn(generate)
    iterator = pipeline._generate_turn(tc)
    async for frame in iterator:
        if '"type": "delta"' in frame:
            break
    assert tc.ai_task.done()
    await iterator.aclose()
    await asyncio.gather(*tasks)
    finalizer.assert_awaited_once()
    assert tc.cancel_finalized


@pytest.mark.asyncio
async def test_provider_hr_pilot_does_not_receive_callback(monkeypatch):
    monkeypatch.setattr(provider,'_get_model',AsyncMock(return_value=CLAUDE_HAIKU))
    call = AsyncMock(return_value=_claude.ClaudeResult('{"reply":"Audited later"}',None,'end_turn',True))
    monkeypatch.setattr(provider,'call_claude_thread',call)
    monkeypatch.setattr(provider,'record_claude_call',AsyncMock())
    await provider.GeminiProvider().generate([{'role':'user','content':'Hi'}],{},hr_pilot_mode=True,on_reply_delta=lambda _:None)
    assert call.await_args.kwargs['on_reply_delta'] is None


@pytest.mark.asyncio
async def test_small_delta_is_visible_before_model_finishes():
    finish = asyncio.Event()
    async def generate(*a,on_reply_delta=None,**kw):
        on_reply_delta('First words')
        await finish.wait()
        on_reply_delta(' and more')
        return provider.AIResponse('Authoritative reply')
    tc = make_turn(generate)
    iterator = pipeline._generate_turn(tc)
    await anext(iterator)  # estimate
    await anext(iterator)  # status
    first = await asyncio.wait_for(anext(iterator),timeout=0.5)
    assert json.loads(first[len('data: '):]) == {'type':'delta','text':'First words'}
    assert not tc.ai_task.done()
    finish.set()
    rest = [frame async for frame in iterator]
    assert any(' and more' in frame for frame in rest)
    assert tc.ai_resp.assistant_reply == 'Authoritative reply'
