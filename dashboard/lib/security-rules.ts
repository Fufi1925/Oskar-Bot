/** Shared AutoMod editing logic. Filters never modify the complete draft. */
export function filterRules(rules: any[], draft: Record<string, any>, query: string, filter: string, translate: (text: string) => string = text => text) {
  const search = query.trim().toLocaleLowerCase();
  return rules.filter(rule => {
    const enabled = draft[rule.key]?.enabled ?? rule.enabled;
    return `${rule.label} ${rule.description} ${translate(rule.label)} ${translate(rule.description)}`.toLocaleLowerCase().includes(search)
      && (filter === "all" || (filter === "enabled" ? enabled : !enabled));
  });
}

export function ruleDefaults(rule: any) {
  return {
    threshold: rule.defaults.threshold,
    duration: rule.defaults.duration,
    punishment: rule.defaults.punishment,
    ...(rule.has_window ? { window: rule.defaults.window || 10 } : {}),
  };
}

export function validateRules(rules: any[], draft: Record<string, any>): boolean {
  return rules.some(rule => {
    const patch = draft[rule.key];
    if (!patch) return false;
    const bounds: Record<string, number[]> = {
      threshold: [rule.threshold_min, rule.threshold_max], duration: [1, 10080], window: [2, 120],
    };
    return Object.entries(bounds).some(([field, [min, max]]) => patch[field] !== undefined
      && (!Number.isInteger(patch[field]) || patch[field] < min || patch[field] > max));
  });
}
