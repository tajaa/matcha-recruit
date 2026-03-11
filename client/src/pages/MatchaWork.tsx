import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function MatchaWork() {
  const navigate = useNavigate();

  useEffect(() => {
    navigate('/app/matcha/work/chats', { replace: true });
  }, [navigate]);

  return null;
}
