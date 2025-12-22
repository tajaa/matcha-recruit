import { useState, useRef, useCallback, useEffect } from 'react';
import type { WSMessage } from '../types';

const AUDIO_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const AUDIO_CHUNK_SIZE = 4096;
const PLAYAHEAD_SECONDS = 0.25;
const TURN_START_DELAY_SECONDS = 0.5;
const TURN_START_GRACE_SECONDS = 0.05;

// Session protection constants
const IDLE_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes idle = auto-disconnect
const MAX_SESSION_DURATION_MS = 30 * 60 * 1000; // 30 minutes max session
const WARNING_BEFORE_DISCONNECT_MS = 60 * 1000; // Warn 1 minute before auto-disconnect

// Audio message type prefixes (must match backend protocol)
const AUDIO_FROM_CLIENT = 0x01;
const AUDIO_FROM_SERVER = 0x02;

interface UseAudioInterviewReturn {
  isConnected: boolean;
  isRecording: boolean;
  messages: WSMessage[];
  sessionTimeRemaining: number | null; // seconds remaining, null if not connected
  idleWarning: boolean;
  connect: () => void;
  disconnect: () => void;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  resetIdleTimer: () => void;
}

export function useAudioInterview(interviewId: string): UseAudioInterviewReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [messages, setMessages] = useState<WSMessage[]>([]);
  const [sessionTimeRemaining, setSessionTimeRemaining] = useState<number | null>(null);
  const [idleWarning, setIdleWarning] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const nextPlaybackTimeRef = useRef(0);

  // Session protection refs
  const sessionStartTimeRef = useRef<number | null>(null);
  const lastActivityTimeRef = useRef<number>(Date.now());
  const idleTimerRef = useRef<NodeJS.Timeout | null>(null);
  const sessionTimerRef = useRef<NodeJS.Timeout | null>(null);
  const warningTimerRef = useRef<NodeJS.Timeout | null>(null);

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

  // Clear all session protection timers
  const clearAllTimers = useCallback(() => {
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
      idleTimerRef.current = null;
    }
    if (sessionTimerRef.current) {
      clearInterval(sessionTimerRef.current);
      sessionTimerRef.current = null;
    }
    if (warningTimerRef.current) {
      clearTimeout(warningTimerRef.current);
      warningTimerRef.current = null;
    }
    setIdleWarning(false);
    setSessionTimeRemaining(null);
  }, []);

  // Reset idle timer (called on any activity)
  const resetIdleTimer = useCallback(() => {
    lastActivityTimeRef.current = Date.now();
    setIdleWarning(false);

    // Clear existing idle timer
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
    }
    if (warningTimerRef.current) {
      clearTimeout(warningTimerRef.current);
    }

    if (!wsRef.current || !isConnected) return;

    // Set warning timer (1 minute before disconnect)
    warningTimerRef.current = setTimeout(() => {
      setIdleWarning(true);
      setMessages((prev) => [
        ...prev,
        {
          type: 'system',
          content: '⚠️ Session idle - will disconnect in 1 minute. Click or speak to stay connected.',
          timestamp: Date.now(),
        },
      ]);
    }, IDLE_TIMEOUT_MS - WARNING_BEFORE_DISCONNECT_MS);

    // Set disconnect timer
    idleTimerRef.current = setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          type: 'system',
          content: '🔌 Session disconnected due to inactivity (saving API credits)',
          timestamp: Date.now(),
        },
      ]);
      // Will call disconnect after setting message
      if (wsRef.current) {
        wsRef.current.close();
      }
    }, IDLE_TIMEOUT_MS);
  }, [isConnected]);

  // Start session timer (tracks max duration)
  const startSessionTimer = useCallback(() => {
    sessionStartTimeRef.current = Date.now();

    // Update remaining time every second
    sessionTimerRef.current = setInterval(() => {
      if (!sessionStartTimeRef.current) return;

      const elapsed = Date.now() - sessionStartTimeRef.current;
      const remaining = Math.max(0, Math.floor((MAX_SESSION_DURATION_MS - elapsed) / 1000));
      setSessionTimeRemaining(remaining);

      // Warn at 5 minutes remaining
      if (remaining === 300) {
        setMessages((prev) => [
          ...prev,
          {
            type: 'system',
            content: '⏱️ 5 minutes remaining in session',
            timestamp: Date.now(),
          },
        ]);
      }

      // Warn at 1 minute remaining
      if (remaining === 60) {
        setMessages((prev) => [
          ...prev,
          {
            type: 'system',
            content: '⚠️ 1 minute remaining - session will end soon',
            timestamp: Date.now(),
          },
        ]);
      }

      // Auto-disconnect at max duration
      if (remaining === 0) {
        setMessages((prev) => [
          ...prev,
          {
            type: 'system',
            content: '⏰ Maximum session duration reached (30 minutes). Disconnecting to save API credits.',
            timestamp: Date.now(),
          },
        ]);
        if (wsRef.current) {
          wsRef.current.close();
        }
      }
    }, 1000);

    resetIdleTimer();
  }, [resetIdleTimer]);

  // Play audio from server
  const playAudio = useCallback(
    async (pcmData: ArrayBuffer) => {
      // Reset idle timer on incoming audio (activity)
      resetIdleTimer();

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
    [schedulePlayback, resetIdleTimer],
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
      startSessionTimer();
    };

    ws.onclose = () => {
      setIsConnected(false);
      clearAllTimers();
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
  }, [interviewId, playAudio, startSessionTimer, clearAllTimers]);

  // Disconnect
  const disconnect = useCallback(() => {
    stopRecording();
    clearAllTimers();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (playbackContextRef.current) {
      playbackContextRef.current.close();
      playbackContextRef.current = null;
    }
    nextPlaybackTimeRef.current = 0;
    sessionStartTimeRef.current = null;
    setIsConnected(false);
  }, [clearAllTimers]);

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

        // Reset idle timer on outgoing audio (user activity)
        resetIdleTimer();

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
    sessionTimeRemaining,
    idleWarning,
    connect,
    disconnect,
    startRecording,
    stopRecording,
    resetIdleTimer,
  };
}
