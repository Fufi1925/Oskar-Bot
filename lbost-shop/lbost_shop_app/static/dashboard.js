(() => {
  const root = document.documentElement;
  const sidebar = document.querySelector('[data-ub-sidebar]');
  const overlay = document.querySelector('[data-ub-overlay]');
  const closeSidebar = () => { sidebar?.classList.remove('open'); overlay?.classList.remove('open'); };
  document.querySelector('[data-open-sidebar]')?.addEventListener('click', () => {
    sidebar?.classList.add('open'); overlay?.classList.add('open');
  });
  document.querySelector('[data-close-sidebar]')?.addEventListener('click', closeSidebar);
  overlay?.addEventListener('click', closeSidebar);

  const closePopovers = (except) => document.querySelectorAll('[data-popover].open').forEach((el) => {
    if (el !== except) el.classList.remove('open');
  });
  document.querySelectorAll('[data-popover-button]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const popup = document.querySelector(`[data-popover="${button.dataset.popoverButton}"]`);
      const willOpen = popup && !popup.classList.contains('open');
      closePopovers(popup);
      popup?.classList.toggle('open', Boolean(willOpen));
    });
  });
  document.addEventListener('click', () => closePopovers(null));
  document.querySelectorAll('[data-popover]').forEach((popup) => popup.addEventListener('click', (e) => e.stopPropagation()));

  const search = document.querySelector('[data-global-search]');
  const rows = [...document.querySelectorAll('[data-search-item]')];
  search?.addEventListener('input', () => {
    const term = search.value.trim().toLocaleLowerCase();
    rows.forEach((row) => row.classList.toggle('search-hidden', Boolean(term) && !row.textContent.toLocaleLowerCase().includes(term)));
  });
  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); search?.focus();
    }
  });
  search?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      const first = rows.find((row) => !row.classList.contains('search-hidden'));
      if (first?.href) window.location.href = first.href;
    }
  });

  document.querySelectorAll('[data-page-tab]').forEach((button) => button.addEventListener('click', () => {
    const selected = button.dataset.pageTab;
    document.querySelectorAll('[data-page-tab]').forEach((item) => item.classList.toggle('active', item === button));
    document.querySelectorAll('[data-page-panel]').forEach((panel) => { panel.hidden = panel.dataset.pagePanel !== selected; });
    const url = new URL(window.location.href); url.searchParams.set('tab', selected); history.replaceState(null, '', url);
  }));

  const serverSearch = document.querySelector('[data-server-search]');
  const serverGrid = document.querySelector('[data-server-grid]');
  const serverCards = [...document.querySelectorAll('[data-server-card]')];
  const noResults = document.querySelector('[data-no-server-results]');
  const filterServers = () => {
    const term = (serverSearch?.value || '').trim().toLocaleLowerCase();
    let visible = 0;
    serverCards.forEach((card) => {
      const show = !term || card.dataset.name.includes(term) || card.dataset.id.includes(term);
      card.hidden = !show; if (show) visible += 1;
    });
    noResults?.classList.toggle('open', visible === 0 && Boolean(term));
  };
  serverSearch?.addEventListener('input', filterServers);
  document.querySelectorAll('[data-server-sort]').forEach((button) => button.addEventListener('click', () => {
    const mode = button.dataset.serverSort;
    document.querySelectorAll('[data-server-sort]').forEach((item) => item.classList.toggle('active', item === button));
    serverCards.sort((a, b) => mode === 'name'
      ? a.dataset.name.localeCompare(b.dataset.name, 'de')
      : Number(b.dataset.members) - Number(a.dataset.members));
    serverCards.forEach((card) => serverGrid?.appendChild(card));
  }));


  // ── Ticket-Vorschau: tippen ohne Speichern, gerechnet im Bot ──
  const vorschauFormular = document.querySelector('[data-preview-url]');
  if (vorschauFormular) {
    const vorschauUrl = vorschauFormular.dataset.previewUrl;
    const status = document.querySelector('[data-preview-state]');
    let vorschauTimer = null;

    const feldwerte = () => {
      const daten = {};
      vorschauFormular.querySelectorAll('[data-preview-field]').forEach((feld) => {
        const name = feld.dataset.previewField;
        if (feld.type === 'checkbox') { daten[name] = feld.checked; return; }
        if (name.endsWith('_json')) {
          if (!feld.value.trim()) { daten[name] = []; return; }
          try { daten[name] = JSON.parse(feld.value); } catch (fehler) { /* unvollstaendiges JSON: letzter Stand bleibt stehen */ }
          return;
        }
        daten[name] = feld.value;
      });
      return daten;
    };

    const schreiben = (name, wert) => {
      const feld = document.querySelector('[data-preview="' + name + '"]');
      if (feld) feld.textContent = wert === null || wert === undefined ? '' : String(wert);
    };

    const fragenZeigen = (fragen) => {
      const feld = document.querySelector('[data-preview="fragen"]');
      if (!feld) return;
      feld.textContent = '';
      if (!fragen || fragen.length === 0) {
        const leer = document.createElement('em');
        leer.textContent = 'Keine Fragen gestellt.';
        feld.appendChild(leer);
        return;
      }
      fragen.forEach((frage, index) => {
        if (index) feld.appendChild(document.createElement('br'));
        const kopf = document.createElement('b');
        kopf.textContent = (index + 1) + '. ' + frage.label + (frage.pflicht ? ' · Pflicht' : '');
        feld.appendChild(kopf);
        feld.appendChild(document.createTextNode(frage.hinweis || frage.feld));
      });
    };

    const merken = (text, online) => {
      if (!status) return;
      status.className = 'ub-status-pill ' + (online ? 'online' : 'offline');
      status.textContent = text;
    };

    const vorschauLaden = async () => {
      merken('rechne\u2026', true);
      try {
        const antwort = await fetch(vorschauUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(feldwerte()),
        });
        if (!antwort.ok) throw new Error('HTTP ' + antwort.status);
        const daten = await antwort.json();
        if (daten.fehler) throw new Error(daten.fehler);
        schreiben('titel', daten.titel);
        schreiben('nachricht', daten.nachricht);
        schreiben('bestaetigung', daten.bestaetigung);
        fragenZeigen(daten.fragen);
        const kanal = document.querySelector('[data-preview-kanal]');
        if (kanal) kanal.textContent = '#' + daten.kanal;
        if (daten.unbekannte_felder && daten.unbekannte_felder.length) {
          merken('Feld unbekannt: ' + daten.unbekannte_felder.join(', '), false);
        } else {
          merken('Entwurf, gerechnet im Bot', true);
        }
      } catch (fehler) {
        merken('Vorschau nicht verf\u00fcgbar', false);
      }
    };

    const planen = (verzoegerung) => {
      clearTimeout(vorschauTimer);
      vorschauTimer = setTimeout(vorschauLaden, verzoegerung);
    };

    vorschauFormular.addEventListener('input', () => planen(500));
    vorschauFormular.addEventListener('change', () => planen(150));
  }

  // JSON-Felder: Tab rueckt ein, statt zum naechsten Feld zu springen
  document.querySelectorAll('textarea[spellcheck="false"]').forEach((feld) => {
    feld.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab') return;
      event.preventDefault();
      feld.setRangeText('  ', feld.selectionStart, feld.selectionEnd, 'end');
      feld.dispatchEvent(new Event('input', { bubbles: true }));
    });
  });
  root.classList.add('dashboard-js');
})();
