"""Reviewed bot-copy templates; dynamic values and server-authored copy stay intact."""
import json
import re
from pathlib import Path

_DATA = json.loads(Path(__file__).with_name('dm_translations.json').read_text(encoding='utf-8'))


def _pattern(template):
    pieces = re.split(r'(\{\d+\})', template)
    seen = set()
    pattern = ''
    for piece in pieces:
        if re.fullmatch(r'\{\d+\}', piece):
            key = 'p' + piece[1:-1]
            pattern += f'(?P={key})' if key in seen else f'(?P<{key}>.*?)'
            seen.add(key)
        else:
            pattern += re.escape(piece)
    return re.compile('^' + pattern + '$', re.S)


_EXACT = {row[lang]: row for row in _DATA for lang in ('en', 'de') if not re.search(r'\{\d+\}', row[lang])}
_RULES = [(row, lang, _pattern(row[lang])) for row in _DATA for lang in ('en', 'de') if re.search(r'\{\d+\}', row[lang])]
_RULES.sort(key=lambda x: len(re.sub(r'\{\d+\}', '', x[0][x[1]])), reverse=True)


def translate(text, language='en'):
    value = str(text or '')
    if value.strip().startswith('```'):
        return value
    # Formatting and the bot's custom marker are not part of the copy key.
    match = re.match(r'^(\s*(?:#{1,3} |\-# )?(?:(?:<a?:\w+:\d+>|[^\w\s*`<])\s*)?(?:\*\*)?)(.*?)(\*\*)?$', value, re.S)
    candidates = [(value, '', '')]
    if match:
        candidates.append((match[2], match[1], match[3] or ''))
    for body, prefix, suffix in candidates:
        exact = _EXACT.get(body)
        if exact:
            return prefix + exact[language if language in ('en', 'de') else 'en'] + suffix
        for row, source, pattern in _RULES:
            found = pattern.fullmatch(body)
            if found:
                target = row[language if language in ('en', 'de') else 'en']
                target = re.sub(r'\{(\d+)\}', lambda m: _parameter(found.group('p' + m[1]), language) if int(m[1]) in row.get('localized', []) else found.group('p' + m[1]), target)
                return prefix + target + suffix
    # Cards often join several independent paragraphs/lines. Translate only
    # whole known frames; never replace words inside user-supplied values.
    if '\n' in value:
        lines = value.split('\n')
        return '\n'.join(translate(line, language) if line else '' for line in lines)
    return value


def preserve(view):
    """Mark a server-created message. Its wording must never be translated."""
    if view is not None:
        view._university_dm_custom_copy = True
    return view


def preserve_body(view):
    """Protect a server-authored body while allowing the bot heading to localize."""
    for item in view.walk_children():
        if type(item).__name__ == 'TextDisplay' and not item.content.startswith(('#', '-#')):
            item._university_dm_custom_copy = True
    return view


def verification_success(view, settings):
    from utils.verify_store import DEFAULTS
    original = settings.get('dm_success_text', '')
    presets = {DEFAULTS['dm_success_text'], 'Willkommen auf **{server}**, {user.name}!\n\nDu bist verifiziert und kannst loslegen. Schau am besten zuerst in die Regeln und stell dich kurz vor.'}
    return view if original in presets else preserve_body(view)


def bot_reason(reason, user_id, fallback='No reason provided'):
    from utils.dm_preferences import language
    return reason if reason else translate(fallback, language(user_id))


def preserve_values(view, values):
    """Protect only the exact server-authored fields, leaving bot copy localizable."""
    values = {str(x) for x in values if x}
    for item in view.walk_children():
        if type(item).__name__ == 'TextDisplay' and (item.content in values or re.sub(r'^#{1,3}\s+', '', item.content).removeprefix('**').removesuffix('**') in values):
            item._university_dm_custom_copy = True
        if type(item).__name__ == 'Button' and item.label in values:
            item._university_dm_custom_copy = True
    return view


def _parameter(value, language):
    units = r'(?:seconds?|minutes?|hours?|days?|Sekunden?|Minuten?|Stunden?|Tage?)'
    if re.match(r'^\d+(?:[.,]\d+)? ' + units + r'\b', value):
        return re.sub(r'\d+(?:[.,]\d+)? ' + units + r'\b', lambda m: translate(m[0], language), value)
    # Incident summaries and lists of automatic actions contain no user copy.
    if '× ' in value or ' · ' in value:
        return ', '.join(' · '.join(translate(part, language) for part in group.split(' · ')) for group in value.split(', '))
    return translate(value, language)
