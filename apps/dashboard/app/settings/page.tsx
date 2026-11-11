import { ProviderSettings } from "@/components/provider-settings";

export const metadata = { title: "Settings · Shahid Workforce" };

export default function SettingsPage() {
  return (
    <section>
      <h1>Settings</h1>
      <p className="muted">
        Provider API keys are stored server-side in the database, returned
        only as a masked prefix, and never written to Git. Environment
        variables override saved keys.
      </p>
      <div className="panel">
        <ProviderSettings />
      </div>
    </section>
  );
}
