# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Centralized emoji module for the universitybot bot.
All emoji definitions are stored here for easy management and consistency.
"""

# ============================================================================
# DISCORD CUSTOM EMOJIS (Static)
# ============================================================================
BOOST = "<:boost:1530375445785084005>"
BUG_HUNTER = "<:BugHunterLevel1:1530375321281368285>"
BUG_HUNTER_LVL2 = "<:BugHunterLvl2:1532395583564677380>"
CAST = "<:zcast:1530375366495965264>"
CERTIFIED_MODERATOR = "<:CertifiedDiscordModerator:1530375542338093227>"
CHANNEL = "<:channel:1530375477263470745>"
CODEBASE = "<:codebase:1530375110815645706>"
CODED = "<:coded:1530375137382109184>"
CROSS = "<:zcross:1530375117954093107>"
CROSS_ALT = "<:CrossIcon:1530375441888710918>"
CUTE_CUTE_CUTE = "<:Cute_Cute_Cute:1530375091601539243>"
DELETE = "<:delete:1530375208899448902>"
DELETE_ALT1 = "<:delete:1530375208899448902>"
DENIED = "<:Denied:1530375301656219849>"
DISABLE = "<:Disable:1530375483936608277>"
DND = "<:dnd:1530375178448535634>"
EARLY_SUPPORTER = "<:EarlySupporter:1530375223051026582>"
ENABLE = "<:Enable:1530375130683801730>"
# The original ":error:" emoji no longer exists on Discord's CDN and is not
# hosted by the application, so it rendered as literal "<:error:...>" text.
# Point it at the red cross the application really owns.
ERROR = "<:zcross:1530375117954093107>"
FORWARD = "<:forward:1530375267560722522>"
GAMES = "<:games:1530375470921810150>"
HANDSHAKE = "<:handshake:1530375521534214306>"
HAPPY_PANDA = "<:happy_panda:1530375098035339334>"
HEADMOD = "<:headmod:1530375195397849309>"
HEART3 = "<:heart3:1530375335223365772>"
HEART_EM = "<:heart_em:1530375151152267314>"
HEERIYE = "<:Heeriye:1530375555654881341>"
HOME = "<:icons_home:1530375328114016470>"
HYPESQUAD_BRILLIANCE = "<:Hypesquad_Brilliance:1530375404962185489>"
ICONLOAD = "<:iconLoad:1530375463996756008>"
ICONS_CHANNEL = "<:icons_channel:1530375438654898288>"
ICONS_MUSIC = "<:icons_music:1530375398804819988>"
ICONS_PAUSE = "<:icons_pause:1530375294656057394>"
ICONS_PLUS = "<:icons_plus:1530375247008759960>"
ICONS_WARNING = "<:icons_warning:1530375205631955056>"
ICONS_WARNING_ALT1 = "<:icons_warning:1530375205631955056>"
ICON_BROWSER = "<:icon_browser:1530375500214829247>"
IDLE = "<:idle:1530375449488785429>"
INDEX = "<:index:1530375391959580783>"
INFO = "<:info:1530375411299782786>"
KING = "<a:king:1530375254529147023>"
LEVEL_UP = "<:zlevelup:1530375085167218688>"
LOCK = "<:lock:1530375181887995924>"
MANAGER = "<:manager:1530375251031101552>"
MENTION = "<:universitybot_mention:1530375331729510430>"
MESSAGE = "<:zmsg:1530375239580516484>"
MINECRAFT = "<:zmc:1530375460620337152>"
ML_CROSS = "<:ml_cross:1530375171444179085>"
MUSIC = "<:zmusic:1530375363090448404>"
MUSICSTOP_ICONS = "<:musicstop_icons:1530375140381294635>"
MUTE = "<:zmute:1530375311043334145>"
NEW = "<:New:1530375314528538625>"
NEXT = "<:icons_next:1530375143992590346>"
NEXT_ALT1 = "<:next:1530375229845672077>"
OFFLINE = "<:offline:1530375199114137772>"
PARTNER_BADGE = "<:PartneredServerOwner:1532395582306386231>"
PC = "<:pc:1530375283893469234>"
PIN = "<:zpin:1530375133791784964>"
# Was <:next:> -- the same right-pointing arrow as NEXT_ALT1, so every
# "previous page" button in the paginator and the help menu showed an
# arrow pointing forwards. <:zback:> is the app's only left-pointing
# arrow; checked against the rendered images, not the names.
PREVIOUS = "<:zback:1530375525044850749>"
RED_BUTTON = "<:red_button:1530375507214991471>"
RED_PIN = "<:red_pin:1530375100900053043>"
REWIND = "<:rewind1:1530375493751148675>"
REWIND_ALT1 = "<:rewind:1530375395298250772>"
SEED = "<:zseed:1530375235981803573>"
SHUFFLE = "<:shuffle:1530375185079865375>"
SKIP = "<:skip:1530375545823694888>"
STAR = "<:starr:1530375456715444358>"
SWORD = "<:zsowrd:1530375481067573340>"
SYSTEM = "<:universitybot_system:1530375121292755104>"
THUNDER = "<:universitybotthunder:1530375325056237600>"
TICK = "<:ztick:1530375424922750977>"
TICKET = "<:zticket:1530375273802104833>"
TICK_ALT = "<:tick:1530375233037664349>"
TIME = "<:universitybot_time:1530375094893936800>"
TIMER = "<:ztimer:1530375552190517319>"
UNLOCK = "<:unlock:1530375088577450054>"
UPTIME = "<:uptime:1530375280714055731>"
U_ADMIN = "<:U_admin:1530375175432966204>"
WARNING = "<:warning:1530375219733201036>"
WARNING_ALT = "<:warning:1530375219733201036>"
WIFI = "<:zwifi:1530375277459537960>"
ZAI = "<:zai:1530375243258920980>"
ZARROW = "<:zArrow:1530375154977214504>"
ZBACK = "<:zback:1530375525044850749>"
ZBAN = "<:zban:1530375511237197856>"
ZBOT = "<:zbot:1530375453142159521>"
ZCIRCLE = "<:zcircle:1530375261185638400>"
ZCIRCLE_ALT1 = "<:zcircle:1530375261185638400>"
ZCLOUD = "<:zCloud:1530375428559343936>"
ZCOUNTING = "<:zcounting:1530375514722926783>"
ZCROSS = "<:zcross:1530375117954093107>"
ZDIL = "<:zdil:1530375257800835184>"
ZHUMAN = "<:zHuman:1530375212862935040>"
ZMODULE = "<:zmodule:1530375147008294923>"
ZMUSICPAUSE = "<:zmusicpause:1530375338733867019>"
ZPAUSE = "<:zpause:1530375124258259015>"
ZPEOPLE = "<:zpeople:1530375384657297549>"
ZPLAY = "<:zplay:1530375388558262282>"
ZPLUS = "<:zplus:1530375548793262110>"
ZROCKET = "<:zrocket:1530375359806312488>"
ZSAFE = "<:zSafe:1530375518434889879>"
ZSETTINGS = "<:zsettings:1530375532535873636>"
ZTADA = "<:ztada:1530375290684047540>"
ZTICK = "<:Ztick:1530375535925006457>"
ZUNMUTE = "<:zunmute:1530375376654565507>"
ZWARNING = "<:zwarning:1530375341607096371>"
ZWRENCH = "<:zwrench:1530375167446876170>"
universitybotCONNECTION = "<:universitybotconnection:1530375380681363476>"
universitybotHAMMER = "<:universitybothammer:1530375418128105592>"
universitybotLINKS = "<:universitybotlinks:1530375352835117126>"
universitybotSYS = "<:universitybotsys:1530375270790467584>"
universitybot_CODE = "<:universitybot_code:1530375487174606878>"
universitybot_COMMAND = "<:universitybot_command:1530375113814577194>"
universitybot_GLOBAL = "<:universitybot_global:1530375192025632969>"
universitybot_OWNER = "<:universitybot_owner:1530375107812524112>"
universitybot_SEARCH = "<:universitybot_search:1530375538999562240>"

# ============================================================================
# DISCORD CUSTOM EMOJIS (Animated)
# ============================================================================
ACTIVE_DEVELOPER = "<a:Active_Developer:1530375164259209216>"
ARROWRED = "<a:ArrowRed:1530375308270899371>"
BLACKCROWN = "<a:BlackCrown:1530375431973376001>"
BLOBPART = "<a:blobpart:1530375528979103805>"
BOOSTS = "<a:boosts:1530375345574777045>"
EARLY_VERIFIED_BOT_DEV = "<a:EarlyVerifiedBotDeveloper:1530375202331164844>"
EMOTE = "<a:emote:1530375407965310979>"
GIFD = "<a:GIFD:1530375467344072905>"
GIFN = "<a:GIFN:1530375490215477251>"
HYPESQUAD_BALANCE = "<a:a_Hypesquad_Balance:1530375496829763684>"
HYPESQUAD_BRAVERY = "<a:a_Hypesquad_Bravery:1530375356274708702>"
HYPESQUAD_EVENTS = "<:HypesquadEvents:1532395580771536917>"
KING_ALT1 = "<a:king:1530375254529147023>"
LOADING = "<a:loading:1530375402004942909>"
LOADINGRED = "<a:loadingred:1530375297894060083>"
LOADING_ALT1 = "<a:loading:1530375402004942909>"
MAX__A = "<a:max__A:1530375373232144388>"
MENTION_ALT1 = "<a:mention:1530375226532167770>"
MINGLE = "<a:mingle:1530375188720652438>"
MOBILE = "<a:mobile:1530375216151134278>"
MUSIC_ALT1 = "<a:music:1530375370006593779>"
NITRO_BOOST = "<a:nitroboost:1530375104372932739>"
ONLINE = "<a:online:1530375304907067452>"
PREMIUM = "<a:premium:1530375127638872164>"
RACECAR64 = "<a:racecar64:1530375435463168110>"
REDDOT = "<a:reddot:1530375503712878603>"
REDHEART = "<a:RedHeart:1530375421596794912>"
REDRULESBOOK = "<a:RedRulesBook:1530375161017008229>"
SG_RD = "<a:sg_rd:1530375264574374118>"
STAFF = "<a:staff:1530375157988720792>"
STAR_ALT1 = "<a:Star:1530375287399776406>"
STAR_ALT2 = "<a:star:1530375318085566464>"
TADAA = "<a:TADAA:1530375414575529984>"
TIMER_ALT1 = "<a:timer:1530375349232472206>"
_37496ALERT = "<a:37496alert:1530375474276995152>"

# ============================================================================
# DISCORD BADGE EMOJIS MAPPING (Dictionary)
# ============================================================================
DISCORD_BADGE_EMOJIS = {
    "staff": STAFF,
    "partner": PARTNER_BADGE,
    "hypesquad": HYPESQUAD_BRILLIANCE,
    "hypesquad_bravery": HYPESQUAD_BRAVERY,
    "hypesquad_brilliance": HYPESQUAD_BRILLIANCE,
    "hypesquad_balance": HYPESQUAD_BALANCE,
    "bug_hunter": BUG_HUNTER,
    "bug_hunter_level_2": BUG_HUNTER_LVL2,
    "early_supporter": EARLY_SUPPORTER,
    "early_verified_bot_developer": EARLY_VERIFIED_BOT_DEV,
    "certified_moderator": CERTIFIED_MODERATOR,
    "active_developer": ACTIVE_DEVELOPER,
    "discord_mod": CERTIFIED_MODERATOR,
}

# ============================================================================
# UNICODE EMOJIS
# ============================================================================
ARROW_DOWN = "⬇️"
ARROW_LEFT = "⬅️"
ARROW_RIGHT = "➡️"
ARROW_UP = "⬆️"
BLOCK = "🚫"
BUBBLE_TEA = "🧋"
CELEBRATE = "🎉"
CHERRIES = "🍒"
CLOCK = "⏱️"
COOKIE = "🍪"
CURSOR = "🖱️"
DIZZY = "🥴"
ERROR_UNICODE = "❌"
GAME_CONTROLLER = "🎮"
HEARTS = "💕"
JAVA_COFFEE = "☕"
LAUGH1 = "😂"
LAUGH2 = "🤣"
LAUGH3 = "😆"
LOCK_UNICODE = "🔒"
MONEY = "💸"
MOON = "🌙"
NOTE = "📝"
PAPER = "\U0001f4f0"
PEACH = "🍑"
REFRESH = "🔄"
ROCK = "\U0001faa8"
SCISSORS = "\U00002702"
SHOCKED = "😳"
SPARKLE = "✨"
STAR_UNICODE = "⭐"
STOP_BUTTON = "⏹️"
SUCCESS = "✅"
TARGET = "🎯"
TONGUE_OUT = "😜"
UPSIDE_DOWN = "🙃"
WARNING_UNICODE = "⚠️"

# ============================================================================
# EMOJI COLLECTIONS BY CATEGORY (Dictionaries)
# ============================================================================
GAME_BUTTONS = {
    "up": ARROW_UP,
    "down": ARROW_DOWN,
    "left": ARROW_LEFT,
    "right": ARROW_RIGHT,
    "stop": STOP_BUTTON,
    "target": "🎯",
}

# The app owns 142 custom emojis, so these tables use them rather than
# the platform's ✅ / ❌ / ⚠️. Those render differently on every OS and
# have nothing to do with the bot's own look; the custom set is one
# style everywhere. The *_UNICODE constants stay defined for anywhere
# a real fallback is still wanted.
ACTION_EMOJIS = {
    "success": TICK,
    "error": CROSS,
    "warning": WARNING,
    "clock": TIMER,
    # The app has no refresh arrow of its own; <:iconLoad:> is the
    # nearest thing and reads as "working on it".
    "refresh": ICONLOAD,
}

RPS_CHOICES = {
    "rock": ROCK,
    "scissors": SCISSORS,
    "paper": PAPER,
}

BUTTON_EMOJIS = {
    "note": MESSAGE,
    "privacy": LOCK,
    "claim": STAR,
    "untrust": CROSS,
    "block": DENIED,
    # No custom counterpart for these two among the app's 142; the
    # platform emoji stays rather than a wrong icon that happens to be
    # custom.
    "target": "🎯",
    "edit": "✏️",
}

REACTION_TEST_EMOJIS = [
    COOKIE, CELEBRATE, BUBBLE_TEA, CHERRIES, PEACH, MONEY, MOON, HEARTS
]

FUN_EMOJIS = [
    LAUGH1, LAUGH2, LAUGH3, SHOCKED, DIZZY, UPSIDE_DOWN, TONGUE_OUT
]

MINECRAFT_EMOJIS = {
    "success": TICK,
    "error": CROSS,
    "warning": WARNING,
    "clock": TIMER,
    "refresh": ICONLOAD,
    # <:zmc:> is the app's own Minecraft icon -- better here than a
    # coffee cup standing in for "Java edition".
    "java": MINECRAFT,
}

# ============================================================================
# FEATURE EMOJIS (Dictionaries)
# ============================================================================
MODERATION_EMOJIS = {
    "warn": WARNING,
    "mute": MUTE,
    "ban": SWORD,
    "kick": SWORD,
    "lock": LOCK,
}

TICKET_EMOJIS = {
    "ticket": TICKET,
    "close": ERROR,
    "open": SUCCESS,
    "pin": PIN,
}

LEVEL_EMOJIS = {
    "level_up": LEVEL_UP,
    "sparkle": SPARKLE,
    "achievement": STAR,
}

UTILITY_EMOJIS = {
    "music": MUSIC,
    "system": SYSTEM,
    "new": NEW,
    "message": MESSAGE,
    "wifi": WIFI,
    "cast": CAST,
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_badge_emoji(badge_name: str) -> str:
    """
    Get Discord badge emoji by name.
    
    Args:
        badge_name: The name of the badge (e.g., 'staff', 'partner', 'bug_hunter')
    
    Returns:
        The emoji string for the badge, or None if not found
    """
    return DISCORD_BADGE_EMOJIS.get(badge_name.lower())


def get_action_emoji(action: str) -> str:
    """
    Get emoji for a common action.
    
    Args:
        action: The action name (e.g., 'success', 'error', 'warning')
    
    Returns:
        The emoji string for the action
    """
    return ACTION_EMOJIS.get(action.lower())


def get_button_emoji(button_type: str) -> str:
    """
    Get emoji for a button type.
    
    Args:
        button_type: The button type (e.g., 'note', 'privacy', 'claim')
    
    Returns:
        The emoji string for the button
    """
    return BUTTON_EMOJIS.get(button_type.lower())


# ============================================================================
# COMPATIBILITY ALIASES
# ============================================================================

# Common aliases for frequently used emojis.
#
# These used to be split: ERROR was the custom <:zcross:>, while SUCCESS
# right next to it was the platform's ✅ -- so a success and a failure
# from the same command did not look like they came from the same bot.
# Both are custom now.
CHECKMARK = TICK
CROSS_MARK = CROSS
CHECK = TICK
FAIL = ERROR
OK = TICK
NOT_OK = ERROR


# ============================================================================
# BUTTON LABEL → EMOJI
# ============================================================================

# 140 buttons across the bot carried no emoji at all. Rather than pick
# one at 140 call sites -- and end up with three different icons for
# "Cancel" -- the label decides, once, here.
#
# Matched lowercase; the longest matching key wins, so "stop freezing"
# does not pick up the plain "stop" icon. A label with no match keeps no
# emoji: a wrong icon is worse than none.
LABEL_EMOJIS = {
    # confirm / deny
    "yes": TICK,
    "no": CROSS,
    "confirm": TICK,
    "confirm reset": WARNING,
    "cancel": CROSS,
    "submit": TICK,
    "submit & continue": TICK,
    "finish setup": TICK,
    "done": TICK,
    "enable": ENABLE,
    "disable": DISABLE,
    "approve": TICK,
    "deny": DENIED,
    # navigation
    "next": NEXT,
    "previous": PREVIOUS,
    "back": ZBACK,
    "back to setup": ZBACK,
    "home": HOME,
    "stop": MUSICSTOP_ICONS,
    "stop freezing": MUSICSTOP_ICONS,
    # editing
    "edit": ZWRENCH,
    "edit content": MESSAGE,
    "edit settings": ZSETTINGS,
    "settings": ZSETTINGS,
    "change channels": CHANNEL,
    "manage channels": CHANNEL,
    "manage roles": U_ADMIN,
    "manage users": ZPEOPLE,
    "manage ignores": ZSETTINGS,
    "add": ZPLUS,
    "delete": DELETE,
    "remove": DELETE,
    "clear": DELETE,
    "reset": WARNING,
    # information
    "info": INFO,
    "help": INFO,
    "support": HANDSHAKE,
    "vote": STAR,
    "invite": ZBOT,
    "title": MESSAGE,
    "description": MESSAGE,
    "show rules": REDRULESBOOK,
    "show overwrites": ZSETTINGS,
    "show punishment type": SWORD,
    "view ignored": INFO,
    "list successful": TICK,
    "list unsuccessful": CROSS,
    # features
    "verify now": ZSAFE,
    "quick verify": ZSAFE,
    "captcha verify": ZSAFE,
    "verify with captcha": ZSAFE,
    "enter code": ZSAFE,
    "setup verification system": ZSAFE,
    "join": ZPLUS,
    "steal as emoji": EMOTE,
    "steal as sticker": EMOTE,
    "global afk": ZDIL,
    "local afk": ZDIL,
    "download icon": ICON_BROWSER,
    "server avatar": ZPEOPLE,
    "user banner": ZHUMAN,
    "make a guess!": GAMES,
    "hint": INFO,
}


def get_label_emoji(label: str) -> str | None:
    """
    The emoji for a button label, or None when nothing fits.

    Longest match first, so "edit settings" does not resolve to the
    plain "edit" icon.
    """
    key = str(label or "").strip().lower()
    if not key:
        return None
    if key in LABEL_EMOJIS:
        return LABEL_EMOJIS[key]
    # Fall back to the longest key contained in the label.
    best = None
    for candidate, emoji in LABEL_EMOJIS.items():
        if candidate in key and (best is None or len(candidate) > len(best[0])):
            best = (candidate, emoji)
    return best[1] if best else None

