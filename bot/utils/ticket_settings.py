"""Validated ticket preferences shared by the API and Discord runtime."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA = "CREATE TABLE IF NOT EXISTS ticket_preferences (guild_id INTEGER NOT NULL, scope TEXT NOT NULL, object_id INTEGER NOT NULL, settings TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(guild_id, scope, object_id))"
STATE_SCHEMA = "CREATE TABLE IF NOT EXISTS ticket_workflow (channel_id INTEGER PRIMARY KEY, last_activity REAL NOT NULL, alerted REAL, team_alerted REAL, priority TEXT NOT NULL DEFAULT 'normal', close_requested_by INTEGER)"
FEEDBACK_SCHEMA = "CREATE TABLE IF NOT EXISTS ticket_feedback_requests (channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, creator_id INTEGER NOT NULL, snapshot TEXT NOT NULL)"
RATING_SCHEMA = "CREATE TABLE IF NOT EXISTS ticket_ratings (channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, creator_id INTEGER NOT NULL, score INTEGER NOT NULL, comment TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL)"
DEFAULTS = dict(active=True, prefix='ticket', description='', capacity=50, priority='normal',
    ping_team=True, ticket_limit=3, staff_only_close=True, allow_participants=False,
    restrict_claimed=False, allow_on_behalf=False, on_leave='none', name_format='{prefix}-{ticket_number}-{username}',
    show_capacity=True, timezone='Europe/Berlin', opening_hours=[], claim_category_id='',
    rating_enabled=False, rating_channel_id='', rating_public_channel_id='',
    rating_values=['creator', 'category', 'duration'], snippets=[],
    auto_close=False, auto_close_seconds=86400, auto_alert=False, auto_alert_seconds=86400,
    auto_team_alert=False, auto_team_alert_seconds=86400, high_priority_seconds=0,
    auto_unclaim=False, auto_unclaim_seconds=86400, close_after_alert=False,
    auto_claim=False, close_after_request=False, no_auto_close_priority='off',
    welcome_image_url='', welcome_thumbnail_url='', opening_questions=None,
    closing_questions=[], rating_questions=[])


def decode(value):
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def validate(data, *, category=False):
    if not isinstance(data, dict):
        raise ValueError('Ticket settings must be an object.')
    clean = {}
    for key, value in data.items():
        if key not in DEFAULTS:
            raise ValueError(f'Unknown ticket setting: {key}')
        if value is None and category:
            continue  # Category inherits this field from its panel.
        default = DEFAULTS[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(f'{key} must be true or false.')
        elif isinstance(default, int):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= (31536000 if key.endswith('_seconds') else 1000):
                raise ValueError(f'Invalid value for {key}.')
            if key.endswith('_seconds') and key != 'high_priority_seconds' and value < 60:
                raise ValueError('Automation delays must be at least 60 seconds.')
        elif key.endswith('_questions'):
            if value is None and key == 'opening_questions':
                clean[key] = None
                continue
            if not isinstance(value, list) or len(value) > (4 if key == 'rating_questions' else 5):
                raise ValueError('A form can contain up to five fields.')
            questions = []
            for field in value:
                if not isinstance(field, dict) or not str(field.get('label', '')).strip():
                    raise ValueError('Every form field needs a name.')
                kind = field.get('type', 'short')
                if kind not in ('short', 'paragraph', 'image', 'file', 'select', 'checkbox', 'radio'):
                    raise ValueError('Unknown form field type.')
                maximum = field.get('max_length', 4000 if kind == 'paragraph' else 200)
                if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 4000:
                    raise ValueError('The form character limit must be between 1 and 4000.')
                if not isinstance(field.get('options',[]),list):raise ValueError('Form options must be a list.')
                choices = [str(x).strip()[:100] for x in field.get('options', []) if str(x).strip()]
                if kind in ('select', 'radio') and not 1 <= len(choices) <= 25:
                    raise ValueError('Selection fields need between 1 and 25 options.')
                if kind == 'checkbox' and len(choices) > 10:
                    raise ValueError('Checkbox fields support up to 10 options.')
                questions.append(dict(label=str(field['label']).strip()[:45], type=kind,
                    required=bool(field.get('required', True)), placeholder=str(field.get('placeholder', ''))[:100],
                    description=str(field.get('description', ''))[:100], max_length=maximum,
                    options=choices, public=bool(field.get('public', False))))
            value = questions
        elif key == 'opening_hours':
            if not isinstance(value, list) or len(value) > 28:
                raise ValueError('Invalid opening hours.')
            intervals = []
            for item in value:
                if not isinstance(item,dict):raise ValueError('Invalid opening hours.')
                day = item.get('day')
                if isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 6:
                    raise ValueError('Invalid weekday.')
                try:
                    start = datetime.strptime(item['start'], '%H:%M').time()
                    end = datetime.strptime(item['end'], '%H:%M').time()
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError('Enter opening hours as HH:MM.') from exc
                if start >= end or any(d == day and start < e and end > s for d, s, e in intervals):
                    raise ValueError('Opening hours must not overlap and must end after they start.')
                intervals.append((day, start, end))
            value = [dict(day=d, start=s.strftime('%H:%M'), end=e.strftime('%H:%M')) for d,s,e in intervals]
        elif key == 'rating_values':
            if not isinstance(value, list) or any(x not in ('supporter','creator','case','category','panel','duration') for x in value):
                raise ValueError('Invalid public rating fields.')
        elif key == 'snippets':
            if not isinstance(value, list) or len(value) > 25:
                raise ValueError('Up to 25 snippets are supported.')
            if any(not isinstance(x,dict) for x in value):raise ValueError('Invalid text snippet.')
            value = [dict(name=str(x.get('name','')).strip()[:80], text=str(x.get('text',''))[:2000]) for x in value]
            if any(not x['name'] or not x['text'] for x in value):
                raise ValueError('Text snippets need a name and a message.')
        else:
            value = str(value or '')
            if len(value) > 500:
                raise ValueError(f'{key} is too long.')
            if key.endswith('_id') and value and not value.isdigit():
                raise ValueError('Channel and category IDs must be numeric strings.')
            if key.endswith('_url') and value and not value.startswith('https://'):
                raise ValueError('Image addresses must start with https://.')
            allowed = {'priority': ('low','normal','high','urgent'), 'on_leave': ('none','delete','notify'),
                       'no_auto_close_priority': ('off','low','normal','high','urgent')}
            if key in allowed and value not in allowed[key]:
                raise ValueError(f'Invalid {key}.')
            if key == 'timezone':
                try: ZoneInfo(value)
                except (ZoneInfoNotFoundError, ValueError) as exc: raise ValueError('Unknown timezone.') from exc
        clean[key] = value
    return clean


def resolve(panel=None, category=None):
    return {**DEFAULTS, **(panel or {}), **(category or {})}


def sync_settings(db, guild_id, panel_id, category_id=None):
    def load(scope, object_id):
        row = db.fetchone('SELECT settings FROM ticket_preferences WHERE guild_id=? AND scope=? AND object_id=?', (guild_id, scope, object_id))
        return decode(row['settings']) if row else {}
    return resolve(load('panel', panel_id), load('category', category_id) if category_id else {})


def is_open(settings, now=None):
    hours = settings.get('opening_hours') or []
    if not hours:
        return True
    current = now or datetime.now(ZoneInfo(settings['timezone']))
    return any(x['day'] == current.weekday() and x['start'] <= current.strftime('%H:%M') < x['end'] for x in hours)


async def load(db, guild_id, scope, object_id):
    async with db.execute('SELECT settings FROM ticket_preferences WHERE guild_id=? AND scope=? AND object_id=?', (guild_id, scope, object_id)) as cursor:
        row = await cursor.fetchone()
    return decode(row[0]) if row else {}


async def save(db, guild_id, scope, object_id, settings):
    clean = validate(settings, category=scope == 'category')
    await db.execute('INSERT INTO ticket_preferences VALUES(?,?,?,?) ON CONFLICT(guild_id,scope,object_id) DO UPDATE SET settings=excluded.settings', (guild_id,scope,object_id,json.dumps(clean)))
