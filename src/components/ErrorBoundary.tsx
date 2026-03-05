import { Component } from 'react';
import type { ReactNode, ErrorInfo } from 'react';
import { RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-[100dvh] flex items-center justify-center" style={{ background: 'var(--bg-error)' }}>
          <div className="text-center px-6 max-w-md">
            <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4" style={{ background: 'rgba(239, 68, 68, 0.1)' }}>
              <span className="text-3xl" style={{ color: '#ef4444' }}>!</span>
            </div>
            <h2 className="text-lg font-bold mb-2" style={{ color: 'var(--text-primary)' }}>Something went wrong</h2>
            <p className="text-sm mb-6" style={{ color: 'var(--text-quaternary)' }}>
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full transition-all"
              style={{ background: 'var(--action-bg)', color: 'var(--text-primary)' }}
            >
              <RefreshCw className="w-4 h-4" />
              Reload App
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
