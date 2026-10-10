/** Largest communities first; unknown counts follow known counts. */
export function compareGuildMembers(
  a: { id: string; name: string; memberCount: number | null },
  b: { id: string; name: string; memberCount: number | null },
) {
  const count = (value: number | null) =>
    typeof value === "number" && Number.isFinite(value) && value >= 0
      ? value
      : -1;
  return (
    count(b.memberCount) - count(a.memberCount) ||
    a.name.localeCompare(b.name, "de") ||
    a.id.localeCompare(b.id)
  );
}
