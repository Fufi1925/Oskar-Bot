import { HoneypotLiveStats } from "@/components/honeypot-live-stats";

export const metadata = { title: "Honeypot Live Statistics · CloudTIX", description: "Real-time Honeypot moderation and server statistics from CloudTIX." };

export default function Page() {
  return <HoneypotLiveStats />;
}
