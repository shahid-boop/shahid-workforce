import { AgentDirectory } from "@/components/agent-directory";

export const metadata = { title: "Agents · Shahid Workforce" };

export default function AgentsPage() {
  return (
    <section>
      <h1>Agents</h1>
      <p className="muted">
        The specialist roster loaded from the agent registry. Prompt text stays
        server-side and is never sent to the browser.
      </p>
      <div className="panel">
        <AgentDirectory />
      </div>
    </section>
  );
}
