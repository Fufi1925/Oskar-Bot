# Website languages

The website supports German and English through the shared language provider.
The language switcher is available in the existing website and dashboard
navigation. The selected language is stored in local storage
and a `website-language` cookie, including when local storage is unavailable.
The cookie gives server-rendered pages and the OAuth start handler the same
preference. Explicit `lang=de` / `lang=en` links override the saved preference.
Changing the language updates an existing `lang` parameter to preserve the
selection after reloading the verification result page.

Legacy UI translations retain their original DOM text and attributes across
language changes. React/API updates replace the recorded source. Translators
are cached rather than rebuilding the full catalog for each mutation. Native
confirmation, prompt and alert dialogs use the same catalog; input values,
custom Discord preview text and `data-no-translate` content are preserved.
Date and number formatting follows the selected locale. Global notices and
popups share the provider, and verification result pages suppress modal popups.

OAuth state signs the selected language together with the guild ID, nonce and
expiry. Result links include the language without granting any additional
Discord scopes. Success, denial, cancellation, backend errors and expired
links render localized views. Success links return to the verified server;
retry links retain the chosen language. An invalid OAuth state has no trusted
guild ID and is redirected to a safe error view without a retry action.

Maintain German/English phrase pairs in `tools/i18n_work/batch_*.json` and
variable templates in `dynamic_pairs.json`. Generate and check them with:

```sh
python tools/build_dom_translations.py
python tools/find_missing_translations.py --check
node --test dashboard/tests/*.test.cjs
npm --prefix dashboard run build
```

The audit uses the installed dashboard TypeScript parser to extract JSX text,
attributes, options, messages and dynamic template branches. It excludes code,
styles, protected custom text and identifiers. It checks shipped UI copy, not
arbitrary user-generated content or unknown upstream error messages.
