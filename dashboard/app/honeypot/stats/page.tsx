import { HoneypotLiveStats } from "@/components/honeypot-live-stats";

export const metadata = { title: "Honeypot Live Statistics · University Bot", description: "Real-time Honeypot moderation and server statistics from University Bot." };

export default function Page() {
  return <HoneypotLiveStats />;
}
