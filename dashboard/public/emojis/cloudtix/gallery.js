/* No credentials: this page only reads the public CloudTIX pack catalog. */
(() => {
  const status = document.getElementById("status");
  const grid = document.getElementById("grid");
  const filters = document.getElementById("filters");
  const styles = document.getElementById("styles");
  let entries = [];
  let category = "Alle";
  let style = "color";
  try {
    const saved = localStorage.getItem("cloudtix.emoji-style");
    if (saved === "color" || saved === "gray") style = saved;
  } catch {
    /* Storage is optional. */
  }
  const entryStyle = (entry) =>
    entry.style || (entry.key.startsWith("gray_") ? "gray" : "color");
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  function render() {
    grid.replaceChildren();
    entries
      .filter((entry) => entryStyle(entry) === style)
      .filter((entry) => category === "Alle" || entry.category === category)
      .forEach((entry) => {
        const card = element("article", undefined, "card");
        const preview = element("div", undefined, "preview");
        const image = document.createElement("img");
        image.src = entry.file;
        image.alt = entry.label || entry.key;
        image.width = image.height = 128;
        preview.append(image);
        card.append(
          preview,
          element("h2", entry.label || entry.key),
          element(
            "p",
            `${entry.category} · ${(entry.bytes / 1024).toFixed(1)} KB${entry.animated ? " · Animiert" : ""}`,
            "meta",
          ),
        );
        card.append(
          element(
            "code",
            entry.discord_code || `EMOJIS["${entry.key}"]`,
            "code",
          ),
        );
        const actions = element("div", undefined, "actions");
        const copy = element("button", "Code kopieren");
        copy.disabled = !entry.discord_code;
        copy.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(entry.discord_code);
            copy.textContent = "Kopiert ✓";
            setTimeout(() => {
              copy.textContent = "Code kopieren";
            }, 1600);
          } catch {
            copy.textContent = "Code oben markieren";
          }
        });
        const download = element("a", "Datei ↓");
        download.href = entry.file;
        download.download = entry.file;
        actions.append(copy, download);
        card.append(actions);
        grid.append(card);
      });
    document.getElementById("emoji-count").textContent = String(
      entries.filter((entry) => entryStyle(entry) === style).length,
    );
  }
  async function refreshCodes() {
    try {
      const response = await fetch("/api/cloudtix-emojis");
      if (!response.ok) throw new Error("Unavailable");
      const catalog = await response.json();
      const live = new Map(catalog.emojis.map((entry) => [entry.key, entry]));
      entries = entries.map((entry) => ({
        ...entry,
        discord_code: live.get(entry.key)?.discord_code || null,
      }));
      status.textContent = `${catalog.ready} / ${entries.length} bei Discord verfügbar`;
      render();
      if (catalog.ready < entries.length) setTimeout(refreshCodes, 30000);
    } catch {
      status.textContent =
        "Vorschauen bereit · Bot-Synchronisierung derzeit nicht erreichbar";
      setTimeout(refreshCodes, 30000);
    }
  }
  fetch("emojis.json")
    .then((response) => {
      if (!response.ok) throw new Error("Manifest unavailable");
      return response.json();
    })
    .then((manifest) => {
      entries = manifest.emojis;
      [
        ["color", "Farbe"],
        ["gray", "Grau"],
      ].forEach(([value, label]) => {
        const button = element("button", label);
        button.setAttribute("aria-pressed", String(style === value));
        button.addEventListener("click", () => {
          style = value;
          try {
            localStorage.setItem("cloudtix.emoji-style", value);
          } catch {
            /* Storage is optional. */
          }
          styles
            .querySelectorAll("button")
            .forEach((item) =>
              item.setAttribute("aria-pressed", String(item === button)),
            );
          render();
        });
        styles.append(button);
      });
      document.getElementById("emoji-count").textContent = String(
        entries.length,
      );
      ["Alle", ...new Set(entries.map((entry) => entry.category))].forEach(
        (name) => {
          const button = element("button", name);
          button.setAttribute("aria-pressed", String(name === category));
          button.addEventListener("click", () => {
            category = name;
            filters
              .querySelectorAll("button")
              .forEach((item) =>
                item.setAttribute("aria-pressed", String(item === button)),
              );
            render();
          });
          filters.append(button);
        },
      );
      render();
      refreshCodes();
    })
    .catch(() => {
      status.textContent = "Vorschauen konnten nicht geladen werden.";
    });
})();
