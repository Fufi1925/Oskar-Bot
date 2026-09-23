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

  const stored = localStorage.getItem('lbost-language') || 'de';
  document.querySelectorAll('[data-language-current]').forEach((el) => { el.textContent = stored.toUpperCase(); });
  document.querySelectorAll('[data-language]').forEach((button) => button.addEventListener('click', () => {
    localStorage.setItem('lbost-language', button.dataset.language);
    document.querySelectorAll('[data-language-current]').forEach((el) => { el.textContent = button.dataset.language.toUpperCase(); });
    closePopovers(null);
  }));
  root.classList.add('dashboard-js');
})();
