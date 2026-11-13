import { Component, type ReactNode } from 'react'

/** Keep a recoverable screen if an open tab outlives a deployed route chunk. */
export class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="mx-auto flex min-h-screen max-w-lg items-center p-5">
        <section className="card space-y-4 p-6">
          <p className="text-sm font-bold text-brand">ShelfLoop</p>
          <h1 className="text-xl font-bold">Let’s reload your workspace.</h1>
          <p className="text-sm text-ink/70">This screen could not load. Check your connection and reload. Saved capture drafts and queued changes stay on this device.</p>
          <p className="text-sm text-ink/70" lang="hi">यह स्क्रीन लोड नहीं हो सकी। कनेक्शन जाँचें और फिर खोलें। सहेजे गए ड्राफ़्ट इसी डिवाइस पर रहेंगे।</p>
          <button className="btn-primary" type="button" onClick={() => window.location.reload()}>Reload · फिर खोलें</button>
        </section>
      </main>
    )
  }
}
