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
      sourceItems(kind).forEach((source) => {
        if (term && !source.textContent.toLocaleLowerCase('de').includes(term)) return;
        const option = source.cloneNode(true);
        option.classList.toggle('selected', pickerChoices.has(source.dataset.id));
        option.addEventListener('click', () => {
          if (pickerButton.hasAttribute('data-picker-multiple')) {
            if (pickerChoices.has(source.dataset.id)) pickerChoices.delete(source.dataset.id);
            else pickerChoices.add(source.dataset.id);
            renderPickerResults();
            return;
          }
          const target = document.getElementById(pickerButton.dataset.pickerTarget);
          if (target) {
            target.value = source.dataset.id;
            target.dispatchEvent(new Event('change', { bubbles: true }));
          }
          updatePickerButtons(pickerButton.dataset.pickerTarget, kind);
          closePicker();
        });
        results.appendChild(option);
        shown += 1;
      });
      modal?.querySelector('[data-picker-empty]')?.toggleAttribute('hidden', shown !== 0);
      if (pickerCount) pickerCount.textContent = `${pickerChoices.size} ausgewählt`;
    };

    const openPicker = (button) => {
      pickerButton = button;
      pickerChoices = new Set(targetValues(button));
      if (pickerTitle) pickerTitle.textContent = pickerKindTitle[button.dataset.pickerKind] || 'Auswählen';
      pickerFooter?.toggleAttribute('hidden', !button.hasAttribute('data-picker-multiple'));
      if (searchInput) searchInput.value = '';
      modal.hidden = false;
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('ub-picker-open');
      renderPickerResults();
      window.setTimeout(() => searchInput?.focus(), 30);
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

    document.querySelectorAll('[data-picker-open]').forEach((button) => button.addEventListener('click', () => openPicker(button)));
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
      const known = !channel || sourceItems('channels').some((item) => item.dataset.id === channel);
      const broken = enabled && (!channel || !known);
      row.classList.toggle('active', enabled && channel && known);
      row.classList.toggle('broken', broken);
      row.querySelector('.ub-log-category-controls')?.toggleAttribute('hidden', !enabled);
      const error = row.querySelector('[data-category-error]');
      if (error) {
        error.hidden = !broken;
        if (broken) error.lastChild.textContent = channel && !known ? 'Diesen Kanal gibt es nicht mehr.' : 'Kein Kanal gewählt — hier landet nichts.';
      }
      const test = row.querySelector('.ub-log-test');
      const hint = row.querySelector('.ub-log-test-hint');
      const saved = channel && channel === row.dataset.savedChannel && known;
      if (test) test.hidden = !enabled || !saved;
      if (hint) hint.hidden = !enabled || !channel || saved;
    };
    const updateSummary = () => {
      const rows = [...loggingForm.querySelectorAll('[data-log-category]')];
      rows.forEach(updateCategory);
      const active = rows.filter((row) => row.classList.contains('active')).length;
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
      if (copy) copy.textContent = `${broken.length === 1 ? 'ist an' : 'sind an'}, aber dort landet nichts. Kanal fehlt oder wurde gelöscht.`;
      loggingForm.querySelector('[data-log-all-off]')?.toggleAttribute('hidden', !rows.some((row) => row.querySelector('input[type="checkbox"]').checked));
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
    loggingForm.querySelectorAll('[data-log-preset]').forEach((button) => button.addEventListener('click', () => {
      if (!allChannel?.value) return;
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
      userCandidate.value = ''; addUser.disabled = true; updatePickerButtons('ignore-user-candidate', 'members'); renderUserChips();
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

  root.classList.add('dashboard-js');
})();
