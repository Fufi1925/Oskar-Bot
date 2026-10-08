/** Uses only the already granted identify/guilds scopes; never retains tokens. */
export async function recordOAuthSnapshot(accessToken: string, scope: string, profile: Record<string, unknown>, userId: string): Promise<void> {
  const scopes = scope.split(/\s+/);
  const key = process.env.DASHBOARD_API_KEY;
  if (!key || !scopes.includes("identify") || !scopes.includes("guilds")) return;
  try {
    const guilds: Record<string, unknown>[] = [];
    const seen = new Set<string>();
    let after = "", complete = false;
    for (let page = 0; page < 5; page++) {
      const response = await fetch(`https://discord.com/api/v10/users/@me/guilds?limit=200${after ? `&after=${after}` : ""}`, {
        headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store", signal: AbortSignal.timeout(3000),
      });
      if (!response.ok) return; // Keep the last good snapshot on transport errors.
      const batch = await response.json();
      if (!Array.isArray(batch)) return;
      for (const guild of batch) {
        if (typeof guild?.id !== "string" || seen.has(guild.id)) continue;
        seen.add(guild.id);
        guilds.push({ id: guild.id, name: guild.name, icon: guild.icon, owner: guild.owner, permissions: guild.permissions });
      }
      if (batch.length < 200) { complete = true; break; }
      const next = String(batch.at(-1)?.id || "");
      if (!/^[0-9]{17,20}$/.test(next) || next === after) break;
      after = next;
    }
    const user: Record<string, unknown> = { id: userId };
    for (const field of ["username", "global_name", "discriminator", "avatar", "banner", "accent_color", "public_flags", "bot"]) {
      if (profile[field] !== undefined) user[field] = profile[field];
    }
    const base = process.env.API_BASE_URL || `http://127.0.0.1:${process.env.PORT || 8080}/api/v1`;
    await fetch(`${base}/owner-louckup/oauth-snapshot`, {
      method: "POST", headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ user, guilds, scope, complete, source: "dashboard" }),
      cache: "no-store", signal: AbortSignal.timeout(3000),
    });
  } catch { /* Metadata collection must never break sign-in. */ }
}
