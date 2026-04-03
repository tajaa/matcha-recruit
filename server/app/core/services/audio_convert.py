"""Audio format conversion for Twilio ↔ Gemini Live bridging.

Twilio Media Streams: mulaw 8kHz
Gemini Live API: PCM signed 16-bit 16kHz
"""

try:
    import audioop
except ImportError:
    import audioop_lts as audioop  # Python 3.13+ fallback


def mulaw_8k_to_pcm_16k(mulaw_data: bytes) -> bytes:
    """Convert mulaw 8kHz audio to PCM 16-bit 16kHz for Gemini."""
    # mulaw → PCM 16-bit
    pcm_8k = audioop.ulaw2lin(mulaw_data, 2)
    # Resample 8kHz → 16kHz
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
    return pcm_16k


def pcm_16k_to_mulaw_8k(pcm_data: bytes) -> bytes:
    """Convert PCM 16-bit 16kHz from Gemini to mulaw 8kHz for Twilio."""
    # Resample 16kHz → 8kHz
    pcm_8k, _ = audioop.ratecv(pcm_data, 2, 1, 16000, 8000, None)
    # PCM 16-bit → mulaw
    return audioop.lin2ulaw(pcm_8k, 2)
