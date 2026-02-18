import { useState, useEffect, useRef } from 'react';
import { Mic, Volume2, Globe, CheckCircle2, X, Activity } from 'lucide-react';
import { Button } from './Button';
import { AsciiWaveform } from './AsciiWaveform';
import { auth } from '../api/client';

interface SystemCheckModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SystemCheckModal({ isOpen, onClose }: SystemCheckModalProps) {
  const [micStatus, setMicStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [speakerStatus, setSpeakerStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle');
  const [volume, setVolume] = useState(0);
  
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animationRef = useRef<number | null>(null);

  // Cleanup on close
  useEffect(() => {
    if (!isOpen) {
      stopMicTest();
    }
  }, [isOpen]);

  const startMicTest = async () => {
    setMicStatus('testing');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      
      const updateVolume = () => {
        analyser.getByteFrequencyData(dataArray);
        // Calculate average
        const sum = dataArray.reduce((a, b) => a + b, 0);
        const avg = sum / dataArray.length;
        // Normalize 0-255 to 0-1
        setVolume(avg / 64); // Boost sensitivity
        animationRef.current = requestAnimationFrame(updateVolume);
      };
      
      updateVolume();
      
    } catch (err) {
      console.error(err);
      setMicStatus('error');
    }
  };

  const stopMicTest = () => {
    if (animationRef.current) cancelAnimationFrame(animationRef.current);
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    if (audioContextRef.current) audioContextRef.current.close();
    streamRef.current = null;
    audioContextRef.current = null;
    setVolume(0);
  };

  const playTestSound = () => {
    setSpeakerStatus('testing');
    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      
      osc.type = 'sine';
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.1);
      
      gain.gain.setValueAtTime(0.1, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
      
      osc.start();
      osc.stop(ctx.currentTime + 0.5);
      
      setTimeout(() => setSpeakerStatus('success'), 500);
    } catch (err) {
      console.error(err);
      setSpeakerStatus('error');
    }
  };

  const testConnection = async () => {
    setConnectionStatus('testing');
    try {
      await auth.me(); // Simple ping
      setConnectionStatus('success');
    } catch {
      setConnectionStatus('error');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 shadow-2xl relative animate-in fade-in zoom-in duration-200">
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 text-zinc-500 hover:text-white"
        >
          <X size={20} />
        </button>
        
        <div className="p-8 border-b border-white/10">
          <h2 className="text-xl font-bold text-white uppercase tracking-wider flex items-center gap-3">
            <Activity className="w-5 h-5 text-emerald-500" />
            System Diagnostic
          </h2>
          <p className="text-zinc-500 text-xs mt-2 font-mono uppercase">
            Verify your hardware and connection environment.
          </p>
        </div>

        <div className="p-8 space-y-8">
          {/* Microphone */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded ${micStatus === 'success' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-zinc-900 text-zinc-400'}`}>
                  <Mic size={18} />
                </div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wide">Microphone Input</h3>
              </div>
              {micStatus === 'testing' ? (
                <div className="flex gap-2">
                  <button onClick={() => { setMicStatus('success'); stopMicTest(); }} className="text-[10px] bg-emerald-500 text-black px-3 py-1 font-bold uppercase hover:bg-emerald-400">Working</button>
                  <button onClick={() => { setMicStatus('error'); stopMicTest(); }} className="text-[10px] border border-red-500 text-red-500 px-3 py-1 font-bold uppercase hover:bg-red-500/10">Failed</button>
                </div>
              ) : (
                <Button variant="secondary" onClick={startMicTest} className="text-[10px] h-8 bg-transparent border border-zinc-700 text-zinc-300">Test Input</Button>
              )}
            </div>
            
            {micStatus === 'testing' && (
              <div className="bg-black/40 border border-white/10 p-4 rounded text-center">
                <div className="py-2">
                   <AsciiWaveform isRecording={false} isPlaying={false} level={volume} />
                </div>
                <p className="text-[10px] text-zinc-600 mt-2 font-mono uppercase">Speak to verify input level</p>
              </div>
            )}
            
            {micStatus === 'error' && <p className="text-xs text-red-500">Microphone access denied or not detected.</p>}
            {micStatus === 'success' && <p className="text-xs text-emerald-500 flex items-center gap-2"><CheckCircle2 size={12} /> Input Verified</p>}
          </div>

          {/* Speakers */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded ${speakerStatus === 'success' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-zinc-900 text-zinc-400'}`}>
                  <Volume2 size={18} />
                </div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wide">Audio Output</h3>
              </div>
              <Button variant="secondary" onClick={playTestSound} className="text-[10px] h-8 bg-transparent border border-zinc-700 text-zinc-300">Play Sound</Button>
            </div>
            {speakerStatus === 'success' && <p className="text-xs text-emerald-500 flex items-center gap-2"><CheckCircle2 size={12} /> Output Verified</p>}
          </div>

          {/* Connection */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded ${connectionStatus === 'success' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-zinc-900 text-zinc-400'}`}>
                  <Globe size={18} />
                </div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wide">Server Connection</h3>
              </div>
              <Button variant="secondary" onClick={testConnection} className="text-[10px] h-8 bg-transparent border border-zinc-700 text-zinc-300">Ping Server</Button>
            </div>
            {connectionStatus === 'success' && <p className="text-xs text-emerald-500 flex items-center gap-2"><CheckCircle2 size={12} /> Connection Stable</p>}
            {connectionStatus === 'error' && <p className="text-xs text-red-500">Unable to reach API server.</p>}
          </div>
        </div>

        <div className="p-6 border-t border-white/10 bg-zinc-900/50 flex justify-end">
          <Button onClick={onClose} className="px-8 bg-white text-black hover:bg-zinc-200 font-bold uppercase tracking-widest text-xs">Close Diagnostics</Button>
        </div>
      </div>
    </div>
  );
}
