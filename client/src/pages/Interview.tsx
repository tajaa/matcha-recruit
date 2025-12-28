import { useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { useAudioInterview } from '../hooks/useAudioInterview';

export function Interview() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    isConnected,
    isRecording,
    messages,
    connect,
    disconnect,
    startRecording,
    stopRecording,
  } = useAudioInterview(id || '');

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleEnd = () => {
    disconnect();
    navigate(-1);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <div className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate(-1)} className="text-zinc-500 hover:text-zinc-300 transition-colors">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-2xl font-bold text-white">Culture Interview</h1>
      </div>

      <Card className="mb-6">
        <CardContent>
          {/* Connection Status */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div
                className={`w-3 h-3 rounded-full shadow-[0_0_10px_currentColor] transition-colors ${
                  isConnected ? 'bg-matcha-500 text-matcha-500' : 'bg-zinc-600 text-zinc-600'
                }`}
              />
              <span className="text-sm font-medium text-zinc-300">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {isRecording && (
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-red-500/10 border border-red-500/20">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span className="text-sm font-medium text-red-400">Recording</span>
              </div>
            )}
          </div>

          {/* Controls */}
          <div className="flex gap-4">
            {!isConnected ? (
              <Button onClick={connect} className="flex-1 py-4 text-lg">
                Connect to AI Interviewer
              </Button>
            ) : (
              <>
                {!isRecording ? (
                  <Button onClick={startRecording} className="flex-1 py-4 text-lg shadow-[0_0_20px_rgba(34,197,94,0.2)]">
                    <svg className="w-6 h-6 mr-3" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                      <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                    </svg>
                    Start Speaking
                  </Button>
                ) : (
                  <Button onClick={stopRecording} variant="danger" className="flex-1 py-4 text-lg">
                    <svg className="w-6 h-6 mr-3" fill="currentColor" viewBox="0 0 24 24">
                      <rect x="6" y="6" width="12" height="12" />
                    </svg>
                    Stop Speaking
                  </Button>
                )}
                <Button onClick={handleEnd} variant="secondary" className="px-8">
                  End
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Conversation */}
      <Card>
        <CardContent className="h-[500px] overflow-y-auto custom-scrollbar p-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-zinc-500 space-y-4">
              <div className="w-16 h-16 rounded-full bg-zinc-800 flex items-center justify-center">
                <svg className="w-8 h-8 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </div>
              <p>Connect and start speaking to begin the interview</p>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${
                    msg.type === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <div
                    className={`max-w-[80%] px-5 py-3 rounded-2xl shadow-md ${
                      msg.type === 'user'
                        ? 'bg-matcha-500 text-zinc-950 rounded-br-none'
                        : msg.type === 'assistant'
                        ? 'bg-zinc-800 text-zinc-100 rounded-bl-none border border-zinc-700'
                        : msg.type === 'system'
                        ? 'bg-yellow-500/10 text-yellow-400 text-sm border border-yellow-500/20 text-center mx-auto'
                        : 'bg-blue-500/10 text-blue-400 text-sm border border-blue-500/20 text-center mx-auto'
                    }`}
                  >
                    {msg.type === 'system' || msg.type === 'status' ? (
                      <span className="text-xs uppercase font-bold mr-2 opacity-75">
                        {msg.type}:
                      </span>
                    ) : null}
                    {msg.content}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Instructions */}
      <div className="mt-6 p-5 bg-matcha-500/5 rounded-xl border border-matcha-500/10">
        <h3 className="font-semibold text-matcha-400 mb-3 flex items-center gap-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Interview Tips
        </h3>
        <ul className="text-sm text-zinc-400 space-y-2 ml-1">
          <li className="flex items-start gap-2">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
            Speak naturally about your company's culture and values
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
            Share specific examples of how your team works together
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
            Describe what makes someone successful at your company
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-matcha-500 flex-shrink-0"></span>
            The AI will ask follow-up questions to understand better
          </li>
        </ul>
      </div>
    </div>
  );
}

export default Interview;
