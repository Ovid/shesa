interface HelpPanelProps {
  onClose: () => void
}

export default function HelpPanel({ onClose }: HelpPanelProps) {
  return (
    <div className="fixed inset-y-0 right-0 w-[400px] bg-surface-1 border-l border-border shadow-2xl z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary">Help</h2>
        <button onClick={onClose} className="text-text-dim hover:text-text-secondary text-lg">&times;</button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-6 text-sm">
        {/* Quick Start */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">Quick Start</h3>
          <ol className="list-decimal list-inside space-y-1 text-text-secondary">
            <li>Create a topic using the <strong>+</strong> button in the sidebar</li>
            <li>Click the <strong>Search</strong> icon to find papers on arXiv</li>
            <li>Select papers and click <strong>Add</strong> to add them to your topic</li>
            <li>Ask questions about your papers in the chat area</li>
            <li>Click <strong>View trace</strong> on any answer to see how the LLM arrived at it</li>
          </ol>
        </section>

        {/* FAQ */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">FAQ</h3>
          <div className="space-y-3">
            <div>
              <p className="text-text-primary font-medium">How do I add papers to multiple topics?</p>
              <p className="text-text-dim">Use the search panel's topic picker when adding papers. Each paper can belong to multiple topics.</p>
            </div>
            <div>
              <p className="text-text-primary font-medium">What does the context budget indicator mean?</p>
              <p className="text-text-dim">It estimates how much of the model's context window is used by your documents and conversation history. Green (&lt;50%), amber (&lt;80%), red (&ge;80%).</p>
            </div>
            <div>
              <p className="text-text-primary font-medium">Why do queries take so long?</p>
              <p className="text-text-dim">Shesha uses a recursive approach: the LLM writes code to explore your documents, runs it, examines the output, and repeats. This takes multiple iterations.</p>
            </div>
            <div>
              <p className="text-text-primary font-medium">Can I cancel a running query?</p>
              <p className="text-text-dim">Yes, press Escape or click the cancel button while a query is running.</p>
            </div>
            <div>
              <p className="text-text-primary font-medium">What is the citation check?</p>
              <p className="text-text-dim">It verifies that claims in the LLM's answer are supported by the source documents. Results show which citations are verified, unverified, or missing.</p>
            </div>
            <div>
              <p className="text-text-primary font-medium">How do I export my conversation?</p>
              <p className="text-text-dim">Click the export button in the header to download a Markdown transcript of the current topic's conversation.</p>
            </div>
          </div>
        </section>

        {/* Keyboard Shortcuts */}
        <section>
          <h3 className="font-semibold text-text-primary mb-2">Keyboard Shortcuts</h3>
          <div className="space-y-1 text-text-secondary">
            <div className="flex justify-between">
              <span>Send message</span>
              <kbd className="bg-surface-2 border border-border px-1.5 rounded text-xs font-mono">Enter</kbd>
            </div>
            <div className="flex justify-between">
              <span>New line in input</span>
              <kbd className="bg-surface-2 border border-border px-1.5 rounded text-xs font-mono">Shift+Enter</kbd>
            </div>
            <div className="flex justify-between">
              <span>Cancel query</span>
              <kbd className="bg-surface-2 border border-border px-1.5 rounded text-xs font-mono">Escape</kbd>
            </div>
          </div>
        </section>

        {/* Experimental notice */}
        <section className="bg-amber/5 border border-amber/20 rounded p-3 text-xs text-amber">
          This is experimental software. Features may change or break. Please report issues.
        </section>
      </div>
    </div>
  )
}
