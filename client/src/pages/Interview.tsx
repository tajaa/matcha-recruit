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
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate(-1)} className="text-gray-500 hover:text-gray-700">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-2xl font-bold text-gray-900">Culture Interview</h1>
      </div>

      <Card className="mb-6">
        <CardContent>
          {/* Connection Status */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full ${
                  isConnected ? 'bg-matcha-500' : 'bg-gray-300'
                }`}
              />
              <span className="text-sm text-gray-600">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {isRecording && (
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500 animate-pulse" />
                <span className="text-sm text-red-600">Recording</span>
              </div>
            )}
          </div>

          {/* Controls */}
          <div className="flex gap-3">
            {!isConnected ? (
              <Button onClick={connect} className="flex-1">
                Connect
              </Button>
            ) : (
              <>
                {!isRecording ? (
                  <Button onClick={startRecording} className="flex-1">
                    <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                      <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                    </svg>
                    Start Speaking
                  </Button>
                ) : (
                  <Button onClick={stopRecording} variant="danger" className="flex-1">
                    <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 24 24">
                      <rect x="6" y="6" width="12" height="12" />
                    </svg>
                    Stop
                  </Button>
                )}
                <Button onClick={handleEnd} variant="secondary">
                  End Interview
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Conversation */}
      <Card>
        <CardContent className="h-[400px] overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-400">
              <p>Connect and start speaking to begin the interview</p>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${
                    msg.type === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <div
                    className={`max-w-[80%] px-4 py-2 rounded-2xl ${
                      msg.type === 'user'
                        ? 'bg-matcha-500 text-white rounded-br-md'
                        : msg.type === 'assistant'
                        ? 'bg-gray-100 text-gray-900 rounded-bl-md'
                        : msg.type === 'system'
                        ? 'bg-yellow-50 text-yellow-800 text-sm'
                        : 'bg-blue-50 text-blue-800 text-sm'
                    }`}
                  >
                    {msg.type === 'system' || msg.type === 'status' ? (
                      <span className="text-xs uppercase font-medium mr-2">
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
      <div className="mt-6 p-4 bg-matcha-50 rounded-lg">
        <h3 className="font-medium text-matcha-800 mb-2">Interview Tips</h3>
        <ul className="text-sm text-matcha-700 space-y-1">
          <li>• Speak naturally about your company's culture and values</li>
          <li>• Share specific examples of how your team works together</li>
          <li>• Describe what makes someone successful at your company</li>
          <li>• The AI will ask follow-up questions to understand better</li>
        </ul>
      </div>
    </div>
  );
}
