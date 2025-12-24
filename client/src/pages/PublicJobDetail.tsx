import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

export function PublicJobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  // Redirect to registration page with return URL
  useEffect(() => {
    navigate(`/register?returnTo=/careers/${jobId}/apply`, { replace: true });
  }, [jobId, navigate]);

  // Show loading spinner while redirecting
  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
      <div className="w-6 h-6 border-2 border-matcha-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}
