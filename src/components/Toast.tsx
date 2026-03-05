import { useEffect } from 'react';

export function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 2000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 animate-slide-in-up px-4">
      <div className="glass-light px-5 py-3 rounded-full text-sm font-medium shadow-2xl whitespace-nowrap" style={{ background: 'var(--toast-bg)', color: 'var(--toast-text)' }}>
        {message}
      </div>
    </div>
  );
}
