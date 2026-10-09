"""Local German/English topic matching, including common price paraphrases."""
from difflib import SequenceMatcher
import re
import unicodedata

ALIASES = {
    **dict.fromkeys(('gratis','kostenlos','kostenfrei','umsonst','nix','nichts','free'), 'free'),
    **dict.fromkeys(('preis','preise','price','prices','kosten','kostet','kostenpunkt','cost','costs','zahlen','bezahlen','paid'), 'price'),
    **dict.fromkeys(('eur','euros','euro','eu'), 'euro'),
    **dict.fromkeys(('regel','regeln','rules','rule'), 'rule'),
    **dict.fromkeys(('rolle','rollen','role','roles'), 'role'),
    **dict.fromkeys(('kaufen','kauf','buy','purchase'), 'purchase'),
    **dict.fromkeys(('support','hilfe','help','helfen'), 'support'),
    **dict.fromkeys(('bewerbung','bewerbungen','application','applications'), 'application'),
    **dict.fromkeys(('verifizierung','verifizieren','verification','verify'), 'verify'),
}
STOP = set('der die das dem den des ein eine einer einen einem eines ist sind es gibt nun jetzt hier dort bei auf im in am an unserem unsere unser server this the a an is are it our on at in for of and or to you your users user man kann bekommt bekommen und oder fur von mit ohne ich wir ihr also bitte have has not no nicht mehr will dann schon'.split())
FIELDS = {'price': {'price','free','euro','dollar'}, 'role': {'role'}, 'rule': {'rule'}, 'purchase': {'purchase','shop'}, 'verify': {'verify'}, 'application': {'application'}}

def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold().replace('ß','ss')) if not unicodedata.combining(c))

def words(value):
    tokens = {ALIASES.get(w, w) for w in re.findall(r'[a-z0-9_]+', normalize(value)) if w not in STOP and len(w) >= 2}
    if '€' in value: tokens.update(('euro','price'))
    if 'free' in tokens: tokens.add('price')
    return tokens

def subjects(value):
    attributes = set().union(*FIELDS.values())
    return {w for w in words(value) - attributes - {'how','what','where','viel','does','much'} if not w.isdigit()}

def related_word(a, b):
    return a == b or (min(len(a),len(b)) >= 5 and (a in b or b in a or SequenceMatcher(None,a,b).ratio() >= .84))

def same_topic(incoming, existing):
    if normalize(incoming).strip() == normalize(existing).strip(): return True
    left, right = words(incoming), words(existing)
    lf = {name for name,tokens in FIELDS.items() if left & tokens}
    rf = {name for name,tokens in FIELDS.items() if right & tokens}
    if bool(lf) != bool(rf): return False
    if lf and rf and not lf & rf: return False
    # A price statement is distinct from general Premium role/shop details.
    if ('price' in lf) != ('price' in rf) and (lf and rf): return False
    attributes = set().union(*FIELDS.values()) | {'yes','nein','ja','true','false'}
    left = {w for w in left - attributes if not w.isdigit()}
    right = {w for w in right - attributes if not w.isdigit()}
    if not left or not right: return False
    overlap = sum(any(related_word(a,b) for b in right) for a in left)
    return overlap >= 1 and overlap / min(len(left),len(right)) >= .7
