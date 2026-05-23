# Voice Agent Setup Guide

A comprehensive reference for building real-time voice agents using Gemini Live API with WebSocket streaming. This document covers the full architecture implemented in Matcha Recruit for AI-powered voice interviews.

---

## Architecture Overview

```
┌─────────────────┐     WebSocket      ┌─────────────────┐    Gemini Live API    ┌─────────────────┐
│                 │   (Binary Audio)   │                 │    (Streaming)        │                 │
│     Browser     │ ◄────────────────► │  FastAPI Server │ ◄──────────────────►  │   Gemini API    │
│   (React App)   │   (JSON Messages)  │   (Python)      │                       │                 │
│                 │                    │                 │                       │                 │
└─────────────────┘                    └─────────────────┘                       └─────────────────┘
     │                                        │
     │ Web Audio API                          │ google-genai SDK
     │ - MediaStream (mic)                    │ - Live session
     │ - ScriptProcessor (capture)            │ - Async streaming
     │ - AudioContext (playback)              │ - Transcription
     │                                        │
```

### Data Flow

1. **User speaks** → Browser captures audio via `getUserMedia()`
2. **Audio chunks** → Converted to 16-bit PCM, prefixed with `0x01`, sent via WebSocket
3. **Server receives** → Strips prefix, forwards raw PCM to Gemini Live session
4. **Gemini processes** → Returns audio response chunks + transcriptions
5. **Server forwards** → Prefixes audio with `0x02`, sends to browser
6. **Browser plays** → Decodes PCM, schedules playback via AudioContext

---

## Audio Specifications

| Direction | Sample Rate | Format | Channels | Chunk Size |
|-----------|-------------|--------|----------|------------|
| Input (mic → server) | 16,000 Hz | Int16 PCM | Mono | 4096 samples |
| Output (server → speaker) | 24,000 Hz | Int16 PCM | Mono | Variable |

### Binary Message Protocol

All audio is sent as binary WebSocket messages with a 1-byte type prefix:

```
┌──────────┬─────────────────────────────────┐
│  Prefix  │         Audio Data (PCM)        │
│  1 byte  │         N bytes                 │
└──────────┴─────────────────────────────────┘
```

| Prefix | Direction | Description |
|--------|-----------|-------------|
| `0x01` | Client → Server | Audio from user's microphone |
| `0x02` | Server → Client | Audio from Gemini (AI response) |

### Text Messages (JSON)

Non-audio messages use JSON format:

```typescript
interface ConversationMessage {
  type: 'user' | 'assistant' | 'status' | 'system';
  content: string;
  timestamp: number;  // Unix ms
}
```

---

## Backend Implementation

### File Structure

```
server/app/
├── config.py                    # Environment & model config
├── protocol.py                  # Message types & framing
├── services/
│   └── gemini_session.py        # Gemini Live API wrapper
└── routes/
    └── interviews.py            # WebSocket endpoint
```

### 1. Configuration (`config.py`)

```python
@dataclass
class Settings:
    # Gemini API - choose one auth method
    gemini_api_key: Optional[str]      # Direct API key
    vertex_project: Optional[str]       # Or Vertex AI project
    vertex_location: str = "us-central1"

    # Model settings
    live_model: str = "gemini-live-2.5-flash-native-audio"
    voice: str = "Kore"  # Options: Kore, Puck, Charon, Fenrir, Aoede
```

**Environment Variables:**
```bash
# Option 1: API Key
LIVE_API=your-gemini-api-key

# Option 2: Vertex AI (requires service account)
VERTEX_PROJECT=your-gcp-project
VERTEX_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Model config
GEMINI_LIVE_MODEL=gemini-live-2.5-flash-native-audio
GEMINI_VOICE=Kore
```

### 2. Protocol (`protocol.py`)

```python
class AudioMessageType:
    FROM_CLIENT = 0x01
    FROM_SERVER = 0x02

def frame_audio_for_client(pcm_data: bytes) -> bytes:
    """Add prefix for server→client audio."""
    return bytes([AudioMessageType.FROM_SERVER]) + pcm_data

def parse_audio_from_client(data: bytes) -> Optional[bytes]:
    """Strip prefix from client→server audio."""
    if len(data) < 2:
        return None
    if data[0] == AudioMessageType.FROM_CLIENT:
        return data[1:]
    return None
```

### 3. Gemini Session (`gemini_session.py`)

This is the core wrapper around Google's `genai` library for live audio streaming.

```python
from google import genai
from google.genai import types

class GeminiLiveSession:
    def __init__(
        self,
        model: str,
        voice: str,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
    ):
        # Initialize client based on auth method
        if vertex_project:
            self.client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_location,
            )
        elif api_key:
            self.client = genai.Client(api_key=api_key)

        self.session = None
        self._response_queue: asyncio.Queue = asyncio.Queue()

        # Transcription buffers
        self._input_transcript_buffer = ""
        self._output_transcript_buffer = ""
        self.session_transcript: list[tuple[str, str]] = []

    async def connect(self, system_prompt: str) -> None:
        """Connect to Gemini Live with system instructions."""
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt)]
            ),
            # Enable transcription for both directions
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        self._session_context = self.client.aio.live.connect(
            model=self.model,
            config=config,
        )
        self.session = await self._session_context.__aenter__()

        # Start background receive loop
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def send_audio(self, pcm_data: bytes) -> None:
        """Send audio to Gemini."""
        await self.session.send_realtime_input(
            media=types.Blob(
                data=pcm_data,
                mime_type="audio/pcm;rate=16000",
            )
        )

    async def send_text(self, text: str) -> None:
        """Send text message (e.g., to trigger AI to speak first)."""
        await self.session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text=text)]
            ),
            turn_complete=True,
        )

    async def _receive_loop(self) -> None:
        """Background task to receive and queue responses."""
        async for response in self.session.receive():
            server_content = response.server_content
            if not server_content:
                continue

            # Handle audio chunks
            if server_content.model_turn:
                for part in server_content.model_turn.parts:
                    if part.inline_data:
                        await self._response_queue.put(
                            GeminiResponse(type="audio", audio_data=part.inline_data.data)
                        )

            # Handle input transcription (what user said)
            if hasattr(server_content, "input_transcription") and server_content.input_transcription:
                text = getattr(server_content.input_transcription, "text", None)
                if text:
                    self._input_transcript_buffer += text

            # Handle output transcription (what AI said)
            if hasattr(server_content, "output_transcription") and server_content.output_transcription:
                text = getattr(server_content.output_transcription, "text", None)
                if text:
                    self._output_transcript_buffer += text

            # Turn complete - flush transcription buffers
            if server_content.turn_complete:
                if self._input_transcript_buffer:
                    self.session_transcript.append(("user", self._input_transcript_buffer))
                    await self._response_queue.put(
                        GeminiResponse(type="transcription", text=self._input_transcript_buffer, is_input=True)
                    )
                    self._input_transcript_buffer = ""

                if self._output_transcript_buffer:
                    self.session_transcript.append(("assistant", self._output_transcript_buffer))
                    await self._response_queue.put(
                        GeminiResponse(type="transcription", text=self._output_transcript_buffer, is_input=False)
                    )
                    self._output_transcript_buffer = ""

                await self._response_queue.put(GeminiResponse(type="turn_complete"))

    async def receive_responses(self) -> AsyncIterator[GeminiResponse]:
        """Yield responses from queue."""
        while not self._closed:
            try:
                response = await asyncio.wait_for(self._response_queue.get(), timeout=0.1)
                yield response
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        """Clean up session."""
        self._closed = True
        if self._receive_task:
            self._receive_task.cancel()
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
```

### 4. WebSocket Endpoint (`interviews.py`)

```python
from fastapi import WebSocket

@router.websocket("/ws/interview/{interview_id}")
async def interview_websocket(websocket: WebSocket, interview_id: UUID):
    await websocket.accept()

    # Create Gemini session
    gemini_session = GeminiLiveSession(
        model=settings.live_model,
        voice=settings.voice,
        api_key=settings.gemini_api_key,
    )

    await gemini_session.connect(system_prompt=YOUR_SYSTEM_PROMPT)

    # Trigger AI to speak first
    await gemini_session.send_text("Please start the conversation now.")

    # Forward responses from Gemini → Client
    async def forward_responses():
        async for response in gemini_session.receive_responses():
            if response.type == "audio" and response.audio_data:
                await websocket.send_bytes(frame_audio_for_client(response.audio_data))
            elif response.type == "transcription":
                msg_type = "user" if response.is_input else "assistant"
                await websocket.send_text(ConversationMessage.create(msg_type, response.text).to_json())

    forward_task = asyncio.create_task(forward_responses())

    try:
        # Receive from client
        while True:
            data = await websocket.receive()

            if "bytes" in data:
                # Binary = audio
                audio = parse_audio_from_client(data["bytes"])
                if audio:
                    await gemini_session.send_audio(audio)

            elif "text" in data:
                # JSON = control message
                pass

    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        await gemini_session.close()
```

---

## Frontend Implementation

### File Structure

```
client/src/
├── hooks/
│   └── useAudioInterview.ts     # Core audio hook
└── pages/
    └── Interview.tsx            # UI component
```

### 1. Audio Hook (`useAudioInterview.ts`)

```typescript
const AUDIO_SAMPLE_RATE = 16000;      // Mic capture rate
const OUTPUT_SAMPLE_RATE = 24000;     // Playback rate (Gemini output)
const AUDIO_CHUNK_SIZE = 4096;        // Samples per chunk
const PLAYAHEAD_SECONDS = 0.25;       // Buffer ahead for smooth playback
const TURN_START_DELAY_SECONDS = 0.5; // Pause before AI speech starts

const AUDIO_FROM_CLIENT = 0x01;
const AUDIO_FROM_SERVER = 0x02;

export function useAudioInterview(interviewId: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [messages, setMessages] = useState<WSMessage[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const nextPlaybackTimeRef = useRef(0);

  // Schedule audio for gapless playback
  const schedulePlayback = useCallback((buffer: AudioBuffer) => {
    const ctx = playbackContextRef.current;
    if (!ctx) return;

    const now = ctx.currentTime;
    let startTime = Math.max(nextPlaybackTimeRef.current, now + PLAYAHEAD_SECONDS);

    // Add delay at start of new turn for natural pacing
    const isNewTurn = nextPlaybackTimeRef.current <= now + 0.05;
    if (isNewTurn) {
      startTime = Math.max(startTime, now + PLAYAHEAD_SECONDS + TURN_START_DELAY_SECONDS);
    }

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.start(startTime);

    nextPlaybackTimeRef.current = startTime + buffer.duration;
  }, []);

  // Play incoming audio from server
  const playAudio = useCallback(async (pcmData: ArrayBuffer) => {
    if (!playbackContextRef.current) {
      playbackContextRef.current = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });
      nextPlaybackTimeRef.current = 0;
    }

    const ctx = playbackContextRef.current;
    if (ctx.state === 'suspended') await ctx.resume();

    // Convert Int16 PCM to Float32
    const samples = new Int16Array(pcmData);
    const floatSamples = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      floatSamples[i] = samples[i] / 32768;
    }

    const audioBuffer = ctx.createBuffer(1, floatSamples.length, OUTPUT_SAMPLE_RATE);
    audioBuffer.getChannelData(0).set(floatSamples);

    schedulePlayback(audioBuffer);
  }, [schedulePlayback]);

  // Connect WebSocket
  const connect = useCallback(() => {
    const ws = new WebSocket(`ws://localhost:8000/api/ws/interview/${interviewId}`);
    ws.binaryType = 'arraybuffer';

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        const view = new Uint8Array(event.data);
        if (view[0] === AUDIO_FROM_SERVER) {
          playAudio(event.data.slice(1));
        }
        return;
      }

      // JSON message
      const msg = JSON.parse(event.data);
      setMessages(prev => [...prev, msg]);
    };

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);

    wsRef.current = ws;
  }, [interviewId, playAudio]);

  // Start microphone capture
  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: AUDIO_SAMPLE_RATE,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });

    audioContextRef.current = new AudioContext({ sampleRate: AUDIO_SAMPLE_RATE });
    const source = audioContextRef.current.createMediaStreamSource(stream);
    const processor = audioContextRef.current.createScriptProcessor(AUDIO_CHUNK_SIZE, 1, 1);

    processor.onaudioprocess = (e) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

      // Convert Float32 to Int16 PCM
      const input = e.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        pcm[i] = Math.max(-32768, Math.min(32767, input[i] * 32768));
      }

      // Frame with prefix and send
      const framed = new Uint8Array(1 + pcm.byteLength);
      framed[0] = AUDIO_FROM_CLIENT;
      framed.set(new Uint8Array(pcm.buffer), 1);

      wsRef.current.send(framed);
    };

    source.connect(processor);
    processor.connect(audioContextRef.current.destination);

    setIsRecording(true);
  }, []);

  // Stop recording
  const stopRecording = useCallback(() => {
    // Clean up audio nodes and stream
    setIsRecording(false);
  }, []);

  return { isConnected, isRecording, messages, connect, disconnect, startRecording, stopRecording };
}
```

### 2. Session Protection (Cost Control)

The hook includes safeguards to prevent runaway API costs:

```typescript
const IDLE_TIMEOUT_MS = 5 * 60 * 1000;        // Auto-disconnect after 5min idle
const MAX_SESSION_DURATION_MS = 12 * 60 * 1000; // Hard limit: 12 minutes
const WARNING_BEFORE_DISCONNECT_MS = 60 * 1000; // Warn 1 minute before

// Reset idle timer on any activity (audio in/out)
const resetIdleTimer = useCallback(() => {
  lastActivityTimeRef.current = Date.now();

  // Set warning at 4 minutes idle
  warningTimerRef.current = setTimeout(() => {
    setMessages(prev => [...prev, {
      type: 'system',
      content: '⚠️ Session idle - will disconnect in 1 minute',
      timestamp: Date.now(),
    }]);
  }, IDLE_TIMEOUT_MS - WARNING_BEFORE_DISCONNECT_MS);

  // Auto-disconnect at 5 minutes idle
  idleTimerRef.current = setTimeout(() => {
    wsRef.current?.close();
  }, IDLE_TIMEOUT_MS);
}, []);

// Track max session duration
const startSessionTimer = useCallback(() => {
  sessionStartTimeRef.current = Date.now();

  sessionTimerRef.current = setInterval(() => {
    const elapsed = Date.now() - sessionStartTimeRef.current;
    const remaining = Math.max(0, (MAX_SESSION_DURATION_MS - elapsed) / 1000);
    setSessionTimeRemaining(remaining);

    if (remaining === 0) {
      wsRef.current?.close();
    }
  }, 1000);
}, []);
```

---

## Prompt Engineering

### System Prompt Structure

For good conversational flow:

```python
SYSTEM_PROMPT = """You are an AI interviewer for {context}.

YOUR GOAL:
{Clear objective in 1-2 sentences}

INTERVIEW APPROACH:
- Be warm, professional, and conversational
- Ask open-ended questions that encourage detailed responses
- Keep responses concise (2-3 sentences max unless explaining)
- Don't use bullet points or lists in speech (this is voice!)
- Probe deeper on interesting points - ask follow-ups

KEY AREAS TO EXPLORE:
1. {Topic 1}
   - Sub-question
   - Sub-question
2. {Topic 2}
   ...

CONVERSATION FLOW:
1. Start with a warm greeting
2. Begin with easier questions
3. Naturally transition between topics
4. Dig deeper when they mention something interesting
5. Thank them and summarize key points

IMPORTANT:
- This is a voice conversation - be natural and human
- Don't overwhelm with multiple questions at once
- If they give short answers, ask follow-up questions
"""
```

### Triggering First Response

Send a text message to make the AI speak first:

```python
await gemini_session.send_text("Please start the interview now. Greet the person warmly and begin.")
```

---

## Key Design Decisions

### 1. Why Binary Framing?

WebSocket messages can be text or binary. Using a 1-byte prefix allows:
- Efficient routing without JSON parsing overhead
- Clear separation of audio vs control messages
- Simple protocol that's easy to debug

### 2. Why Separate Sample Rates?

- **16kHz input**: Standard for speech recognition, reduces bandwidth
- **24kHz output**: Gemini's native output rate, higher quality speech

### 3. Why ScriptProcessorNode?

Despite being deprecated, `ScriptProcessorNode` provides:
- Direct access to raw PCM samples
- Synchronous processing in the audio thread
- Simple integration with WebSocket streaming

(AudioWorklet is the modern alternative but adds complexity)

### 4. Why Queue-Based Receive?

The async queue pattern allows:
- Non-blocking receive loop
- Backpressure handling
- Clean separation of concerns

---

## Troubleshooting

### No Audio Playback
1. Check browser console for AudioContext errors
2. Ensure `AudioContext.resume()` is called after user interaction
3. Verify sample rate matches (24000 Hz for output)

### Audio Choppy/Delayed
1. Increase `PLAYAHEAD_SECONDS` buffer
2. Check network latency to Gemini API
3. Ensure client isn't CPU-bound

### Transcription Missing
1. Verify `input_audio_transcription` and `output_audio_transcription` are enabled in config
2. Check for `turn_complete` events to flush buffers

### Session Disconnects
1. Check idle timeout settings
2. Verify WebSocket keep-alive
3. Monitor Gemini API quotas

---

## Dependencies

### Backend (Python)
```
google-genai>=0.5.0
fastapi
websockets
python-dotenv
```

### Frontend (Node)
```
react
typescript
```

No additional audio libraries needed - uses native Web Audio API.

---

## Quick Start Checklist

1. [ ] Set up Gemini API key or Vertex AI credentials
2. [ ] Configure model (`gemini-live-2.5-flash-native-audio`) and voice
3. [ ] Implement `GeminiLiveSession` wrapper
4. [ ] Create WebSocket endpoint with bidirectional streaming
5. [ ] Build React hook with audio capture/playback
6. [ ] Add session protection (idle timeout, max duration)
7. [ ] Write system prompt for your use case
8. [ ] Test with headphones (to avoid echo)
