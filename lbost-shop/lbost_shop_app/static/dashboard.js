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
  // ── Logs: derselbe Entwurfsablauf und dieselben eigenen Picker wie im University-Panel ──
  const loggingForm = document.querySelector('[data-logging-form]');
  if (loggingForm) {
    const modal = document.querySelector('[data-picker-modal]');
    const results = modal?.querySelector('[data-picker-results]');
    const searchInput = modal?.querySelector('[data-picker-search]');
    const pickerTitle = modal?.querySelector('[data-picker-title]');
    const pickerFooter = modal?.querySelector('[data-picker-footer]');
    const pickerCount = modal?.querySelector('[data-picker-selection-count]');
    let pickerButton = null;
    let pickerChoices = new Set();

    const sourceItems = (kind) => [...document.querySelectorAll(`[data-picker-source="${kind}"] > button`)];
    const sourceName = (kind, id) => sourceItems(kind).find((item) => item.dataset.id === id)?.dataset.name || id;
    const targetValues = (button) => {
      const target = document.getElementById(button.dataset.pickerTarget);
      if (!target) return [];
      return button.hasAttribute('data-picker-multiple')
        ? [...target.querySelectorAll('input')].map((input) => input.value)
        : [target.value].filter(Boolean);
    };
    const pickerKindTitle = { channels: 'Kanal auswählen', roles: 'Rollen auswählen', members: 'Mitglied auswählen' };

    const renderPickerResults = () => {
      if (!pickerButton || !results) return;
      const term = (searchInput?.value || '').trim().toLocaleLowerCase('de');
      const kind = pickerButton.dataset.pickerKind;
      results.textContent = '';
      let shown = 0;
      if (!pickerButton.hasAttribute('data-picker-multiple') && targetValues(pickerButton).length) {
        const clear = document.createElement('button'); clear.type = 'button'; clear.className = 'ub-picker-clear';
        clear.textContent = 'Auswahl entfernen';
        clear.addEventListener('click', () => {
          const target = document.getElementById(pickerButton.dataset.pickerTarget);
          if (target) { target.value = ''; target.dispatchEvent(new Event('change', { bubbles: true })); }
          updatePickerButtons(pickerButton.dataset.pickerTarget, kind); closePicker();
        });
        results.appendChild(clear); shown += 1;
      }
      sourceItems(kind).forEach((source) => {
        if (term && !source.textContent.toLocaleLowerCase('de').includes(term)) return;
        const option = source.cloneNode(true);
        option.classList.toggle('selected', pickerChoices.has(source.dataset.id));
        option.addEventListener('click', () => {
          if (pickerButton.hasAttribute('data-picker-multiple')) {
            if (pickerChoices.has(source.dataset.id)) pickerChoices.delete(source.dataset.id);
            else pickerChoices.add(source.dataset.id);
            setMultipleValues(pickerButton, [...pickerChoices]);
            renderPickerResults();
            return;
          }
          const target = document.getElementById(pickerButton.dataset.pickerTarget);
          if (target) {
            target.value = source.dataset.id;
            target.dispatchEvent(new Event('change', { bubbles: true }));
          }
          if (pickerButton.hasAttribute('data-picker-external-search')) pickerButton.value = source.dataset.name;
          updatePickerButtons(pickerButton.dataset.pickerTarget, kind);
          closePicker();
        });
        results.appendChild(option);
        shown += 1;
      });
      if (kind === 'members' && /^\d{15,20}$/.test((searchInput?.value || '').trim()) &&
          !sourceItems(kind).some((item) => item.dataset.id === searchInput.value.trim())) {
        const rawId = searchInput.value.trim();
        const option = document.createElement('button'); option.type = 'button'; option.className = 'ub-picker-raw-id';
        const avatar = document.createElement('span'); avatar.className = 'ub-picker-avatar'; avatar.textContent = '#';
        const copy = document.createElement('span');
        const title = document.createElement('strong'); title.textContent = 'Discord-ID verwenden';
        const detail = document.createElement('small'); detail.textContent = rawId;
        copy.append(title, detail); option.append(avatar, copy);
        option.addEventListener('click', () => {
          const target = document.getElementById(pickerButton.dataset.pickerTarget);
          if (target) { target.value = rawId; target.dispatchEvent(new Event('change', { bubbles: true })); }
          if (pickerButton.hasAttribute('data-picker-external-search')) pickerButton.value = rawId;
          updatePickerButtons(pickerButton.dataset.pickerTarget, kind); closePicker();
        });
        results.appendChild(option); shown += 1;
      }
      modal?.querySelector('[data-picker-empty]')?.toggleAttribute('hidden', shown !== 0);
      if (pickerCount) pickerCount.textContent = `${pickerChoices.size} ausgewählt`;
    };

    const openPicker = (button) => {
      pickerButton = button;
      pickerChoices = new Set(targetValues(button));
      if (pickerTitle) pickerTitle.textContent = pickerKindTitle[button.dataset.pickerKind] || 'Auswählen';
      if (pickerFooter) pickerFooter.hidden = true;
      const externalSearch = button.hasAttribute('data-picker-external-search');
      if (searchInput) searchInput.value = externalSearch ? button.value : '';
      modal.querySelector('.ub-picker-search')?.toggleAttribute('hidden', externalSearch);
      modal.hidden = false;
      modal.setAttribute('aria-hidden', 'false');
      const panel = modal.querySelector('section');
      const rect = button.getBoundingClientRect();
      const width = Math.max(280, rect.width);
      const left = Math.min(Math.max(8, rect.left), window.innerWidth - width - 8);
      const roomBelow = window.innerHeight - rect.bottom - 10;
      const openAbove = roomBelow < 260 && rect.top > roomBelow;
      panel.style.width = `${Math.min(width, window.innerWidth - 16)}px`;
      panel.style.left = `${left}px`;
      panel.style.top = openAbove ? 'auto' : `${rect.bottom + 6}px`;
      panel.style.bottom = openAbove ? `${window.innerHeight - rect.top + 6}px` : 'auto';
      panel.style.maxHeight = `${Math.max(180, openAbove ? rect.top - 16 : roomBelow)}px`;
      renderPickerResults();
      if (!externalSearch) window.setTimeout(() => searchInput?.focus(), 30);
    };
    const closePicker = () => {
      if (!modal) return;
      modal.hidden = true;
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('ub-picker-open');
      pickerButton = null;
    };
    const updatePickerButtons = (targetId, kind) => {
      const target = document.getElementById(targetId);
      document.querySelectorAll(`[data-picker-target="${targetId}"]`).forEach((button) => {
        const label = button.querySelector('[data-picker-label]');
        if (!label || !target) return;
        if (button.hasAttribute('data-picker-multiple')) {
          const values = [...target.querySelectorAll('input')].map((input) => input.value);
          label.textContent = values.length ? `${values.length} ausgewählt` : button.dataset.pickerPlaceholder;
        } else {
          label.textContent = target.value ? sourceName(kind, target.value) : button.dataset.pickerPlaceholder;
          const inlineClear = button.querySelector('[data-picker-inline-clear]');
          if (inlineClear) inlineClear.hidden = !target.value;
        }
      });
      renderMultiChips(targetId, kind);
    };
    const setMultipleValues = (button, values) => {
      const target = document.getElementById(button.dataset.pickerTarget);
      if (!target) return;
      const fieldName = button.dataset.pickerKind === 'roles' ? 'ignore_roles' : 'ignore_channels';
      target.textContent = '';
      values.forEach((value) => {
        const input = document.createElement('input');
        input.type = 'hidden'; input.name = fieldName; input.value = value;
        target.appendChild(input);
      });
      target.dispatchEvent(new Event('change', { bubbles: true }));
      updatePickerButtons(target.id, button.dataset.pickerKind);
      updateSummary();
    };
    const renderMultiChips = (targetId, kind) => {
      const holder = document.querySelector(`[data-picker-chips="${targetId}"]`);
      const target = document.getElementById(targetId);
      if (!holder || !target) return;
      holder.textContent = '';
      [...target.querySelectorAll('input')].forEach((input) => {
        const chip = document.createElement('span');
        chip.appendChild(document.createTextNode(sourceName(kind, input.value)));
        const remove = document.createElement('button');
        remove.type = 'button'; remove.title = 'Entfernen'; remove.textContent = '×';
        remove.addEventListener('click', () => {
          input.remove();
          target.dispatchEvent(new Event('change', { bubbles: true }));
          updatePickerButtons(targetId, kind);
          updateSummary();
        });
        chip.appendChild(remove); holder.appendChild(chip);
      });
    };

    document.querySelectorAll('[data-picker-inline-clear]').forEach((clear) => clear.addEventListener('click', (event) => {
      event.preventDefault(); event.stopPropagation();
      const button = clear.closest('[data-picker-open]');
      const target = document.getElementById(button.dataset.pickerTarget);
      if (target) { target.value = ''; target.dispatchEvent(new Event('change', { bubbles: true })); }
      updatePickerButtons(button.dataset.pickerTarget, button.dataset.pickerKind);
    }));
    document.querySelectorAll('[data-picker-open]').forEach((button) => {
      button.addEventListener('click', () => openPicker(button));
      if (button.hasAttribute('data-picker-external-search')) {
        button.addEventListener('focus', () => openPicker(button));
        button.addEventListener('input', () => {
          if (pickerButton !== button) openPicker(button);
          if (searchInput) searchInput.value = button.value;
          renderPickerResults();
        });
      }
    });
    modal?.querySelectorAll('[data-picker-close], [data-picker-cancel]').forEach((button) => button.addEventListener('click', closePicker));
    modal?.querySelector('[data-picker-apply]')?.addEventListener('click', () => {
      if (pickerButton) setMultipleValues(pickerButton, [...pickerChoices]);
      closePicker();
    });
    searchInput?.addEventListener('input', renderPickerResults);
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && modal && !modal.hidden) closePicker(); });

    const configFields = () => [...loggingForm.querySelectorAll('input[name]')].filter((input) =>
      !['csrf', 'action', 'all_channel'].includes(input.name)
    );
    const fieldState = () => {
      const state = {};
      configFields().forEach((input) => {
        if (input.type === 'checkbox' && !input.checked) return;
        (state[input.name] ||= []).push(input.value);
      });
      Object.keys(state).forEach((key) => state[key].sort());
      return state;
    };
    const initialState = JSON.stringify(fieldState());
    const saveBar = loggingForm.querySelector('[data-log-save-bar]');
    const dirtyCount = loggingForm.querySelector('[data-log-dirty-count]');
    let currentDirty = 0;

    const updateCategory = (row) => {
      const enabled = row.querySelector('input[type="checkbox"]').checked;
      const channelInput = row.querySelector('input[name^="channel_"]');
      const channel = channelInput?.value || '';
      const channelOption = sourceItems('channels').find((item) => item.dataset.id === channel);
      const known = !channel || Boolean(channelOption);
      const canPost = !channelOption || channelOption.dataset.canPost !== 'false';
      const broken = enabled && (!channel || !known || !canPost);
      row.classList.toggle('active', enabled && channel && known && canPost);
      row.classList.toggle('broken', broken);
      row.querySelector('.ub-log-category-controls')?.toggleAttribute('hidden', !enabled);
      const error = row.querySelector('[data-category-error]');
      if (error) {
        error.hidden = !broken;
        if (broken) {
          error.lastChild.textContent = channel && !known
            ? 'Diesen Kanal gibt es nicht mehr.'
            : channel && !canPost
              ? 'Der Bot darf dort nicht schreiben.'
              : 'Kein Kanal gewählt — hier landet nichts.';
        }
      }
      const test = row.querySelector('.ub-log-test');
      const hint = row.querySelector('.ub-log-test-hint');
      const saved = channel && channel === row.dataset.savedChannel && known && canPost;
      if (test) test.hidden = !enabled || !saved;
      if (hint) hint.hidden = !enabled || !channel || saved;
    };
    const updateSummary = () => {
      const rows = [...loggingForm.querySelectorAll('[data-log-category]')];
      rows.forEach(updateCategory);
      const active = rows.filter((row) => {
        const enabled = row.querySelector('input[type="checkbox"]').checked;
        const channel = row.querySelector('input[name^="channel_"]')?.value;
        return enabled && Boolean(channel);
      }).length;
      const broken = rows.filter((row) => row.classList.contains('broken'));
      const activeNode = loggingForm.querySelector('[data-log-active]');
      const brokenNode = loggingForm.querySelector('[data-log-broken]');
      if (activeNode) activeNode.textContent = active;
      if (brokenNode) brokenNode.textContent = broken.length;
      const problemStat = loggingForm.querySelector('[data-log-problem-stat]');
      problemStat?.classList.toggle('danger', broken.length > 0);
      const problemLabel = loggingForm.querySelector('[data-log-problem-label]');
      if (problemLabel) problemLabel.textContent = broken.length === 1 ? 'Problem' : 'Probleme';
      const banner = loggingForm.querySelector('[data-log-broken-banner]');
      banner?.classList.toggle('is-hidden', broken.length === 0);
      const names = loggingForm.querySelector('[data-log-broken-names]');
      if (names) names.textContent = broken.map((row) => row.dataset.label).join(', ');
      const copy = loggingForm.querySelector('[data-log-broken-copy]');
      if (copy) copy.textContent = `${broken.length === 1 ? 'ist an' : 'sind an'}, aber dort landet nichts. Kanal fehlt, wurde gelöscht, oder der Bot darf nicht hineinschreiben.`;
      loggingForm.querySelector('[data-log-all-off]')?.toggleAttribute('hidden', active === 0);
      loggingForm.querySelectorAll('[data-log-group]').forEach((group) => {
        const groupRows = [...group.querySelectorAll('[data-log-category]')];
        const on = groupRows.filter((row) => row.querySelector('input[type="checkbox"]').checked).length;
        group.classList.toggle('active', on > 0);
        const count = group.querySelector('[data-group-active]'); if (count) count.textContent = on;
        const button = group.querySelector('[data-log-group-all]'); if (button) button.textContent = on === groupRows.length ? 'Alle aus' : 'Alle an';
      });
      const exceptionCount = loggingForm.querySelectorAll('#ignore-channels-inputs input, #ignore-roles-inputs input').length +
        (loggingForm.querySelector('#ignore-users')?.value.split(',').filter(Boolean).length || 0);
      const exceptionNode = loggingForm.querySelector('[data-log-exception-count]'); if (exceptionNode) exceptionNode.textContent = exceptionCount;
      const exceptionLabel = loggingForm.querySelector('[data-log-exception-label]');
      if (exceptionLabel) exceptionLabel.textContent = exceptionCount === 0 ? 'Keine Ausnahmen' : `${exceptionCount} ${exceptionCount === 1 ? 'Ausnahme' : 'Ausnahmen'}`;
      const current = fieldState();
      let changes = 0;
      const original = JSON.parse(initialState);
      new Set([...Object.keys(original), ...Object.keys(current)]).forEach((key) => {
        if (JSON.stringify(original[key] || []) !== JSON.stringify(current[key] || [])) changes += 1;
      });
      currentDirty = changes;
      if (dirtyCount) dirtyCount.textContent = changes;
      if (saveBar) {
        saveBar.hidden = changes === 0;
        const copy = saveBar.querySelector('p');
        if (copy) {
          copy.textContent = '';
          const strong = document.createElement('strong'); strong.textContent = changes;
          copy.append(strong, document.createTextNode(` Änderung${changes === 1 ? '' : 'en'} noch nicht gespeichert.`));
        }
      }
    };

    loggingForm.querySelectorAll('[data-log-group-expand]').forEach((button) => button.addEventListener('click', () => {
      const group = button.closest('[data-log-group]');
      const details = group.querySelector('.ub-log-group-details');
      const opening = details.hidden;
      loggingForm.querySelectorAll('.ub-log-group-details').forEach((item) => { item.hidden = true; item.closest('[data-log-group]')?.classList.remove('open'); });
      details.hidden = !opening; group.classList.toggle('open', opening);
    }));
    loggingForm.querySelectorAll('[data-log-group-all]').forEach((button) => button.addEventListener('click', () => {
      const group = button.closest('[data-log-group]');
      const boxes = [...group.querySelectorAll('[data-log-category] input[type="checkbox"]')];
      const turnOn = boxes.some((box) => !box.checked);
      boxes.forEach((box) => { box.checked = turnOn; }); updateSummary();
    }));
    loggingForm.querySelector('[data-log-all-off]')?.addEventListener('click', () => {
      loggingForm.querySelectorAll('[data-log-category] input[type="checkbox"]').forEach((box) => { box.checked = false; }); updateSummary();
    });
    loggingForm.querySelectorAll('[data-log-category] input').forEach((input) => input.addEventListener('change', updateSummary));

    const presetKeys = {
      essential: ['member_moderation', 'join_leave_events', 'system_events'],
      usual: ['member_moderation', 'join_leave_events', 'system_events', 'message_events', 'channel_events', 'role_events', 'voice_events'],
      everything: [...loggingForm.querySelectorAll('[data-log-category]')].map((row) => row.dataset.key),
    };
    const allChannel = loggingForm.querySelector('#log-all-channel');
    allChannel?.addEventListener('change', () => loggingForm.querySelectorAll('[data-log-preset]').forEach((button) => { button.disabled = !allChannel.value; }));
    loggingForm.querySelectorAll('[data-log-preset]').forEach((button) => button.addEventListener('click', async () => {
      if (!allChannel?.value) return;
      if (button.dataset.logPreset === 'everything') {
        const body = new FormData();
        body.set('csrf', loggingForm.querySelector('input[name="csrf"]').value);
        body.set('action', 'everything'); body.set('all_channel', allChannel.value);
        button.disabled = true;
        try {
          const response = await fetch(window.location.href, { method: 'POST', body });
          if (!response.ok || !response.url.includes('saved=1')) throw new Error('preset failed');
          currentDirty = 0; window.location.href = response.url;
        } catch (error) {
          button.disabled = false; showLogToast('Die Voreinstellung konnte nicht gespeichert werden.', true);
        }
        return;
      }
      const wanted = new Set(presetKeys[button.dataset.logPreset]);
      loggingForm.querySelectorAll('[data-log-category]').forEach((row) => {
        const enabled = wanted.has(row.dataset.key);
        row.querySelector('input[type="checkbox"]').checked = enabled;
        if (enabled) {
          const channel = row.querySelector('input[name^="channel_"]'); channel.value = allChannel.value;
          updatePickerButtons(channel.id, 'channels');
        }
      });
      updateSummary();
    }));

    const exceptionsToggle = loggingForm.querySelector('[data-log-exceptions-toggle]');
    exceptionsToggle?.addEventListener('click', () => {
      const panel = loggingForm.querySelector('[data-log-exceptions]'); panel.hidden = !panel.hidden;
      exceptionsToggle.classList.toggle('open', !panel.hidden);
    });
    const userInput = loggingForm.querySelector('#ignore-users');
    const userCandidate = loggingForm.querySelector('#ignore-user-candidate');
    const addUser = loggingForm.querySelector('[data-log-add-user]');
    userCandidate?.addEventListener('change', () => { if (addUser) addUser.disabled = !userCandidate.value; });
    const renderUserChips = () => {
      const holder = loggingForm.querySelector('[data-user-chips]'); if (!holder || !userInput) return;
      holder.textContent = '';
      userInput.value.split(',').filter(Boolean).forEach((id) => {
        const chip = document.createElement('span'); chip.dataset.id = id;
        chip.appendChild(document.createTextNode(sourceName('members', id)));
        const remove = document.createElement('button'); remove.type = 'button'; remove.title = 'Entfernen'; remove.textContent = '×';
        remove.addEventListener('click', () => {
          userInput.value = userInput.value.split(',').filter((value) => value && value !== id).join(',');
          userInput.dispatchEvent(new Event('change', { bubbles: true })); renderUserChips();
        });
        chip.appendChild(remove); holder.appendChild(chip);
      });
    };
    addUser?.addEventListener('click', () => {
      if (!userCandidate?.value || !userInput) return;
      const users = userInput.value.split(',').filter(Boolean);
      if (!users.includes(userCandidate.value)) users.push(userCandidate.value);
      userInput.value = users.join(','); userInput.dispatchEvent(new Event('change', { bubbles: true }));
      userCandidate.value = '';
      const userSearch = loggingForm.querySelector('[data-user-search]'); if (userSearch) userSearch.value = '';
      addUser.disabled = true; updatePickerButtons('ignore-user-candidate', 'members'); renderUserChips();
    });
    userInput?.addEventListener('change', updateSummary);

    const showLogToast = (message, error = false) => {
      document.querySelector('[data-log-toast]')?.remove();
      const toast = document.createElement('div');
      toast.dataset.logToast = ''; toast.className = `ub-log-toast${error ? ' error' : ''}`; toast.textContent = message;
      document.body.appendChild(toast);
      window.setTimeout(() => toast.remove(), 3500);
    };
    loggingForm.querySelectorAll('[data-log-test-url]').forEach((button) => button.addEventListener('click', async () => {
      const label = button.querySelector('span'); const previous = label?.textContent;
      button.disabled = true; if (label) label.textContent = 'Wird gepostet …';
      try {
        const body = new FormData(); body.set('csrf', loggingForm.querySelector('input[name="csrf"]').value);
        const response = await fetch(button.dataset.logTestUrl, { method: 'POST', body });
        if (!response.ok || !response.url.includes('tested=1')) throw new Error('test failed');
        showLogToast('Der Testeintrag wurde erfolgreich auf Discord gepostet.');
      } catch (error) {
        showLogToast('Der Testeintrag konnte nicht gepostet werden.', true);
      } finally {
        button.disabled = false; if (label) label.textContent = previous;
      }
    }));

    const refuseNavigation = () => {
      if (!saveBar || !currentDirty) return;
      saveBar.classList.remove('shake'); void saveBar.offsetWidth; saveBar.classList.add('shake');
      saveBar.scrollIntoView({ behavior: 'smooth', block: 'center' });
      window.setTimeout(() => saveBar.classList.remove('shake'), 1200);
    };
    window.addEventListener('beforeunload', (event) => {
      if (!currentDirty) return;
      event.preventDefault(); event.returnValue = '';
    });
    document.addEventListener('click', (event) => {
      if (!currentDirty) return;
      const link = event.target.closest?.('a');
      if (!link || !link.href || link.target === '_blank' || link.getAttribute('href')?.startsWith('#')) return;
      if (link.origin !== window.location.origin) return;
      event.preventDefault(); event.stopPropagation(); refuseNavigation();
    }, true);
    loggingForm.addEventListener('submit', () => { currentDirty = 0; });
    loggingForm.querySelector('[data-log-discard]')?.addEventListener('click', () => { currentDirty = 0; window.location.reload(); });
    loggingForm.querySelector('[data-log-reload]')?.addEventListener('click', () => { currentDirty = 0; window.location.reload(); });

    updatePickerButtons('ignore-channels-inputs', 'channels');
    updatePickerButtons('ignore-roles-inputs', 'roles');
    renderUserChips();
    updateSummary();
  }

  // ── Reaktions-Rollen: University form behaviour ──
  const rrRoot = document.querySelector('[data-rr-root]');
  if (rrRoot) {
    const dmForm = rrRoot.querySelector('[data-rr-dm-form]');
    dmForm?.querySelector('input[name="dm_enabled"]')?.addEventListener('change', () => dmForm.submit());
    const addForm = rrRoot.querySelector('[data-rr-add-form]');
    const addButton = rrRoot.querySelector('[data-rr-add]');
    const updateAdd = () => {
      if (!addForm || !addButton) return;
      addButton.disabled = !['channel_id', 'message_id', 'emoji', 'role_id'].every((name) => addForm.querySelector(`[name="${name}"]`)?.value.trim());
    };
    addForm?.querySelectorAll('input').forEach((input) => { input.addEventListener('input', updateAdd); input.addEventListener('change', updateAdd); });
    const emojiInput = rrRoot.querySelector('[data-rr-emoji]');
    rrRoot.querySelectorAll('[data-rr-emoji-value]').forEach((button) => button.addEventListener('click', () => {
      if (emojiInput) { emojiInput.value = button.dataset.rrEmojiValue; emojiInput.dispatchEvent(new Event('input', { bubbles: true })); }
      rrRoot.querySelectorAll('[data-rr-emoji-value]').forEach((item) => item.classList.toggle('selected', item === button));
    }));
    updateAdd();
  }

  // ── Welcome & Leave: two University tabs with one live renderer ──
  const greetRoot = document.querySelector('[data-greet-root]');
  if (greetRoot) {
    const form = greetRoot.querySelector('[data-greet-form]');
    let focused = null;
    const samples = {
      user: '@Neuer', user_name: 'neuer', user_nick: 'Neuer', user_id: '123456789012345678',
      user_avatar: 'https://cdn.discordapp.com/avatar.png', user_createdate: 'Mo, Jan 08, 2024',
      user_joindate: 'heute', server_name: document.querySelector('.eyebrow')?.textContent.split('/')[0].trim() || 'Mein Server',
      server_membercount: '1.204', server_icon: '', timestamp: 'jetzt',
    };
    const fill = (text) => String(text || '').replace(/\{(\w+)\}/g, (all, key) => samples[key.toLowerCase()] ?? all);
    const field = (name) => form?.querySelector(`[name="${name}"]`);
    const update = () => {
      const embed = form?.querySelector('input[name="welcome_type"]:checked')?.value === 'embed';
      const simple = greetRoot.querySelector('[data-greet-simple]');
      const embedPanel = greetRoot.querySelector('[data-greet-embed]');
      if (simple) simple.hidden = embed;
      if (embedPanel) embedPanel.hidden = !embed;
      const title = greetRoot.querySelector('[data-greet-preview-title]');
      const text = greetRoot.querySelector('[data-greet-preview-text]');
      const footer = greetRoot.querySelector('[data-greet-preview-footer]');
      if (title) title.textContent = fill(embed ? field('welcome_embed_title')?.value || 'Willkommen!' : 'Willkommen');
      if (text) text.textContent = fill(embed ? field('welcome_embed_description')?.value : field('welcome_message')?.value);
      if (footer) footer.textContent = fill(embed ? field('welcome_embed_footer_text')?.value : '');
      const leave = greetRoot.querySelector('[data-greet-preview-text-leave]');
      if (leave) leave.textContent = fill(field('leave_message')?.value);
    };
    form?.querySelectorAll('input, textarea').forEach((input) => {
      input.addEventListener('focus', () => { if (!['checkbox', 'radio', 'color', 'number', 'hidden'].includes(input.type)) focused = input; });
      input.addEventListener('input', update); input.addEventListener('change', update);
    });
    greetRoot.querySelectorAll('[data-greet-token]').forEach((button) => button.addEventListener('click', () => {
      if (!focused) return;
      const token = button.dataset.greetToken; const start = focused.selectionStart ?? focused.value.length; const end = focused.selectionEnd ?? start;
      focused.setRangeText(token, start, end, 'end'); focused.dispatchEvent(new Event('input', { bubbles: true })); focused.focus();
    }));
    const templates = {
      short: { type: 'simple', message: 'Willkommen {user} auf **{server_name}**! Du bist Mitglied Nummer {server_membercount}.' },
      image: { type: 'embed', title: 'Willkommen auf {server_name}!', description: 'Schön, dass du da bist, {user}!\n\nDu bist unser {server_membercount}. Mitglied.', footer: 'Beigetreten am {user_joindate}' },
      formal: { type: 'embed', title: 'Neues Mitglied', description: '{user} ist dem Server beigetreten.', footer: 'Mitglied #{server_membercount}' },
    };
    greetRoot.querySelectorAll('[data-greet-template]').forEach((button) => button.addEventListener('click', () => {
      const data = templates[button.dataset.greetTemplate]; if (!data) return;
      const radio = form.querySelector(`input[name="welcome_type"][value="${data.type}"]`); if (radio) radio.checked = true;
      if (data.message !== undefined) field('welcome_message').value = data.message;
      if (data.title !== undefined) field('welcome_embed_title').value = data.title;
      if (data.description !== undefined) field('welcome_embed_description').value = data.description;
      if (data.footer !== undefined) field('welcome_embed_footer_text').value = data.footer;
      update();
    }));
    update();
  }

  root.classList.add('dashboard-js');
})();

// Complete screenshot-accurate giveaway dashboard interactions.
(() => {
  const root = document.querySelector('[data-gw-create]');
  if (root) {
    const form = root.querySelector('[data-gw-form]');
    const replace = (text, values) => { Object.entries(values).forEach(([key,value]) => text = text.split(`{${key}}`).join(value)); return text; };
    const updateSubmit = () => { const button=root.querySelector('[data-gw-submit]'); if(button) button.disabled=!(form?.prize?.value.trim() && form?.channel_id?.value); };
    const preview = () => {
      if (!form) return; const data=new FormData(form), prize=data.get('prize')||'Dein Preis', winners=data.get('winners')||'1', minutes=+(data.get('duration_minutes')||1440);
      const values={prize,winners,entries:'0',ends:minutes>=1440?`in ${Math.round(minutes/1440)} Tag(en)`:minutes>=60?`in ${Math.round(minutes/60)} Stunde(n)`:`in ${minutes} Minuten`,host:'@Host',winners_mentions:'@Alice, @Bob',server:'dein Server'};
      const body=data.get('description')||'**{prize}**\n\nDrücke den Knopf, um teilzunehmen.\n**Gewinner:** {winners}\n**Endet:** {ends}';
      const title=root.querySelector('[data-gw-preview-title]'), output=root.querySelector('[data-gw-preview-body]'), button=root.querySelector('[data-gw-preview-button]');
      if(title) title.textContent=replace(String(data.get('title')||'Gewinnspiel'),values); if(output) output.textContent=replace(String(body),values); if(button) button.textContent=data.get('button_label')||'Teilnehmen';
      root.querySelectorAll('[data-gw-message-preview]').forEach(box=>{const input=box.parentElement.querySelector('textarea');const caption=box.querySelector('small')?.cloneNode(true);box.textContent=replace(String(input?.value||box.dataset.default||''),values);if(caption)box.prepend(caption);}); updateSubmit();
    };
    root.querySelectorAll('[data-gw-section-toggle]').forEach(toggle=>toggle.addEventListener('click',()=>{const section=root.querySelector(`[data-gw-section="${toggle.dataset.gwSectionToggle}"]`);section.hidden=!section.hidden;toggle.classList.toggle('open',!section.hidden);}));
    root.querySelectorAll('[data-winners]').forEach(button=>button.addEventListener('click',()=>{root.querySelectorAll('[data-winners]').forEach(x=>x.classList.toggle('active',x===button));root.querySelector('[data-gw-winners]').value=button.dataset.winners;root.querySelector('[data-gw-custom-winners]').value=button.dataset.winners;preview();}));
    root.querySelector('[data-gw-custom-winners]')?.addEventListener('input',event=>{const value=Math.max(1,Math.min(20,+event.target.value||1));root.querySelector('[data-gw-winners]').value=value;root.querySelectorAll('[data-winners]').forEach(x=>x.classList.toggle('active',+x.dataset.winners===value));preview();});
    root.querySelectorAll('[data-minutes]').forEach(button=>button.addEventListener('click',()=>{root.querySelectorAll('[data-minutes]').forEach(x=>x.classList.toggle('active',x===button));root.querySelector('[data-gw-duration]').value=button.dataset.minutes;root.querySelector('[data-gw-custom-duration]').value='';preview();}));
    root.querySelector('[data-gw-custom-duration]')?.addEventListener('input',event=>{if(+event.target.value>0){root.querySelector('[data-gw-duration]').value=event.target.value;root.querySelectorAll('[data-minutes]').forEach(x=>x.classList.remove('active'));preview();}});
    root.querySelectorAll('[data-colour]').forEach(button=>button.addEventListener('click',()=>{const input=button.closest('.uv-colours')?.querySelector('input[type=color]');if(input){input.value=button.dataset.colour;input.dispatchEvent(new Event('input',{bubbles:true}));}}));
    form?.querySelectorAll('input,textarea').forEach(input=>{input.addEventListener('input',preview);input.addEventListener('change',preview);});
    root.querySelector('[data-gw-reset]')?.addEventListener('click',()=>setTimeout(()=>{root.querySelector('[data-gw-winners]').value='1';root.querySelector('[data-gw-duration]').value='1440';preview();},0)); preview();
  }
  const detail=document.querySelector('[data-gw-detail]');
  if(detail){
    detail.querySelectorAll('[data-gw-detail-tab]').forEach(button=>button.addEventListener('click',()=>{detail.querySelectorAll('[data-gw-detail-tab]').forEach(x=>x.classList.toggle('active',x===button));detail.querySelectorAll('[data-gw-detail-pane]').forEach(x=>x.classList.toggle('active',x.dataset.gwDetailPane===button.dataset.gwDetailTab));history.replaceState(null,'',`#${button.dataset.gwDetailTab}`);}));
    const hash=location.hash.slice(1);if(hash)detail.querySelector(`[data-gw-detail-tab="${hash}"]`)?.click();
    const liveValues={prize:detail.dataset.prize||'…',winners:detail.dataset.winners||'1',entries:detail.dataset.entries||'0',ends:new Date(+(detail.dataset.ends||0)*1000).toLocaleString('de-DE'),host:'@Host',winners_mentions:'@Alice, @Bob',server:'dein Server'};
    const renderLive=()=>detail.querySelectorAll('[data-gw-live-preview]').forEach(box=>{let text=box.parentElement.querySelector('textarea')?.value||box.dataset.default||'';Object.entries(liveValues).forEach(([key,value])=>text=text.split(`{${key}}`).join(value));const caption=box.querySelector('small')?.cloneNode(true);box.textContent=text;if(caption)box.prepend(caption);});
    detail.querySelectorAll('[data-gw-live-preview]').forEach(box=>box.parentElement.querySelector('textarea')?.addEventListener('input',renderLive));renderLive();
    detail.querySelectorAll('[data-colour]').forEach(button=>button.addEventListener('click',()=>{const input=button.closest('.uv-colours')?.querySelector('input[type=color]');if(input)input.value=button.dataset.colour;}));
    detail.querySelector('[data-gw-entry-search]')?.addEventListener('input',event=>{const q=event.target.value.trim().toLowerCase();detail.querySelectorAll('[data-gw-people] article').forEach(row=>row.hidden=!!q&&!row.dataset.search.includes(q));});
    detail.querySelectorAll('[data-confirm]').forEach(button=>button.addEventListener('click',event=>{if(!confirm(button.dataset.confirm))event.preventDefault();}));
    const modal=detail.querySelector('[data-gw-boost-modal]'),modeInput=detail.querySelector('[data-gw-boost-mode]');
    detail.querySelectorAll('[data-gw-boost]').forEach(button=>button.addEventListener('click',()=>{modal.hidden=false;document.body.classList.add('modal-open');modal.querySelector('[data-gw-boost-user]').value=button.dataset.id;modal.querySelector('[data-gw-boost-title]').textContent=button.dataset.name;modal.querySelector('[name=weight]').value=+button.dataset.weight>1?button.dataset.weight:100;modal.querySelector('[name=note]').value=button.dataset.note||'';modal.querySelector(`[data-mode="${button.dataset.guaranteed==='1'?'guaranteed':(+button.dataset.weight>1?'weight':'weight')}"]`)?.click();}));
    modal?.querySelectorAll('[data-gw-boost-close]').forEach(button=>button.addEventListener('click',()=>{modal.hidden=true;document.body.classList.remove('modal-open');}));
    modal?.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{modeInput.value=button.dataset.mode;modal.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('active',x===button));modal.querySelector('[data-gw-weight-wrap]').hidden=button.dataset.mode!=='weight';}));
  }
  document.querySelectorAll('time[data-timestamp]').forEach(el=>{const date=new Date(+el.dataset.timestamp*1000);if(!isNaN(date))el.textContent=new Intl.DateTimeFormat('de-DE',{dateStyle:'medium',timeStyle:'short'}).format(date);});
})();

// Full University Custom Command Creator. Marketplace is intentionally absent.
(() => {
  const root=document.querySelector('[data-cc-root]'); if(!root)return;
  const list=root.querySelector('[data-cc-list]'),editor=root.querySelector('[data-cc-editor]'),form=root.querySelector('[data-cc-form]');
  const actionsBox=root.querySelector('[data-cc-actions]'),paramsBox=root.querySelector('[data-cc-parameters]');
  const menu=root.querySelector('[data-cc-action-menu]'),picker=root.querySelector('[data-cc-picker]');
  const empty=()=>({description:'',actions:[],parameters:[],enabled:true,cooldown:0,allowed_roles:[],allowed_users:[],deny_without_role:false});
  const uid=()=>Math.random().toString(36).slice(2,10), esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let config=empty(),original='',menuTarget={parent:'root',branch:'then'},pickerDone=null,pickerKind='',pickerSelected=new Set(),pickerMulti=false;
  const kinds={reply:['Antworten','log'],add_role:['Rolle geben','plus'],remove_role:['Rolle entfernen','x'],send_channel:['Nachricht senden','external'],dm:['DM senden','users'],condition_role:['Bedingung','branch']};
  const sources={}; ['roles','channels','members'].forEach(kind=>sources[kind]=[...root.querySelectorAll(`[data-cc-source="${kind}"] button`)].map(x=>({id:x.dataset.id,name:x.dataset.name})));
  const sourceName=(kind,id)=>sources[kind]?.find(x=>x.id===String(id))?.name||String(id||'Nicht gewählt');
  const walk=(items,callback)=>{for(const action of items){if(callback(action))return action;const nested=[...(action.then||[]),...(action.else||[]),...(action.buttons||[]).flatMap(button=>button.actions||[])];const found=walk(nested,callback);if(found)return found}};
  const find=id=>walk(config.actions,action=>action.id===id);
  const remove=(items,id)=>items.filter(action=>action.id!==id).map(action=>({...action,then:action.then?remove(action.then,id):action.then,else:action.else?remove(action.else,id):action.else,buttons:action.buttons?.map(button=>({...button,actions:remove(button.actions||[],id)}))}));
  const destination=()=>{if(menuTarget.parent==='root')return config.actions;const owner=find(menuTarget.parent);if(!owner)return config.actions;if(menuTarget.branch.startsWith('button:'))return owner.buttons?.find(button=>button.id===menuTarget.branch.slice(7))?.actions||[];return owner[menuTarget.branch]||[]};
  const addAction=type=>{const item={id:uid(),type,...(type==='condition_role'?{then:[],else:[]}:{})};destination().push(item);closeMenu();renderActions()};
  const openMenu=(parent='root',branch='then')=>{menuTarget={parent,branch};menu.hidden=false;document.body.classList.add('modal-open')};
  const closeMenu=()=>{menu.hidden=true;document.body.classList.remove('modal-open')};
  const vars=()=>['{user}','{user_name}','{server}','{channel}','{date}','{args}',...config.parameters.filter(p=>p.name).map(p=>`{${p.name}:${p.type==='user'?'UserPing':p.type==='channel'?'ChannelPing':p.type==='role'?'RolePing':p.type==='integer'?'Number':p.type==='boolean'?'Boolean':'Text'}}`)];
  const varsHtml=(id,field='text')=>`<div class="cc-vars"><b>Variablen einfügen</b>${vars().map((token,index)=>`<button type="button" class="${index>5?'parameter':''}" data-cc-var="${esc(token)}" data-id="${id}" data-field="${field}">${esc(token)}</button>`).join('')}</div>`;
  const choice=(id,field,kind,value,placeholder)=>`<button type="button" class="cc-choice" data-cc-action-pick data-id="${id}" data-field="${field}" data-kind="${kind}"><span>${value?esc(sourceName(kind,value)):placeholder}</span><svg><use href="#i-chevron"></use></svg></button>`;
  const toggle=(label,checked,attrs)=>`<label class="cc-toggle"><span><b>${label}</b></span><input type="checkbox" ${checked?'checked':''} ${attrs}><i></i></label>`;
  function actionHtml(action,nested=false){
    const meta=kinds[action.type]||kinds.reply,embed=action.embed||{enabled:false,title:'',description:'',color:'#2563eb',image_url:'',footer:''},buttons=action.buttons||[];
    let body='';
    if(['reply','dm'].includes(action.type)){
      body+=toggle('Ephemeral (bei Slash nur für den User sichtbar)',!!action.ephemeral,`data-cc-action-check data-id="${action.id}" data-field="ephemeral"`);
      body+=`<textarea data-cc-action-value data-id="${action.id}" data-field="text" placeholder="Hallo {user}!">${esc(action.text||'')}</textarea>${varsHtml(action.id)}`;
      body+=`<button type="button" class="cc-embed-toggle" data-cc-embed-toggle data-id="${action.id}"><b>Embed (optional)</b><span>${embed.enabled?'Entfernen':'+ Hinzufügen'}</span></button>`;
      if(embed.enabled)body+=`<div class="cc-embed"><input data-cc-embed-value data-id="${action.id}" data-field="title" value="${esc(embed.title)}" placeholder="Embed-Titel"><textarea data-cc-embed-value data-id="${action.id}" data-field="description" placeholder="Embed-Beschreibung">${esc(embed.description)}</textarea>${varsHtml(action.id,'embed.description')}<div class="row"><input type="color" data-cc-embed-value data-id="${action.id}" data-field="color" value="${esc(embed.color||'#2563eb')}"><input data-cc-embed-value data-id="${action.id}" data-field="image_url" value="${esc(embed.image_url)}" placeholder="Bild-URL"></div><input data-cc-embed-value data-id="${action.id}" data-field="footer" value="${esc(embed.footer)}" placeholder="Footer"></div>`;
      body+=`<div class="cc-buttons-title"><b>Buttons (${buttons.length}/5)</b><button type="button" data-cc-add-button data-id="${action.id}" ${buttons.length>=5?'disabled':''}>+ Button</button></div>`;
      body+=buttons.map(button=>`<section class="cc-button-card"><header><span class="cc-button-preview ${esc(button.style||'blue')}">${esc(button.emoji||'')} ${esc(button.label||'Klick mich')}</span><small>${(button.actions||[]).length} Aktionen</small><button type="button" data-cc-remove-button data-id="${action.id}" data-button="${button.id}"><svg><use href="#i-trash"></use></svg></button></header><div class="cc-button-fields"><input data-cc-button-value data-id="${action.id}" data-button="${button.id}" data-field="label" value="${esc(button.label||'')}" placeholder="Label"><input data-cc-button-value data-id="${action.id}" data-button="${button.id}" data-field="emoji" value="${esc(button.emoji||'')}" placeholder="Emoji"><div class="cc-style-buttons">${['blue','gray','green','red'].map(style=>`<button type="button" class="${style} ${button.style===style?'selected':''}" data-cc-button-style data-id="${action.id}" data-button="${button.id}" data-style="${style}">${style==='blue'?'Blau':style==='gray'?'Grau':style==='green'?'Grün':'Rot'}</button>`).join('')}</div><small>Aktionen beim Klick</small>${actionsHtml(button.actions||[],true)}<button type="button" class="cc-add-step" data-cc-nested-add data-id="${action.id}" data-branch="button:${button.id}">+ Schritt hinzufügen</button></div></section>`).join('');
    } else if(action.type==='send_channel')body+=`${choice(action.id,'channel_id','channels',action.channel_id,'Kanal wählen …')}<textarea data-cc-action-value data-id="${action.id}" data-field="text">${esc(action.text||'')}</textarea>${varsHtml(action.id)}`;
    else if(['add_role','remove_role'].includes(action.type))body+=choice(action.id,'role_id','roles',action.role_id,'Rolle wählen …');
    else if(action.type==='condition_role')body+=`${choice(action.id,'role_id','roles',action.role_id,'Rolle wählen …')}<div class="cc-branch"><strong>Dann</strong>${actionsHtml(action.then||[],true)}<button type="button" class="cc-add-step" data-cc-nested-add data-id="${action.id}" data-branch="then">+ Schritt hinzufügen</button></div><div class="cc-branch else"><strong>Sonst</strong>${actionsHtml(action.else||[],true)}<button type="button" class="cc-add-step" data-cc-nested-add data-id="${action.id}" data-branch="else">+ Schritt hinzufügen</button></div>`;
    return `<article class="cc-action-card ${nested?'nested':''}"><header class="cc-action-head"><svg><use href="#i-${meta[1]}"></use></svg><b>${meta[0]}</b><button type="button" data-cc-remove-action data-id="${action.id}"><svg><use href="#i-trash"></use></svg></button></header><div class="cc-action-body">${body}</div></article>`;
  }
  function actionsHtml(items,nested=false){return items.map(action=>actionHtml(action,nested)).join('')}
  function bindActions(){
    actionsBox.querySelectorAll('[data-cc-remove-action]').forEach(button=>button.onclick=()=>{config.actions=remove(config.actions,button.dataset.id);renderActions()});
    actionsBox.querySelectorAll('[data-cc-nested-add]').forEach(button=>button.onclick=()=>openMenu(button.dataset.id,button.dataset.branch));
    actionsBox.querySelectorAll('[data-cc-action-value]').forEach(input=>input.oninput=()=>{find(input.dataset.id)[input.dataset.field]=input.value});
    actionsBox.querySelectorAll('[data-cc-action-check]').forEach(input=>input.onchange=()=>{find(input.dataset.id)[input.dataset.field]=input.checked});
    actionsBox.querySelectorAll('[data-cc-action-pick]').forEach(button=>button.onclick=()=>openPicker(button.dataset.kind,new Set(find(button.dataset.id)[button.dataset.field]?[String(find(button.dataset.id)[button.dataset.field])]:[]),false,ids=>{find(button.dataset.id)[button.dataset.field]=[...ids][0]||'';renderActions()}));
    actionsBox.querySelectorAll('[data-cc-var]').forEach(button=>button.onclick=()=>{const action=find(button.dataset.id);if(button.dataset.field==='embed.description'){action.embed.description=(action.embed.description||'')+button.dataset.ccVar}else action[button.dataset.field]=(action[button.dataset.field]||'')+button.dataset.ccVar;renderActions()});
    actionsBox.querySelectorAll('[data-cc-embed-toggle]').forEach(button=>button.onclick=()=>{const action=find(button.dataset.id),old=action.embed||{title:'',description:'',color:'#2563eb',image_url:'',footer:''};action.embed={...old,enabled:!old.enabled};renderActions()});
    actionsBox.querySelectorAll('[data-cc-embed-value]').forEach(input=>input.oninput=()=>{const action=find(input.dataset.id);action.embed={...(action.embed||{}),enabled:true,[input.dataset.field]:input.value}});
    actionsBox.querySelectorAll('[data-cc-add-button]').forEach(button=>button.onclick=()=>{const action=find(button.dataset.id);action.buttons=action.buttons||[];if(action.buttons.length<5)action.buttons.push({id:uid(),label:'Klick mich',emoji:'',style:'blue',actions:[]});renderActions()});
    actionsBox.querySelectorAll('[data-cc-remove-button]').forEach(button=>button.onclick=()=>{const action=find(button.dataset.id);action.buttons=(action.buttons||[]).filter(x=>x.id!==button.dataset.button);renderActions()});
    actionsBox.querySelectorAll('[data-cc-button-value]').forEach(input=>input.oninput=()=>{const button=find(input.dataset.id).buttons.find(x=>x.id===input.dataset.button);button[input.dataset.field]=input.value});
    actionsBox.querySelectorAll('[data-cc-button-style]').forEach(button=>button.onclick=()=>{find(button.dataset.id).buttons.find(x=>x.id===button.dataset.button).style=button.dataset.style;renderActions()});
  }
  function renderActions(){actionsBox.innerHTML=actionsHtml(config.actions);bindActions()}
  function renderParameters(){
    root.querySelector('[data-cc-param-count]').textContent=config.parameters.length;
    paramsBox.innerHTML=config.parameters.map((p,index)=>`<article class="cc-param-card"><header><b>Parameter ${index+1}</b><button type="button" data-cc-param-remove data-id="${p.id}"><svg><use href="#i-trash"></use></svg></button></header><label class="cc-field"><span>Name</span><input data-cc-param-value data-id="${p.id}" data-field="name" value="${esc(p.name)}" placeholder="mein_parameter"></label><label class="cc-field"><span>Beschreibung</span><input data-cc-param-value data-id="${p.id}" data-field="description" value="${esc(p.description)}"></label><div class="cc-param-types">${[['string','Text'],['integer','Zahl'],['user','User'],['channel','Kanal'],['role','Rolle'],['boolean','Ja/Nein']].map(([type,label])=>`<button type="button" class="${p.type===type?'selected':''}" data-cc-param-type data-id="${p.id}" data-type="${type}">${label}</button>`).join('')}</div>${toggle('Pflicht',!!p.required,`data-cc-param-required data-id="${p.id}"`)}</article>`).join('');
    paramsBox.querySelectorAll('[data-cc-param-remove]').forEach(button=>button.onclick=()=>{config.parameters=config.parameters.filter(x=>x.id!==button.dataset.id);renderParameters();renderActions()});
    paramsBox.querySelectorAll('[data-cc-param-value]').forEach(input=>input.oninput=()=>{const p=config.parameters.find(x=>x.id===input.dataset.id);p[input.dataset.field]=input.dataset.field==='name'?input.value.toLowerCase().replace(/\W/g,'_'):input.value});
    paramsBox.querySelectorAll('[data-cc-param-type]').forEach(button=>button.onclick=()=>{config.parameters.find(x=>x.id===button.dataset.id).type=button.dataset.type;renderParameters();renderActions()});
    paramsBox.querySelectorAll('[data-cc-param-required]').forEach(input=>input.onchange=()=>config.parameters.find(x=>x.id===input.dataset.id).required=input.checked);
  }
  function renderChips(){
    const roles=root.querySelector('[data-cc-role-chips]'),users=root.querySelector('[data-cc-user-chips]');
    roles.innerHTML=config.allowed_roles.map(id=>`<button type="button" data-remove="${id}">${esc(sourceName('roles',id))} ×</button>`).join('');users.innerHTML=config.allowed_users.map(id=>`<button type="button" data-remove="${id}">${esc(sourceName('members',id))} ×</button>`).join('');
    roles.querySelectorAll('button').forEach(button=>button.onclick=()=>{config.allowed_roles=config.allowed_roles.filter(x=>x!==button.dataset.remove);renderChips()});users.querySelectorAll('button').forEach(button=>button.onclick=()=>{config.allowed_users=config.allowed_users.filter(x=>x!==button.dataset.remove);renderChips()});
  }
  function openPicker(kind,selected,multi,done){pickerKind=kind;pickerSelected=new Set(selected);pickerMulti=multi;pickerDone=done;picker.hidden=false;root.querySelector('[data-cc-picker-title]').textContent=kind==='roles'?'Rolle auswählen':kind==='channels'?'Kanal auswählen':'User auswählen';root.querySelector('[data-cc-picker-search]').value='';renderPicker()}
  function renderPicker(){const q=root.querySelector('[data-cc-picker-search]').value.toLowerCase(),box=root.querySelector('[data-cc-picker-results]');box.innerHTML=(sources[pickerKind]||[]).filter(item=>item.name.toLowerCase().includes(q)||item.id.includes(q)).map(item=>`<button type="button" class="${pickerSelected.has(item.id)?'selected':''}" data-id="${item.id}">${esc(item.name)}</button>`).join('');box.querySelectorAll('button').forEach(button=>button.onclick=()=>{if(pickerMulti){pickerSelected.has(button.dataset.id)?pickerSelected.delete(button.dataset.id):pickerSelected.add(button.dataset.id);renderPicker()}else{pickerSelected=new Set([button.dataset.id]);pickerDone?.(pickerSelected);closePicker()}})}
  function closePicker(){picker.hidden=true;document.body.classList.remove('modal-open')}
  root.querySelector('[data-cc-picker-search]').oninput=renderPicker;root.querySelectorAll('[data-cc-picker-close]').forEach(button=>button.onclick=()=>{if(pickerMulti)pickerDone?.(pickerSelected);closePicker()});
  root.querySelectorAll('[data-cc-action-kind]').forEach(button=>button.onclick=()=>addAction(button.dataset.ccActionKind));root.querySelectorAll('[data-cc-menu-close]').forEach(button=>button.onclick=closeMenu);
  root.querySelector('[data-cc-add-root]').onclick=()=>openMenu();root.querySelector('[data-cc-add-param]').onclick=()=>{if(config.parameters.length<10){config.parameters.push({id:uid(),name:'',description:'',type:'string',required:false});renderParameters()}};
  root.querySelectorAll('[data-cc-tab]').forEach(button=>button.onclick=()=>{root.querySelectorAll('[data-cc-tab]').forEach(x=>x.classList.toggle('active',x===button));root.querySelectorAll('[data-cc-pane]').forEach(x=>x.classList.toggle('active',x.dataset.ccPane===button.dataset.ccTab))});
  root.querySelector('[data-cc-choose="allowed_roles"]').onclick=()=>openPicker('roles',new Set(config.allowed_roles),true,ids=>{config.allowed_roles=[...ids];renderChips()});root.querySelector('[data-cc-choose="allowed_users"]').onclick=()=>openPicker('members',new Set(config.allowed_users),true,ids=>{config.allowed_users=[...ids];renderChips()});
  const open=entry=>{original=entry?.name||'';config={...empty(),...(entry?.config||{}),actions:entry?.config?.actions||[],parameters:entry?.config?.parameters||[],allowed_roles:entry?.config?.allowed_roles||[],allowed_users:entry?.config?.allowed_users||[]};list.hidden=true;editor.hidden=false;form.reset();root.querySelector('[data-cc-original]').value=original;root.querySelector('[data-cc-name]').value=entry?.name||'';root.querySelector('[data-cc-name]').disabled=!!original;root.querySelector('[data-cc-description]').value=config.description||'';root.querySelector('[data-cc-editor-mode]').textContent=original?'bearbeiten':'erstellen';for(const key of ['use_prefix','use_exact','use_contains','use_slash'])form.elements[key].checked=entry?!!entry[key]:['use_prefix','use_slash'].includes(key);root.querySelector('[data-cc-enabled]').checked=config.enabled!==false;root.querySelector('[data-cc-cooldown]').value=config.cooldown||0;root.querySelector('[data-cc-deny]').checked=!!config.deny_without_role;renderActions();renderParameters();renderChips();updateLabels();scrollTo({top:0,behavior:'smooth'})};
  const close=()=>{editor.hidden=true;list.hidden=false;original='';scrollTo({top:0,behavior:'smooth'})};root.querySelector('[data-cc-close]').onclick=close;root.querySelectorAll('[data-cc-new]').forEach(button=>button.onclick=()=>open());root.querySelectorAll('[data-cc-edit]').forEach(button=>button.onclick=()=>open(JSON.parse(button.closest('article').querySelector('[data-cc-command-payload]').value)));
  root.querySelectorAll('[data-cc-delete]').forEach(deleteForm=>deleteForm.onsubmit=event=>{if(!confirm('Command wirklich löschen?'))event.preventDefault()});
  const updateLabels=()=>{const name=root.querySelector('[data-cc-name]').value||'command';root.querySelector('[data-cc-prefix-label]').textContent=`Server-Präfix (${root.dataset.prefix}${name})`;root.querySelector('[data-cc-slash-label]').textContent=`Slash (/${name})`};root.querySelector('[data-cc-name]').oninput=updateLabels;
  form.onsubmit=event=>{config.description=root.querySelector('[data-cc-description]').value;config.enabled=root.querySelector('[data-cc-enabled]').checked;config.cooldown=+root.querySelector('[data-cc-cooldown]').value||0;config.deny_without_role=root.querySelector('[data-cc-deny]').checked;const name=root.querySelector('[data-cc-name]').value.trim().toLowerCase().replace(/\s+/g,'-').replace(/^[!>?./]+/,'');root.querySelector('[data-cc-name]').disabled=false;root.querySelector('[data-cc-name]').value=name;if(!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(name)){event.preventDefault();alert('Bitte einen gültigen Command-Namen eingeben.');return}if(!config.actions.length){event.preventDefault();alert('Füge mindestens einen Flow-Schritt hinzu.');return}if(!['use_prefix','use_exact','use_contains','use_slash'].some(key=>form.elements[key].checked)){event.preventDefault();alert('Wähle mindestens eine Erkennungsart.');return}root.querySelector('[data-cc-config]').value=JSON.stringify(config)};
})();

// Dedicated Automation: messages, responses and announcements.
(() => {
  const root=document.querySelector('[data-auto-root]');if(!root)return;
  const activate=tab=>{root.querySelectorAll('[data-auto-tab]').forEach(button=>button.classList.toggle('active',button.dataset.autoTab===tab));root.querySelectorAll('[data-auto-pane]').forEach(pane=>pane.classList.toggle('active',pane.dataset.autoPane===tab));};
  root.querySelectorAll('[data-auto-tab]').forEach(button=>button.addEventListener('click',()=>{activate(button.dataset.autoTab);history.replaceState(null,'',`?tab=${button.dataset.autoTab}`)}));activate(root.dataset.activeTab||'messages');
  const localDate=timestamp=>{const date=new Date(timestamp*1000),pad=n=>String(n).padStart(2,'0');return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`};
  const modalFor=kind=>root.querySelector(`[data-auto-modal="${kind}"]`);
  const setControl=(form,name,value)=>{const input=form.elements[name];if(!input)return;if(input.type==='checkbox')input.checked=!!value;else input.value=value??'';input.dispatchEvent(new Event('change',{bubbles:true}));};
  const open=(kind,item=null)=>{const modal=modalFor(kind),form=modal.querySelector('form');form.reset();setControl(form,'id',item?.id||'');setControl(form,'enabled',item?!!item.enabled:true);setControl(form,'color',item?.color||'#5865f2');setControl(form,'title',item?.title||'');setControl(form,'image_url',item?.image_url||'');
    if(kind==='messages'){setControl(form,'channel_id',item?.channel_id||'');setControl(form,'content',item?.content||'');setControl(form,'send_at',localDate(item?.next_run||Math.floor(Date.now()/1000)+3600));setControl(form,'repeat_minutes',item?.repeat_minutes||0);setControl(form,'delete_after',item?.delete_after||0)}
    if(kind==='responses'){setControl(form,'trigger',item?.trigger||'');setControl(form,'response',item?.response||'');setControl(form,'cooldown_seconds',item?.cooldown_seconds||0);setControl(form,'exact',!!item?.exact)}
    if(kind==='announcements'){setControl(form,'channel_id',item?.channel_id||'');setControl(form,'mention_role_id',item?.mention_role_id||'');setControl(form,'content',item?.content||'');setControl(form,'interval_minutes',item?.interval_minutes||1440);setControl(form,'first_delay_minutes',item?Math.max(0,Math.round((item.next_run-Date.now()/1000)/60)):0)}
    modal.querySelector('[data-auto-modal-title]').textContent=item?'Automation bearbeiten':kind==='messages'?'Nachricht planen':kind==='responses'?'Auto-Response erstellen':'Ankündigung erstellen';modal.hidden=false;document.body.classList.add('modal-open');};
  const close=modal=>{modal.hidden=true;document.body.classList.remove('modal-open')};
  root.querySelectorAll('[data-auto-new]').forEach(button=>button.addEventListener('click',()=>open(button.dataset.autoNew)));
  root.querySelectorAll('[data-auto-edit]').forEach(button=>button.addEventListener('click',()=>{const article=button.closest('article'),item=JSON.parse(article.querySelector('[data-auto-payload]').value);open(button.dataset.autoEdit,item)}));
  root.querySelectorAll('[data-auto-close]').forEach(button=>button.addEventListener('click',()=>close(button.closest('[data-auto-modal]'))));
  root.querySelectorAll('[data-auto-delete]').forEach(button=>button.addEventListener('click',event=>{if(!confirm('Automation wirklich löschen?'))event.preventDefault()}));
  let focused=null;root.querySelectorAll('.auto-modal textarea,.auto-modal input[type=text]').forEach(input=>{input.addEventListener('focus',()=>focused=input)});root.querySelectorAll('[data-auto-token]').forEach(button=>button.addEventListener('click',()=>{if(!focused||!button.closest('form').contains(focused))return;const start=focused.selectionStart??focused.value.length,end=focused.selectionEnd??start;focused.setRangeText(button.dataset.autoToken,start,end,'end');focused.focus()}));
})();
