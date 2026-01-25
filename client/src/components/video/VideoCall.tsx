import { useEffect, useRef, useState, memo } from 'react';
import { X, Maximize2, Minimize2 } from 'lucide-react';

// Declare JitsiMeetExternalAPI on window
declare global {
  interface Window {
    JitsiMeetExternalAPI: new (domain: string, options: JitsiMeetOptions) => JitsiMeetAPI;
  }
}

interface JitsiMeetOptions {
  roomName: string;
  parentNode: HTMLElement;
  width: string;
  height: string;
  userInfo?: {
    displayName: string;
  };
  configOverwrite?: Record<string, unknown>;
  interfaceConfigOverwrite?: Record<string, unknown>;
}

interface JitsiMeetAPI {
  dispose: () => void;
  executeCommand: (command: string, ...args: unknown[]) => void;
  addListener: (event: string, callback: (...args: unknown[]) => void) => void;
}

interface VideoCallProps {
  roomName: string;
  displayName: string;
  onClose: () => void;
}

export const VideoCall = memo(function VideoCall({ roomName, displayName, onClose }: VideoCallProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const jitsiContainerRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<JitsiMeetAPI | null>(null);

  // Sanitize room name for Jitsi (alphanumeric and hyphens only)
  const jitsiRoomName = `matcha-${roomName}`.replace(/[^a-zA-Z0-9-]/g, '');

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

  // Load Jitsi API and initialize meeting
  useEffect(() => {
    if (!jitsiContainerRef.current) return;

    const loadJitsiScript = () => {
      return new Promise<void>((resolve, reject) => {
        if (window.JitsiMeetExternalAPI) {
          resolve();
          return;
        }

        const script = document.createElement('script');
        script.src = 'https://meet.jit.si/external_api.js';
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Failed to load Jitsi API'));
        document.head.appendChild(script);
      });
    };

    const initJitsi = async () => {
      try {
        await loadJitsiScript();

        if (!jitsiContainerRef.current || apiRef.current) return;

        const api = new window.JitsiMeetExternalAPI('meet.jit.si', {
          roomName: jitsiRoomName,
          parentNode: jitsiContainerRef.current,
          width: '100%',
          height: '100%',
          userInfo: {
            displayName: displayName,
          },
          configOverwrite: {
            prejoinPageEnabled: false,
            startWithAudioMuted: false,
            startWithVideoMuted: false,
            disableDeepLinking: true,
            disableInviteFunctions: true,
            enableClosePage: false,
            hideConferenceSubject: true,
            hideConferenceTimer: true,
          },
          interfaceConfigOverwrite: {
            SHOW_JITSI_WATERMARK: false,
            SHOW_WATERMARK_FOR_GUESTS: false,
            SHOW_BRAND_WATERMARK: false,
            SHOW_POWERED_BY: false,
            SHOW_PROMOTIONAL_CLOSE_PAGE: false,
            DISABLE_JOIN_LEAVE_NOTIFICATIONS: true,
            HIDE_INVITE_MORE_HEADER: true,
            TOOLBAR_BUTTONS: [
              'microphone',
              'camera',
              'desktop',
              'fullscreen',
              'hangup',
              'chat',
              'settings',
              'tileview',
            ],
          },
        });

        apiRef.current = api;
        setIsLoading(false);

        // Handle when user hangs up from Jitsi UI
        api.addListener('readyToClose', () => {
          onClose();
        });
      } catch (error) {
        console.error('Failed to initialize Jitsi:', error);
        setIsLoading(false);
      }
    };

    initJitsi();

    return () => {
      if (apiRef.current) {
        apiRef.current.dispose();
        apiRef.current = null;
      }
    };
  }, [jitsiRoomName, displayName, onClose]);

  return (
    <div
      ref={containerRef}
      className="flex-1 flex flex-col bg-zinc-950 relative"
    >
      {/* Controls overlay */}
      <div className="absolute top-0 left-0 right-0 z-10 p-3 flex items-center justify-between bg-gradient-to-b from-black/80 to-transparent pointer-events-none">
        <div className="text-xs text-white/70 font-mono uppercase tracking-wider">
          Video Call • {roomName}
        </div>
        <div className="flex items-center gap-2 pointer-events-auto">
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

      {/* Loading state */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-zinc-950 z-5">
          <div className="text-center">
            <div className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse mx-auto mb-3" />
            <p className="text-xs text-zinc-500 font-mono uppercase tracking-wider">
              Starting video call...
            </p>
          </div>
        </div>
      )}

      {/* Jitsi container */}
      <div
        ref={jitsiContainerRef}
        className="flex-1 w-full"
        style={{ minHeight: '400px' }}
      />
    </div>
  );
});
