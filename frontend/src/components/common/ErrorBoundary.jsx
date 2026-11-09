import React from "react";
import { reportError } from "@/lib/errorReporter";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    reportError(`Render:${error?.name || "Error"}`, error?.message, `${error?.stack || ""}\n${info?.componentStack || ""}`);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center" data-testid="app-error-fallback">
        <h1 className="text-2xl font-bold">Something went wrong</h1>
        <p className="text-sm opacity-70">The problem has been reported. Please reload the page.</p>
        <button type="button" onClick={() => window.location.reload()} className="rounded-full bg-black px-5 py-2 text-sm text-white" data-testid="app-error-reload">Reload</button>
      </div>
    );
  }
}
