import { useEffect, useRef } from 'react';
import { X, Maximize2, Minimize2 } from 'lucide-react';
import { useState } from 'react';

interface VideoCallProps {
  roomName: string;
  displayName: string;
  onClose: () => void;
}

export function VideoCall({ roomName, displayName, onClose }: VideoCallProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sanitize room name for Jitsi (alphanumeric and hyphens only)
  const jitsiRoomName = `matcha-${roomName}`.replace(/[^a-zA-Z0-9-]/g, '');

  // Build Jitsi URL with config
  const jitsiUrl = new URL(`https://meet.jit.si/${jitsiRoomName}`);
  jitsiUrl.hash = `#config.prejoinPageEnabled=false&userInfo.displayName="${encodeURIComponent(displayName)}"`;

  const toggleFullscreen = () => {
    if (!containerRef.current) return;

    if (!isFullscreen) {
      containerRef.current.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  return (
    <div
      ref={containerRef}
      className="flex-1 flex flex-col bg-zinc-950 relative"
    >
      {/* Controls overlay */}
      <div className="absolute top-0 left-0 right-0 z-10 p-3 flex items-center justify-between bg-gradient-to-b from-black/80 to-transparent">
        <div className="text-xs text-white/70 font-mono uppercase tracking-wider">
          Video Call • {roomName}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleFullscreen}
            className="p-2 hover:bg-white/10 rounded transition-colors text-white/70 hover:text-white"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? (
              <Minimize2 className="w-4 h-4" />
            ) : (
              <Maximize2 className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={onClose}
            className="p-2 hover:bg-red-500/20 rounded transition-colors text-white/70 hover:text-red-400"
            title="Leave call"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Jitsi iframe */}
      <iframe
        src={jitsiUrl.toString()}
        allow="camera; microphone; display-capture; autoplay; clipboard-write"
        className="flex-1 w-full border-0"
        style={{ minHeight: '400px' }}
      />
    </div>
  );
}
