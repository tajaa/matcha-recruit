import { useState, useRef, useCallback, useEffect } from 'react';
import type { WSMessage } from '../types';

const AUDIO_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const AUDIO_CHUNK_SIZE = 4096;
const PLAYAHEAD_SECONDS = 0.25;
const TURN_START_DELAY_SECONDS = 0.5;
const TURN_START_GRACE_SECONDS = 0.05;

// Audio message type prefixes (must match backend protocol)
const AUDIO_FROM_CLIENT = 0x01;
const AUDIO_FROM_SERVER = 0x02;

interface UseAudioInterviewReturn {
  isConnected: boolean;
  isRecording: boolean;
  messages: WSMessage[];
  connect: () => void;
  disconnect: () => void;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
}

export function useAudioInterview(interviewId: string): UseAudioInterviewReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [messages, setMessages] = useState<WSMessage[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const nextPlaybackTimeRef = useRef(0);

  const schedulePlayback = useCallback((buffer: AudioBuffer) => {
    const ctx = playbackContextRef.current;
    if (!ctx) return;

    const now = ctx.currentTime;
    const isNewTurn = nextPlaybackTimeRef.current <= now + TURN_START_GRACE_SECONDS;
    let startTime = Math.max(nextPlaybackTimeRef.current, now + PLAYAHEAD_SECONDS);

    if (isNewTurn) {
      startTime = Math.max(startTime, now + PLAYAHEAD_SECONDS + TURN_START_DELAY_SECONDS);
    }

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.start(startTime);
    nextPlaybackTimeRef.current = startTime + buffer.duration;
  }, []);

  // Play audio from server
  const playAudio = useCallback(
    async (pcmData: ArrayBuffer) => {
      if (!playbackContextRef.current) {
        playbackContextRef.current = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });
        nextPlaybackTimeRef.current = 0;
      }

      const ctx = playbackContextRef.current;
      if (ctx.state === 'suspended') {
        await ctx.resume();
      }

      const samples = new Int16Array(pcmData);
      const floatSamples = new Float32Array(samples.length);

      for (let i = 0; i < samples.length; i++) {
        floatSamples[i] = samples[i] / 32768;
      }

      const audioBuffer = ctx.createBuffer(1, floatSamples.length, OUTPUT_SAMPLE_RATE);
      audioBuffer.getChannelData(0).set(floatSamples);

      schedulePlayback(audioBuffer);
    },
    [schedulePlayback],
  );

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current) return;

    const ws = new WebSocket(`ws://localhost:8000/api/ws/interview/${interviewId}`);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      setIsConnected(true);
      setMessages((prev) => [
        ...prev,
        { type: 'system', content: 'Connected to interview', timestamp: Date.now() },
      ]);
    };

    ws.onclose = () => {
      setIsConnected(false);
      setMessages((prev) => [
        ...prev,
        { type: 'system', content: 'Disconnected', timestamp: Date.now() },
      ]);
      wsRef.current = null;
    };

    ws.onerror = () => {
      setMessages((prev) => [
        ...prev,
        { type: 'system', content: 'Connection error', timestamp: Date.now() },
      ]);
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        const dataView = new Uint8Array(event.data);
        if (dataView[0] === AUDIO_FROM_SERVER) {
          const audioData = event.data.slice(1);
          playAudio(audioData);
        }
        return;
      }

      if (event.data instanceof Blob) {
        const arrayBuffer = await event.data.arrayBuffer();
        const dataView = new Uint8Array(arrayBuffer);
        if (dataView[0] === AUDIO_FROM_SERVER) {
          const audioData = arrayBuffer.slice(1);
          playAudio(audioData);
        }
        return;
      }

      try {
        const msg: WSMessage = JSON.parse(event.data);
        setMessages((prev) => [...prev, msg]);
      } catch {
        console.error('Failed to parse message:', event.data);
      }
    };

    wsRef.current = ws;
  }, [interviewId, playAudio]);

  // Disconnect
  const disconnect = useCallback(() => {
    stopRecording();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (playbackContextRef.current) {
      playbackContextRef.current.close();
      playbackContextRef.current = null;
    }
    nextPlaybackTimeRef.current = 0;
    setIsConnected(false);
  }, []);

  // Start recording
  const startRecording = useCallback(async () => {
    if (!wsRef.current || isRecording) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: AUDIO_SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      mediaStreamRef.current = stream;
      audioContextRef.current = new AudioContext({ sampleRate: AUDIO_SAMPLE_RATE });

      const source = audioContextRef.current.createMediaStreamSource(stream);
      const processor = audioContextRef.current.createScriptProcessor(AUDIO_CHUNK_SIZE, 1, 1);

      processor.onaudioprocess = (e) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

        const inputData = e.inputBuffer.getChannelData(0);
        const pcmData = new Int16Array(inputData.length);

        for (let i = 0; i < inputData.length; i++) {
          pcmData[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
        }

        // Prepend the client audio prefix byte
        const framedData = new Uint8Array(1 + pcmData.byteLength);
        framedData[0] = AUDIO_FROM_CLIENT;
        framedData.set(new Uint8Array(pcmData.buffer), 1);

        wsRef.current.send(framedData);
      };

      source.connect(processor);
      processor.connect(audioContextRef.current.destination);
      processorRef.current = processor;

      setIsRecording(true);
    } catch (err) {
      console.error('Failed to start recording:', err);
      setMessages((prev) => [
        ...prev,
        { type: 'system', content: 'Failed to access microphone', timestamp: Date.now() },
      ]);
    }
  }, [isRecording]);

  // Stop recording
  const stopRecording = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    setIsRecording(false);
  }, []);

  // Cleanup on unmount and page refresh
  useEffect(() => {
    const handleBeforeUnload = () => {
      stopRecording();
      if (wsRef.current) {
        wsRef.current.close();
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      disconnect();
      if (playbackContextRef.current) {
        playbackContextRef.current.close();
      }
    };
  }, [disconnect, stopRecording]);

  return {
    isConnected,
    isRecording,
    messages,
    connect,
    disconnect,
    startRecording,
    stopRecording,
  };
}
