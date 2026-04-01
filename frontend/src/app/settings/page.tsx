"use client";

import KnowledgePanel from "@/components/KnowledgePanel";

export default function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto px-6 py-10 space-y-10">
      <div>
        <h1 className="text-xl font-bold text-foreground mb-1">Settings</h1>
        <p className="text-sm text-foreground/40">
          Connect your company data so the AI writes emails with real context.
        </p>
      </div>

      {/* Company Knowledge section */}
      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-foreground/60 mb-1">
            Company Knowledge
          </h2>
          <p className="text-xs text-foreground/40">
            Upload your pitch decks, case studies, and service docs to Google Drive.
            Nester will index them and use the content when writing emails — referencing
            real services, real case studies, and real numbers from your docs.
          </p>
        </div>

        <div className="rounded-xl border border-outline/20 p-1 bg-surface/20">
          <div className="p-4 pb-2 border-b border-outline/10 mb-4">
            <p className="text-xs text-foreground/50 space-y-1">
              <span className="block font-semibold text-foreground/70 mb-2">How to set up:</span>
              <span className="block">1. Create a folder in Google Drive (e.g. "Nester Company Docs")</span>
              <span className="block">2. Upload your pitch deck, case studies, service catalog, pricing</span>
              <span className="block">3. Copy the folder ID from the URL and add to <code className="text-accent-dim">.env</code> as <code className="text-accent-dim">GOOGLE_DRIVE_FOLDER_ID</code></span>
              <span className="block">4. Place your <code className="text-accent-dim">credentials.json</code> at <code className="text-accent-dim">~/.credentials/credentials.json</code></span>
              <span className="block">5. Click "Sync Now" below — a browser window will open to authorize Google Drive</span>
            </p>
          </div>
          <div className="px-1 pb-1">
            <KnowledgePanel />
          </div>
        </div>
      </section>
    </div>
  );
}
