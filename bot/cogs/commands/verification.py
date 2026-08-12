# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

import discord 
from utils.emoji import CROSS, TICK, WARNING, ZSAFE
from discord .ext import commands 
from discord import app_commands 
from discord .ui import LayoutView ,TextDisplay ,Separator ,ActionRow ,MediaGallery 
from utils .cv2 import build_container 
from utils import verify_store 
import aiosqlite 
import random 
import string 
import io 
from PIL import Image ,ImageDraw ,ImageFont 
import asyncio 
import logging 
from datetime import datetime ,timezone ,timedelta 
from typing import Optional 
from utils .Tools import *
from utils.panels import from_view


logger =logging .getLogger ('discord')

DATABASE_PATH ='db/verification.db'


# Accent colours for the Components V2 cards. These were all the same red
# before, so a successful verification looked exactly like a hard error.
TONE_COLORS = {
    "info": 0x3D7CFF,
    "success": 0x2ECC71,
    "warning": 0xF1C40F,
    "error": 0xE74C3C,
}

TONE_MARKERS = {
    "info": "\u2022",
    "success": "\u2713",
    "warning": "!",
    "error": "\u00d7",
}


class VCard(LayoutView):
    """
    A Components V2 card, used everywhere this cog previously sent an embed.

    Renders as a real container with a coloured accent bar. The tone drives
    both the colour and the marker in front of the title, so success,
    warning and error are distinguishable at a glance.
    """

    def __init__(self, title: str, *sections, tone: str = "info"):
        super().__init__(timeout=None)

        self.card_title = title
        self.card_tone = tone

        marker = TONE_MARKERS.get(tone, "\u2022")
        items = [TextDisplay(f"### {marker}  {title}" if title else f"### {marker}")]

        for section in sections:
            text = str(section).strip()
            if not text:
                continue
            items.append(Separator(visible=True))
            items.append(TextDisplay(text))

        self.add_item(
            build_container(*items, accent_color=TONE_COLORS.get(tone, TONE_COLORS["info"]))
        )


# Kept for any leftover reference; mapped onto the tones above.
DISCORD_COLORS = {
    'primary': TONE_COLORS["info"],
    'success': TONE_COLORS["success"],
    'warning': TONE_COLORS["warning"],
    'error': TONE_COLORS["error"],
    'secondary': TONE_COLORS["info"],
    'neutral': TONE_COLORS["info"],
}


def utc_to_ist (dt :datetime )->datetime :
    ist_offset =timedelta (hours =5 ,minutes =30 )
    return dt .replace (tzinfo =timezone .utc ).astimezone (timezone (ist_offset ))


async def check_bot_permissions (guild :discord .Guild ,channel =None )->dict :
    """Check if bot has necessary permissions"""
    bot_member =guild .me 
    required_perms ={
    'guild':['manage_roles','manage_channels','send_messages','manage_messages'],
    'channel':['view_channel','send_messages','attach_files','embed_links','manage_messages']
    }

    missing_perms ={'guild':[],'channel':[]}


    for perm in required_perms ['guild']:
        if not getattr (bot_member .guild_permissions ,perm ):
            missing_perms ['guild'].append (perm .replace ('_',' ').title ())


    if channel and hasattr (channel ,'permissions_for'):
        channel_perms =channel .permissions_for (bot_member )
        for perm in required_perms ['channel']:
            if not getattr (channel_perms ,perm ):
                missing_perms ['channel'].append (perm .replace ('_',' ').title ())

    return missing_perms 


def validate_role_hierarchy (guild :discord .Guild ,role :discord .Role )->bool :
    """Check if bot can manage the specified role"""
    bot_top_role =guild .me .top_role 
    return bot_top_role .position >role .position 

async def create_verified_role (guild :discord .Guild )->discord .Role :
    """Create a verified role with proper permissions"""
    try :

        existing_role =discord .utils .get (guild .roles ,name ="Verified")
        if existing_role :
            return existing_role 


        verified_role =await guild .create_role (
        name ="Verified",
        color =discord .Color .from_rgb (35 ,165 ,90 ),
        reason ="Auto-created for verification system",
        permissions =discord .Permissions (
        read_messages =True ,
        send_messages =True ,
        read_message_history =True ,
        use_external_emojis =True ,
        add_reactions =True ,
        attach_files =True ,
        embed_links =True ,
        connect =True ,
        speak =True ,
        use_voice_activation =True 
        )
        )


        bot_roles =[role for role in guild .roles if role .managed and role .members and guild .me in role .members ]
        position =1 
        if bot_roles :
            position =min (role .position for role in bot_roles )-1 

        await verified_role .edit (position =max (1 ,position ))

        return verified_role 
    except Exception as e :
        logger .error (f"Error creating verified role: {e}")
        raise 

async def auto_fix_permissions (guild :discord .Guild ,verification_channel :discord .TextChannel ,verified_role :discord .Role ):
    """Automatically fix channel permissions for verification system"""
    try :
        everyone_role =guild .default_role 
        bot_member =guild .me 
        failed_channels =[]


        try :
            await verification_channel .set_permissions (
            everyone_role ,
            view_channel =True ,
            send_messages =False ,
            add_reactions =False ,
            reason ="Auto-fix: Verification channel permissions"
            )
            await verification_channel .set_permissions (
            verified_role ,
            view_channel =False ,
            reason ="Auto-fix: Hide verification from verified users"
            )
            await verification_channel .set_permissions (
            bot_member ,
            view_channel =True ,
            send_messages =True ,
            manage_messages =True ,
            embed_links =True ,
            attach_files =True ,
            reason ="Auto-fix: Bot verification permissions"
            )
        except discord .Forbidden :
            logger .warning (f"Cannot fix permissions for verification channel: {verification_channel.name}")


        for channel in guild .channels :
            if isinstance (channel ,(discord .TextChannel ,discord .VoiceChannel ,discord .CategoryChannel )):
                if channel .id !=verification_channel .id :
                    try :

                        current_overwrites =channel .overwrites 


                        everyone_perms =current_overwrites .get (everyone_role )
                        if not everyone_perms or everyone_perms .view_channel is not False :
                            await channel .set_permissions (
                            everyone_role ,
                            view_channel =False ,
                            reason ="Auto-fix: Verification system privacy"
                            )


                        verified_perms =current_overwrites .get (verified_role )
                        if not verified_perms or verified_perms .view_channel is not True :
                            await channel .set_permissions (
                            verified_role ,
                            view_channel =True ,
                            reason ="Auto-fix: Verified role access"
                            )
                    except discord .Forbidden :
                        failed_channels .append (channel .name )

        if failed_channels :
            logger .warning (f"Failed to auto-fix permissions for channels: {', '.join(failed_channels)}")

        return len (failed_channels )

    except Exception as e :
        logger .error (f"Error in auto-fix permissions: {e}")
        return -1 

class CaptchaCard (LayoutView ):
    """
    The CAPTCHA DM as one Components V2 container: instructions, the image
    and the "Enter code" button all inside the same accented block, instead
    of an embed with a file and a view bolted on next to it.
    """

    def __init__ (self ,*,guild_name :str ,buttons :list ,select =None ):
        super ().__init__ (timeout =None )

        instruction =(
        "Such unten den Code aus dem Bild heraus."
        if select is not None else
        "Löse das CAPTCHA und tippe den Code über den Knopf ein."
        )

        items =[
        TextDisplay ("## Kurz bestätigen"),
        Separator (visible =True ),
        TextDisplay (
        f"**Server:** {guild_name}\n\n"
        f"{instruction}\n"
        "Achte auf **Groß- und Kleinschreibung**."
        ),
        MediaGallery (discord .MediaGalleryItem ("attachment://captcha.png")),
        ]

        # A select has to sit in an ActionRow of its own -- Discord
        # refuses a row that mixes a select with anything else.
        if select is not None :
            items .append (ActionRow (select ))
        elif buttons :
            items .append (ActionRow (*buttons [:5 ]))

        self .add_item (build_container (*items ,accent_color =TONE_COLORS ["info"]))


class VerificationPanel (LayoutView ):
    """
    The public verification panel, as a single Components V2 container.

    Previously this was an embed with the buttons attached underneath, so the
    accent bar stopped above the controls. Here the text and the buttons sit
    in one container, which is what V2 is for.

    timeout=None plus the buttons keeping their custom_id makes the panel
    survive a bot restart.
    """

    def __init__ (self ,*,guild_name :str ,methods :list ,role_name :str ,buttons :list ):
        super ().__init__ (timeout =None )

        items =[
        TextDisplay (f"## Verification required"),
        Separator (visible =True ),
        TextDisplay (
        f"Welcome to **{guild_name}**.\n"
        "Verify yourself to unlock the rest of the server."
        ),
        ]

        if methods :
            items .append (Separator (visible =True ))
            items .append (TextDisplay ("\n".join (methods )))

        items .append (Separator (visible =True ))
        items .append (TextDisplay (
        f"You will receive the **{role_name}** role and full access to every channel."
        ))

        if buttons :
            items .append (Separator (visible =True ))
            items .append (ActionRow (*buttons [:5 ]))

        self .add_item (build_container (*items ,accent_color =TONE_COLORS ["info"]))


class ConfigurablePanel (LayoutView ):
    """
    The verification panel, with every word coming from the settings.

    Replaces the fixed-text VerificationPanel: the old one hard-coded
    English strings, so a German server could set a channel and a role
    and nothing else. timeout=None plus the buttons keeping their
    custom_id is what makes the panel survive a restart.
    """

    def __init__ (self ,*,title :str ,sections :list ,buttons :list ):
        super ().__init__ (timeout =None )

        items =[TextDisplay (f"## {title}")]
        for section in sections :
            text =str (section ).strip ()
            if not text :
                continue
            items .append (Separator (visible =True ))
            items .append (TextDisplay (text ))

        if buttons :
            items .append (Separator (visible =True ))
            # Discord refuses more than five buttons in one row.
            items .append (ActionRow (*buttons [:5 ]))

        self .add_item (build_container (*items ,accent_color =TONE_COLORS ["info"]))


class VerificationModal (discord .ui .Modal ,title ="Enter Verification Code"):
    def __init__ (self ,bot ,captcha_code :str ,guild_id :int ):
        super ().__init__ ()
        self .bot =bot 
        self .captcha_code =captcha_code 
        self .guild_id =guild_id 

    captcha_input =discord .ui .TextInput (
    label ="Verification Code",
    placeholder ="Enter the 6-character code from the image",
    required =True ,
    max_length =6 ,
    min_length =6 
    )

    async def on_submit (self ,interaction :discord .Interaction ):
        try :
            if self .captcha_input .value .strip ()!=self .captcha_code :
                embed =VCard("Incorrect Code", "The code you entered is incorrect. Please try again by clicking the verification button in the server.", tone='error')
                await interaction .response .send_message (view =embed ,ephemeral =True )
                return 

            guild =self .bot .get_guild (self .guild_id )
            if not guild :
                await interaction .response .send_message ("Server not found.",ephemeral =True )
                return 

            member =guild .get_member (interaction .user .id )
            if not member :
                await interaction .response .send_message ("You are not in the server.",ephemeral =True )
                return 


            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verified_role_id FROM verification_config WHERE guild_id = ? AND enabled = 1",
                    (guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        await interaction .response .send_message ("Verification system is not configured.",ephemeral =True )
                        return 

                    verified_role =guild .get_role (result [0 ])
                    if not verified_role :
                        await interaction .response .send_message ("Verified role not found.",ephemeral =True )
                        return 


                    if verified_role in member .roles :
                        embed =VCard("Already Verified", "You are already verified in this server!", tone='success')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


            # The modal fires from a DM, so interaction.user is a User and
            # interaction.guild is None -- finish_verification needs the
            # member and the guild it belongs to.
            proxy =_MemberInteraction (interaction ,guild ,member )
            card =await finish_verification (
            self .bot ,proxy ,verified_role ,"captcha"
            )
            if card is None :
                return 
            await interaction .response .send_message (view =card ,ephemeral =True )

        except discord .Forbidden :
            await interaction .response .send_message ("Bot lacks permission to assign roles.",ephemeral =True )
        except Exception as e :
            logger .error (f"Error in verification modal: {e}")
            pass 

    async def log_verification (self ,guild_id :int ,user_id :int ,method :str ):
        try :
            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    current_time =utc_to_ist (discord .utils .utcnow ())
                    await cur .execute (
                    "INSERT INTO verification_logs (guild_id, user_id, verification_method, verified_at) VALUES (?, ?, ?, ?)",
                    (guild_id ,user_id ,method ,current_time .isoformat ())
                    )
                    await db .commit ()
        except Exception as e :
            logger .error (f"Error logging verification: {e}")

    async def send_verification_log (self ,guild :discord .Guild ,user :discord .Member ,method :str ,success :bool ):
        try :
            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT log_channel_id FROM verification_config WHERE guild_id = ?",
                    (guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if result and result [0 ]:
                        log_channel =guild .get_channel (result [0 ])
                        if log_channel and log_channel .permissions_for (guild .me ).send_messages :
                            current_time =utc_to_ist (discord .utils .utcnow ())
                            embed =VCard (
                            "Verification "+("succeeded"if success else "failed"),
                            f"**User:** {user.mention} (`{user}`)\n"
                            f"**ID:** `{user.id}`\n"
                            f"**Method:** {method}\n"
                            f"**Time:** {current_time.strftime('%d.%m.%Y %H:%M')}",
                            tone ="success"if success else "error",
                            )
                            await log_channel .send (view =embed )
        except Exception as e :
            logger .error (f"Error sending verification log: {e}")

class _MemberInteraction :
    """
    An interaction that knows its guild and member.

    The CAPTCHA modal is submitted from a direct message, where
    ``interaction.guild`` is None and ``interaction.user`` is a User
    rather than a Member -- so role checks and mentions would both fail.
    This wraps the real interaction and substitutes the two.
    """

    def __init__ (self ,interaction ,guild ,member ):
        self ._interaction =interaction 
        self .guild =guild 
        self .user =member 

    def __getattr__ (self ,name ):
        return getattr (self ._interaction ,name )


async def finish_verification (bot ,interaction ,role ,method :str ):
    """
    Everything that happens once somebody passes.

    Was copy-pasted across three button views with slightly different
    wording each time; now one place decides what is said, whether a DM
    goes out and which extra rules apply.

    Returns a card to show the person, or None when they were rejected
    (in which case the rejection has already been sent).
    """
    guild =interaction .guild 
    member =interaction .user 

    async with aiosqlite .connect (DATABASE_PATH )as db :
        settings =await verify_store .get_settings (db ,guild .id )

    # A minimum account age keeps throwaway accounts out. Off unless set.
    created =getattr (member ,"created_at",None )
    if created is not None :
        age_days =(datetime .now (timezone .utc )-created ).total_seconds ()/86400
        if verify_store .account_too_young (settings ,age_days ):
            needed =settings ["min_account_age_days"]
            await interaction .response .send_message (
            view =VCard (
            "Konto zu neu",
            f"Dein Discord-Konto muss mindestens **{needed} Tage** alt sein, "
            f"um dich hier zu verifizieren.\n\n"
            f"Deins ist **{int(age_days)} Tage** alt.",
            tone ='error',
            ),
            ephemeral =True ,
            )
            return None 

    await member .add_roles (role ,reason =f"Verifizierung ({method})")

    # Take the holding role away, if the server uses one.
    unverified_id =settings .get ("unverified_role_id")
    if settings .get ("remove_unverified_role")and unverified_id :
        unverified =guild .get_role (int (unverified_id ))
        if unverified is not None and unverified in member .roles :
            try :
                await member .remove_roles (unverified ,reason ="Verifiziert")
            except (discord .Forbidden ,discord .HTTPException ):
                # Not fatal: they are verified either way.
                pass 

    modal =VerificationModal (bot ,"",guild .id )
    await modal .log_verification (guild .id ,member .id ,method )
    await modal .send_verification_log (guild ,member ,method .upper (),True )

    def fill (key ):
        return verify_store .render (
        settings .get (key ,""),
        server =guild .name ,
        user_mention =member .mention ,
        user_name =member .display_name ,
        role =f"@{role.name}",
        member_count =guild .member_count or 0 ,
        )

    if settings .get ("dm_on_success"):
        try :
            await member .send (view =VCard (
            "Verifiziert",fill ("dm_success_text"),tone ='success',
            ))
        except (discord .Forbidden ,discord .HTTPException ):
            # Closed DMs are not a verification failure.
            pass 

    return VCard ("Verifiziert",fill ("success_text"),tone ='success')


class VerificationView (discord .ui .View ):
    def __init__ (self ,bot ):
        super ().__init__ (timeout =None )
        self .bot =bot 

    @discord .ui .button (label ="Quick Verify", emoji=ZSAFE,style =discord .ButtonStyle .green ,custom_id ="verify_button_quick")
    async def verify_button (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        try :

            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verified_role_id, verification_method FROM verification_config WHERE guild_id = ? AND enabled = 1",
                    (interaction .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        embed =VCard("System Unavailable", "Verification system is not configured or disabled.", tone='error')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 

                    verified_role =interaction .guild .get_role (result [0 ])
                    verification_method =result [1 ]

                    if not verified_role :
                        embed =VCard("Verification", "Verified role not found. Please contact an administrator.", tone='error')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


                    if verified_role in interaction .user .roles :
                        embed =VCard("Already Verified", "You are already verified! You can access all channels.", tone='success')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


            if verification_method not in ["button","both"]:
                embed =VCard("CAPTCHA Required", "This server requires CAPTCHA verification. Please use the CAPTCHA button below.", tone='warning')
                await interaction .response .send_message (view =embed ,ephemeral =True )
                return 


            card =await finish_verification (
            self .bot ,interaction ,verified_role ,"button"
            )
            if card is None :
                return 
            await interaction .response .send_message (view =card ,ephemeral =True )

        except discord .Forbidden :
            embed =VCard("Verification", "Bot lacks permission to assign roles. Please contact an administrator.", tone='error')
            await interaction .response .send_message (view =embed ,ephemeral =True )
        except Exception as e :
            logger .error (f"Error in verify button: {e}")
            embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            await interaction .response .send_message (view =embed ,ephemeral =True )

    @discord .ui .button (label ="CAPTCHA Verify", emoji=ZSAFE,style =discord .ButtonStyle .primary ,custom_id ="verify_captcha_secure")
    async def verify_captcha (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        try :

            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verified_role_id FROM verification_config WHERE guild_id = ? AND enabled = 1",
                    (interaction .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        embed =VCard("System Unavailable", "Verification system is not configured or disabled.", tone='error')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 

                    verified_role =interaction .guild .get_role (result [0 ])
                    if not verified_role :
                        embed =VCard("Verification", "Verified role not found. Please contact an administrator.", tone='error')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


                    if verified_role in interaction .user .roles :
                        embed =VCard("Already Verified", "You are already verified! You can access all channels.", tone='success')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


            # Checked before the image is built: otherwise a too-new
            # account gets a CAPTCHA in its DMs and is only told no
            # after solving it.
            async with aiosqlite .connect (DATABASE_PATH )as db :
                settings =await verify_store .get_settings (db ,interaction .guild .id )
            created =getattr (interaction .user ,"created_at",None )
            if created is not None :
                age_days =(datetime .now (timezone .utc )-created ).total_seconds ()/86400
                if verify_store .account_too_young (settings ,age_days ):
                    await interaction .response .send_message (
                    view =VCard (
                    "Konto zu neu",
                    f"Dein Discord-Konto muss mindestens "
                    f"**{settings['min_account_age_days']} Tage** alt sein.",
                    tone ='error',
                    ),
                    ephemeral =True ,
                    )
                    return 

            captcha_code =self .generate_captcha_code ()
            captcha_image =self .create_captcha_image (captcha_code )

            try :

                file =discord .File (captcha_image ,filename ="captcha.png")

                # A dropdown of near-miss codes instead of a modal:
                # typing six characters is the part people get wrong,
                # and the modal gave no feedback until it was submitted.
                choices =verify_store .captcha_options (
                captcha_code ,settings .get ("captcha_choices",5 ),
                )
                view =CaptchaChoiceView (
                self .bot ,captcha_code ,interaction .guild .id ,choices ,
                )

                card =CaptchaCard (
                guild_name =interaction .guild .name ,
                buttons =[],
                select =view .children [0 ],
                )
                await interaction .user .send (view =card ,file =file )


                embed =VCard("Schau in deine DMs",
                "Ich habe dir das CAPTCHA privat geschickt.\n\n"
                "**So geht's:**\n"
                "1. Öffne meine Direktnachricht\n"
                "2. Sieh dir das Bild an\n"
                "3. Wähl den passenden Code aus der Liste\n\n"
                "Falls nichts ankommt, sind deine DMs für diesen Server zu.",
                tone='info')
                await interaction .response .send_message (view =embed ,ephemeral =True )

            except discord .Forbidden :
                embed =VCard("DMs Disabled", "I couldn't send you a DM! Please enable DMs from server members and try again.\n\n"
                f"**How to enable DMs:**\n"
                f"1. Right-click on **{interaction.guild.name}**\n"
                f"2. Go to **Privacy Settings**\n"
                f"3. Enable **Direct Messages**\n"
                f"4. Try verification again", tone='error')
                await interaction .response .send_message (view =embed ,ephemeral =True )

        except Exception as e :
            logger .error (f"Error in verify captcha: {e}")
            embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            await interaction .response .send_message (view =embed ,ephemeral =True )

    def generate_captcha_code (self )->str :
        """Generate a random 6-character alphanumeric code"""
        return ''.join (random .choices (string .ascii_letters +string .digits ,k =6 ))

    def create_captcha_image (self ,code :str )->io .BytesIO :
        """Create a CAPTCHA image with the given code"""

        width ,height =300 ,120 
        image =Image .new ('RGB',(width ,height ),color ='white')
        draw =ImageDraw .Draw (image )


        for y in range (height ):
            color_value =255 -int ((y /height )*50 )
            for x in range (width ):
                draw .point ((x ,y ),fill =(color_value ,color_value ,255 ))


        for _ in range (200 ):
            x =random .randint (0 ,width )
            y =random .randint (0 ,height )
            draw .point ((x ,y ),fill =(random .randint (150 ,200 ),random .randint (150 ,200 ),random .randint (150 ,200 )))


        for _ in range (8 ):
            x1 =random .randint (0 ,width )
            y1 =random .randint (0 ,height )
            x2 =random .randint (0 ,width )
            y2 =random .randint (0 ,height )
            draw .line ([(x1 ,y1 ),(x2 ,y2 )],fill =(random .randint (100 ,150 ),random .randint (100 ,150 ),random .randint (100 ,150 )),width =2 )


        try :
            font =ImageFont .truetype ("utils/arial.ttf",40 )
        except :
            try :
                font =ImageFont .load_default ()
            except :
                font =None 


        if font :
            bbox =draw .textbbox ((0 ,0 ),code ,font =font )
            text_width =bbox [2 ]-bbox [0 ]
            text_height =bbox [3 ]-bbox [1 ]
        else :
            text_width =len (code )*20 
            text_height =20 

        start_x =(width -text_width )//2 
        start_y =(height -text_height )//2 


        for i ,char in enumerate (code ):
            char_x =start_x +(i *text_width //len (code ))+random .randint (-8 ,8 )
            char_y =start_y +random .randint (-15 ,15 )


            color =(random .randint (0 ,100 ),random .randint (0 ,100 ),random .randint (0 ,100 ))

            if font :
                draw .text ((char_x ,char_y ),char ,fill =color ,font =font )
            else :
                draw .text ((char_x ,char_y ),char ,fill =color )


        draw .rectangle ([(0 ,0 ),(width -1 ,height -1 )],outline ='black',width =2 )


        img_buffer =io .BytesIO ()
        image .save (img_buffer ,format ='PNG',quality =95 )
        img_buffer .seek (0 )

        return img_buffer 



class CaptchaOnlyVerificationView (discord .ui .View ):
    def __init__ (self ,bot ):
        super ().__init__ (timeout =None )
        self .bot =bot 

    @discord .ui .button (label ="Verify with CAPTCHA", emoji=ZSAFE,style =discord .ButtonStyle .primary ,custom_id ="verify_captcha_only")
    async def verify_captcha (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        try :

            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verified_role_id FROM verification_config WHERE guild_id = ? AND enabled = 1",
                    (interaction .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        embed =VCard("System Unavailable", "Verification system is not configured or disabled.", tone='error')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 

                    verified_role =interaction .guild .get_role (result [0 ])
                    if not verified_role :
                        embed =VCard("Verification", "Verified role not found. Please contact an administrator.", tone='error')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


                    if verified_role in interaction .user .roles :
                        embed =VCard("Already Verified", "You are already verified! You can access all channels.", tone='success')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


            # Checked before the image is built: otherwise a too-new
            # account gets a CAPTCHA in its DMs and is only told no
            # after solving it.
            async with aiosqlite .connect (DATABASE_PATH )as db :
                settings =await verify_store .get_settings (db ,interaction .guild .id )
            created =getattr (interaction .user ,"created_at",None )
            if created is not None :
                age_days =(datetime .now (timezone .utc )-created ).total_seconds ()/86400
                if verify_store .account_too_young (settings ,age_days ):
                    await interaction .response .send_message (
                    view =VCard (
                    "Konto zu neu",
                    f"Dein Discord-Konto muss mindestens "
                    f"**{settings['min_account_age_days']} Tage** alt sein.",
                    tone ='error',
                    ),
                    ephemeral =True ,
                    )
                    return 

            captcha_code =self .generate_captcha_code ()
            captcha_image =self .create_captcha_image (captcha_code )

            try :

                file =discord .File (captcha_image ,filename ="captcha.png")

                # A dropdown of near-miss codes instead of a modal:
                # typing six characters is the part people get wrong,
                # and the modal gave no feedback until it was submitted.
                choices =verify_store .captcha_options (
                captcha_code ,settings .get ("captcha_choices",5 ),
                )
                view =CaptchaChoiceView (
                self .bot ,captcha_code ,interaction .guild .id ,choices ,
                )

                card =CaptchaCard (
                guild_name =interaction .guild .name ,
                buttons =[],
                select =view .children [0 ],
                )
                await interaction .user .send (view =card ,file =file )


                embed =VCard("Schau in deine DMs",
                "Ich habe dir das CAPTCHA privat geschickt.\n\n"
                "**So geht's:**\n"
                "1. Öffne meine Direktnachricht\n"
                "2. Sieh dir das Bild an\n"
                "3. Wähl den passenden Code aus der Liste\n\n"
                "Falls nichts ankommt, sind deine DMs für diesen Server zu.",
                tone='info')
                await interaction .response .send_message (view =embed ,ephemeral =True )

            except discord .Forbidden :
                embed =VCard("DMs Disabled", "I couldn't send you a DM! Please enable DMs from server members and try again.\n\n"
                f"**How to enable DMs:**\n"
                f"1. Right-click on **{interaction.guild.name}**\n"
                f"2. Go to **Privacy Settings**\n"
                f"3. Enable **Direct Messages**\n"
                f"4. Try verification again", tone='error')
                await interaction .response .send_message (view =embed ,ephemeral =True )

        except Exception as e :
            logger .error (f"Error in verify captcha: {e}")
            embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            await interaction .response .send_message (view =embed ,ephemeral =True )

    def generate_captcha_code (self )->str :
        """Generate a random 6-character alphanumeric code"""
        return ''.join (random .choices (string .ascii_letters +string .digits ,k =6 ))

    def create_captcha_image (self ,code :str )->io .BytesIO :
        """Create a CAPTCHA image with the given code"""

        width ,height =300 ,120 
        image =Image .new ('RGB',(width ,height ),color ='white')
        draw =ImageDraw .Draw (image )


        for y in range (height ):
            color_value =255 -int ((y /height )*50 )
            for x in range (width ):
                draw .point ((x ,y ),fill =(color_value ,color_value ,255 ))


        for _ in range (200 ):
            x =random .randint (0 ,width )
            y =random .randint (0 ,height )
            draw .point ((x ,y ),fill =(random .randint (150 ,200 ),random .randint (150 ,200 ),random .randint (150 ,200 )))


        for _ in range (8 ):
            x1 =random .randint (0 ,width )
            y1 =random .randint (0 ,height )
            x2 =random .randint (0 ,width )
            y2 =random .randint (0 ,height )
            draw .line ([(x1 ,y1 ),(x2 ,y2 )],fill =(random .randint (100 ,150 ),random .randint (100 ,150 ),random .randint (100 ,150 )),width =2 )


        try :
            font =ImageFont .truetype ("utils/arial.ttf",40 )
        except :
            try :
                font =ImageFont .load_default ()
            except :
                font =None 


        if font :
            bbox =draw .textbbox ((0 ,0 ),code ,font =font )
            text_width =bbox [2 ]-bbox [0 ]
            text_height =bbox [3 ]-bbox [1 ]
        else :
            text_width =len (code )*20 
            text_height =20 

        start_x =(width -text_width )//2 
        start_y =(height -text_height )//2 


        for i ,char in enumerate (code ):
            char_x =start_x +(i *text_width //len (code ))+random .randint (-8 ,8 )
            char_y =start_y +random .randint (-15 ,15 )


            color =(random .randint (0 ,100 ),random .randint (0 ,100 ),random .randint (0 ,100 ))

            if font :
                draw .text ((char_x ,char_y ),char ,fill =color ,font =font )
            else :
                draw .text ((char_x ,char_y ),char ,fill =color )


        draw .rectangle ([(0 ,0 ),(width -1 ,height -1 )],outline ='black',width =2 )


        img_buffer =io .BytesIO ()
        image .save (img_buffer ,format ='PNG',quality =95 )
        img_buffer .seek (0 )

        return img_buffer 

class CaptchaChoiceSelect (discord .ui .Select ):
    """
    The answers to a CAPTCHA, as a dropdown.

    Typing a six-character code is the part people get wrong, especially
    on a phone -- and the modal offered no feedback until it was
    submitted. The decoys are near-misses of the real code, so the
    answer is not obvious from shape alone.
    """

    def __init__ (self ,bot ,code :str ,guild_id :int ,options :list ):
        super ().__init__ (
        placeholder ="Welcher Code steht im Bild?",
        min_values =1 ,
        max_values =1 ,
        options =[
        discord .SelectOption (label =value ,value =value )
        for value in options [:25 ]
        ],
        )
        self .bot =bot 
        self .code =code 
        self .guild_id =guild_id 

    async def callback (self ,interaction :discord .Interaction ):
        chosen =self .values [0 ]

        if chosen !=self .code :
            # The whole view is retired on a wrong answer: leaving it
            # live would turn a one-in-five guess into unlimited tries.
            for child in self .view .children :
                child .disabled =True 
            try :
                await interaction .response .edit_message (view =self .view )
            except discord .HTTPException :
                pass 
            await interaction .followup .send (
            view =VCard (
            "Falscher Code",
            "Das war nicht der Code aus dem Bild.\n"
            "Geh zurück in den Server und starte die Verifizierung neu.",
            tone ='error',
            ),
            ephemeral =True ,
            )
            return 

        guild =self .bot .get_guild (self .guild_id )
        if guild is None :
            await interaction .response .send_message (
            view =VCard ("Fehler","Den Server finde ich nicht mehr.",tone ='error'),
            )
            return 

        member =guild .get_member (interaction .user .id )
        if member is None :
            await interaction .response .send_message (
            view =VCard ("Fehler","Du bist nicht mehr auf dem Server.",tone ='error'),
            )
            return 

        async with aiosqlite .connect (DATABASE_PATH )as db :
            settings =await verify_store .get_settings (db ,guild .id )

        role_id =settings .get ("verified_role_id")
        role =guild .get_role (int (role_id ))if role_id else None 
        if role is None :
            await interaction .response .send_message (
            view =VCard ("Fehler","Die Rolle gibt es nicht mehr.",tone ='error'),
            )
            return 

        if role in member .roles :
            await interaction .response .send_message (
            view =VCard ("Schon erledigt","Du bist bereits verifiziert.",tone ='success'),
            )
            return 

        for child in self .view .children :
            child .disabled =True 
        try :
            await interaction .response .edit_message (view =self .view )
        except discord .HTTPException :
            pass 

        proxy =_MemberInteraction (interaction ,guild ,member )
        card =await finish_verification (self .bot ,proxy ,role ,"captcha")
        if card is None :
            return 
        await interaction .followup .send (view =card )


class CaptchaChoiceView (discord .ui .View ):
    """The dropdown on its own, sent with the CAPTCHA image."""

    def __init__ (self ,bot ,code :str ,guild_id :int ,options :list ):
        super ().__init__ (timeout =600 )
        self .add_item (CaptchaChoiceSelect (bot ,code ,guild_id ,options ))


class CaptchaModalView (discord .ui .View ):
    def __init__ (self ,modal :VerificationModal ):
        super ().__init__ (timeout =600 )
        self .modal =modal 

    @discord .ui .button (label ="Enter Code", emoji=ZSAFE,style =discord .ButtonStyle .secondary ,custom_id ="enter_captcha_code")
    async def enter_captcha (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        await interaction .response .send_modal (self .modal )

class VerificationSetupView (discord .ui .View ):
    def __init__ (self ,bot ,ctx ):
        super ().__init__ (timeout =300 )
        self .bot =bot 
        self .ctx =ctx 
        self .verification_channel =None 
        self .log_channel =None 
        self .verification_method ="both"

    @discord .ui .select (
    cls =discord .ui .ChannelSelect ,
    channel_types =[discord .ChannelType .text ],
    placeholder ="Select verification channel..."
    )
    async def verification_channel_select (self ,interaction :discord .Interaction ,select :discord .ui .ChannelSelect ):
        await interaction .response .defer ()
        selected_channel =select .values [0 ]
        self .verification_channel =interaction .guild .get_channel (selected_channel .id )

    @discord .ui .select (
    cls =discord .ui .ChannelSelect ,
    channel_types =[discord .ChannelType .text ],
    placeholder ="Select log channel (optional)..."
    )
    async def log_channel_select (self ,interaction :discord .Interaction ,select :discord .ui .ChannelSelect ):
        await interaction .response .defer ()
        selected_channel =select .values [0 ]
        self .log_channel =interaction .guild .get_channel (selected_channel .id )

    @discord .ui .select (
    placeholder ="Select verification method...",
    options =[
    discord .SelectOption (
    label ="Quick Button Only",
    value ="button",
    description ="Users verify instantly by clicking a button"
    ),
    discord .SelectOption (
    label ="CAPTCHA Only",
    value ="captcha",
    description ="Users must solve a CAPTCHA (more secure)"
    ),
    discord .SelectOption (
    label ="Both Methods",
    value ="both",
    description ="Users can choose between button or CAPTCHA"
    )
    ]
    )
    async def method_select (self ,interaction :discord .Interaction ,select :discord .ui .Select ):
        await interaction .response .defer ()
        self .verification_method =select .values [0 ]

    @discord .ui .button (label ="Setup Verification System", emoji=ZSAFE,style =discord .ButtonStyle .green )
    async def setup_verification (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        if not self .verification_channel :
            embed =VCard("Missing Configuration", "Please select a verification channel first!", tone='error')
            await interaction .response .send_message (view =embed ,ephemeral =True )
            return 

        try :
            await interaction .response .defer (ephemeral =True )


            verified_role =await create_verified_role (interaction .guild )


            failed_count =await auto_fix_permissions (interaction .guild ,self .verification_channel ,verified_role )


            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    """INSERT OR REPLACE INTO verification_config 
                           (guild_id, verification_channel_id, verified_role_id, log_channel_id, verification_method, enabled) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                    interaction .guild .id ,
                    self .verification_channel .id ,
                    verified_role .id ,
                    self .log_channel .id if self .log_channel else None ,
                    self .verification_method ,
                    True 
                    )
                    )
                    await db .commit ()


            await self .send_verification_panel (verified_role )


            try :
                await asyncio .sleep (5 )
                if hasattr (interaction ,'message')and interaction .message :
                    await interaction .message .delete ()
            except discord .NotFound :
                pass 
            except discord .Forbidden :
                pass 
            except Exception as e :
                logger .error (f"Error deleting setup embed: {e}")


            security_features =(
            "• All channels made private to unverified users\n"
            "• Verification channel locked for unverified users\n"
            "• Auto-message deletion in the verification channel\n"
            "• DM-based CAPTCHA system\n"
            "• Comprehensive logging enabled"
            )

            if failed_count >0 :
                security_features +=(
                f"\n\n**Note:** {failed_count} channels could not be adjusted "
                "automatically because of missing permissions."
                )

            embed =VCard (
            "Verification system is ready",
            f"The panel has been posted in {self.verification_channel.mention}.",
            security_features ,
            tone ="success",
            )

            await interaction .followup .send (view =embed ,ephemeral =True )


            try :
                await asyncio .sleep (3 )
                if hasattr (interaction ,'message')and interaction .message :
                    await interaction .message .delete ()
            except discord .NotFound :
                pass 
            except discord .Forbidden :
                pass 
            except Exception as e :
                logger .error (f"Error deleting setup embed: {e}")

            self .stop ()

        except Exception as e :
            logger .error (f"Error setting up verification: {e}")
            embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            await interaction .followup .send (view =embed ,ephemeral =True )

    async def send_verification_panel (self ,verified_role :discord .Role ):
        """Send the verification panel to the verification channel"""
        try :
            channel =self .verification_channel 

            methods =[]
            if self .verification_method in ["button","both"]:
                methods .append ("**Quick Verify** — instant access with one click.")
            if self .verification_method in ["captcha","both"]:
                methods .append ("**CAPTCHA Verify** — solve a short code sent by DM.")

            if self .verification_method =="button":
                buttons =ButtonOnlyVerificationView (self .bot )
            elif self .verification_method =="captcha":
                buttons =CaptchaOnlyVerificationView (self .bot )
            else :
                buttons =VerificationView (self .bot )

            # Components V2: the panel and its buttons live in one container,
            # so the accent bar wraps the whole thing instead of the buttons
            # hanging underneath a separate embed.
            panel =VerificationPanel (
            guild_name =channel .guild .name ,
            methods =methods ,
            role_name =verified_role .name ,
            buttons =list (buttons .children ),
            )

            await channel .send (view =panel )

        except Exception as e :
            logger .error (f"Error sending verification panel: {e}")

class ButtonOnlyVerificationView (discord .ui .View ):
    def __init__ (self ,bot ):
        super ().__init__ (timeout =None )
        self .bot =bot 

    @discord .ui .button (label ="Verify Now", emoji=ZSAFE,style =discord .ButtonStyle .green ,custom_id ="verify_button_only")
    async def verify_button (self ,interaction :discord .Interaction ,button :discord .ui .Button ):
        try :

            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verified_role_id, verification_method FROM verification_config WHERE guild_id = ? AND enabled = 1",
                    (interaction .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        embed =VCard("System Unavailable", "Verification system is not configured or disabled.", tone='error')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 

                    verified_role =interaction .guild .get_role (result [0 ])
                    verification_method =result [1 ]

                    if not verified_role :
                        embed =VCard("Verification", "Verified role not found. Please contact an administrator.", tone='error')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


                    if verified_role in interaction .user .roles :
                        embed =VCard("Already Verified", "You are already verified! You can access all channels.", tone='success')
                        await interaction .response .send_message (view =embed ,ephemeral =True )
                        return 


            card =await finish_verification (
            self .bot ,interaction ,verified_role ,"button"
            )
            if card is None :
                return 
            await interaction .response .send_message (view =card ,ephemeral =True )

        except discord .Forbidden :
            embed =VCard("Verification", "Bot lacks permission to assign roles. Please contact an administrator.", tone='error')
            await interaction .response .send_message (view =embed ,ephemeral =True )
        except Exception as e :
            logger .error (f"Error in verify button: {e}")
            embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            await interaction .response .send_message (view =embed ,ephemeral =True )

class Verification (commands .Cog ):
    def __init__ (self ,bot ):
        self .bot =bot 
        asyncio.create_task(self .create_tables ())

        self .bot .add_view (VerificationView (self .bot ))
        self .bot .add_view (ButtonOnlyVerificationView (self .bot ))
        self .bot .add_view (CaptchaOnlyVerificationView (self .bot ))

    async def refresh(self, guild_id=None):
        """
        Called by the dashboard after it saves.

        Nothing is cached in memory -- every read goes to the store --
        so this only exists so the API's reload hook finds something.
        A missing hook fails silently and looks exactly like "the
        dashboard saves but Discord ignores it".
        """
        return True

    async def settings(self, guild_id: int) -> dict:
        """The configuration for one server, defaults filled in."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            return await verify_store.get_settings(db, int(guild_id))

    def build_panel(self, guild, settings: dict, role=None, preview: bool = False):
        """
        The public panel, built from the configured texts.

        Shared with the dashboard's "post" and "preview" actions so the
        preview cannot drift away from what actually gets posted --
        a second renderer is how a preview starts lying.
        """
        role_name = f"@{role.name}" if role is not None else "@Verifiziert"

        def fill(key):
            return verify_store.render(
                settings.get(key, ""),
                server=getattr(guild, "name", ""),
                user_mention="@Lena" if preview else "",
                user_name="Lena" if preview else "",
                role=role_name,
                member_count=getattr(guild, "member_count", 0) or 0,
            )

        methods = verify_store.methods_for(settings)
        if preview:
            # Dead buttons: a preview that hands out roles is not a
            # preview. Unique custom_ids so they cannot collide with the
            # live panel's persistent handlers either.
            buttons = []
            if "button" in methods:
                buttons.append(discord.ui.Button(
                    label=settings.get("button_label") or "Verifizieren",
                    style=discord.ButtonStyle.green,
                    custom_id="verify_preview_button", disabled=True,
                ))
            if "captcha" in methods:
                buttons.append(discord.ui.Button(
                    label=settings.get("captcha_label") or "Mit CAPTCHA",
                    style=discord.ButtonStyle.primary,
                    custom_id="verify_preview_captcha", disabled=True,
                ))
        else:
            if methods == ["button"]:
                view = ButtonOnlyVerificationView(self.bot)
            elif methods == ["captcha"]:
                view = CaptchaOnlyVerificationView(self.bot)
            else:
                view = VerificationView(self.bot)

            buttons = list(view.children)
            # The labels are configurable; the custom_ids are not, because
            # those are what make the panel survive a restart.
            for child in buttons:
                if getattr(child, "custom_id", "") in (
                    "verify_button_quick", "verify_button_only",
                ):
                    child.label = (settings.get("button_label")
                                   or "Verifizieren")[:80]
                elif getattr(child, "custom_id", "") in (
                    "verify_captcha_secure", "verify_captcha_only",
                ):
                    child.label = (settings.get("captcha_label")
                                   or "Mit CAPTCHA")[:80]

        sections = [fill("panel_text")]
        footer = fill("panel_footer")
        if footer.strip():
            sections.append(footer)
        if preview:
            sections.append("*Vorschau — die Knöpfe sind hier ohne Funktion.*")

        return ConfigurablePanel(
            title=fill("panel_title"),
            sections=sections,
            buttons=buttons,
        )

    async def create_tables (self ):
        """Create database tables for verification system"""
        try :
            async with aiosqlite .connect (DATABASE_PATH )as db :
                await db .execute ("""
                    CREATE TABLE IF NOT EXISTS verification_config (
                        guild_id INTEGER PRIMARY KEY,
                        verification_channel_id INTEGER NOT NULL,
                        verified_role_id INTEGER NOT NULL,
                        log_channel_id INTEGER,
                        verification_method TEXT DEFAULT 'both',
                        enabled BOOLEAN DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await db .execute ("""
                    CREATE TABLE IF NOT EXISTS verification_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        verification_method TEXT NOT NULL,
                        verified_at TEXT NOT NULL,
                        FOREIGN KEY (guild_id) REFERENCES verification_config (guild_id)
                    )
                """)

                await db .commit ()
                pass 
        except Exception as e :
            logger .error (f"Error creating verification tables: {e}")

    @commands .Cog .listener ()
    async def on_message (self ,message ):
        """Auto-delete messages in verification channel from non-bot users"""
        # DMs have no guild. This read message.guild.id straight away, so
        # every direct message the bot received raised AttributeError
        # before the handler could return.
        if message .guild is None or message .author .bot :
            return 

        try :
            settings =await self .settings (message .guild .id )

            if not settings ["enabled"]or not settings ["delete_messages"]:
                return 
            if message .channel .id !=settings ["verification_channel_id"]:
                return 
            if message .author .guild_permissions .manage_messages :
                return 

            try :
                await message .delete ()
            except (discord .Forbidden ,discord .NotFound ):
                return 

            # Telling people off in their DMs is now optional: on a busy
            # server this fires constantly and cannot be muted.
            if not settings ["dm_on_delete"]:
                return 

            embed =VCard(
            "Nachricht gelöscht",
            "Dieser Kanal ist nur zum Verifizieren. Nutze bitte die Knöpfe.",
            tone ='warning',
            )
            try :
                await message .author .send (view =embed )
            except (discord .Forbidden ,discord .HTTPException ):
                pass 
        except Exception as e :
            logger .error (f"Error in verification message handler: {e}")

    @commands .hybrid_group (name ="verification",invoke_without_command =True ,description ="Advanced verification system management.", with_app_command=False)
    @commands .has_permissions (administrator =True )
    async def verification (self ,ctx ):
        await ctx .send_help (ctx .command )

    # `verification setup` gibt es nicht mehr -- auf Wunsch entfernt.
    #
    # Die Verifizierung wird im Dashboard eingerichtet (Reiter
    # "Verify"): Kanal, Rolle und Methode lassen sich dort einzeln
    # ändern, der Chat-Assistent konnte nur alles am Stück.
    #
    # `VerificationSetupView` bleibt stehen -- sie hatte hier ihren
    # einzigen Aufrufer, aber das Aufräumen gehört nicht in einen
    # Commit, der einen Befehl entfernt.
    #
    # Die übrigen /verification-Befehle (status, reset, ...) bleiben.

    @verification .command (name ="status",description ="Check verification system status and analytics.")
    @blacklist_check ()
    @ignore_check ()
    @commands .has_permissions (administrator =True )
    async def verification_status (self ,ctx ):
        try :
            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    """SELECT verification_channel_id, verified_role_id, log_channel_id, 
                                  verification_method, enabled FROM verification_config 
                           WHERE guild_id = ?""",
                    (ctx .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        embed =VCard("Not Configured", "Verification system is not set up. Use `/verification setup` to get started!", tone='error')
                        await ctx .send (view =embed )
                        return 

                    verification_channel =ctx .guild .get_channel (result [0 ])
                    verified_role =ctx .guild .get_role (result [1 ])
                    log_channel =ctx .guild .get_channel (result [2 ])if result [2 ]else None 
                    verification_method =result [3 ]
                    enabled =result [4 ]


                    await cur .execute (
                    "SELECT COUNT(*) FROM verification_logs WHERE guild_id = ?",
                    (ctx .guild .id ,)
                    )
                    total_verifications =(await cur .fetchone ())[0 ]

                    await cur .execute (
                    """SELECT verification_method, COUNT(*) FROM verification_logs 
                           WHERE guild_id = ? GROUP BY verification_method""",
                    (ctx .guild .id ,)
                    )
                    method_stats =await cur .fetchall ()


                    yesterday =utc_to_ist (discord .utils .utcnow ())-timedelta (days =1 )
                    await cur .execute (
                    "SELECT COUNT(*) FROM verification_logs WHERE guild_id = ? AND verified_at > ?",
                    (ctx .guild .id ,yesterday .isoformat ())
                    )
                    recent_verifications =(await cur .fetchone ())[0 ]


            issues =[]
            if not verification_channel :
                issues .append ("Verification channel not found")
            if not verified_role :
                issues .append ("Verified role not found")
            elif not validate_role_hierarchy (ctx .guild ,verified_role ):
                issues .append ("Bot cannot manage verified role (role hierarchy)")

            missing_perms =await check_bot_permissions (ctx .guild ,verification_channel )
            if missing_perms ['guild']:
                issues .append (f"Missing server permissions: {', '.join(missing_perms['guild'])}")
            if missing_perms ['channel']:
                issues .append (f"Missing channel permissions: {', '.join(missing_perms['channel'])}")

            if not enabled :
                tone ="warning"
                status_text ="Disabled"
            elif issues :
                tone ="warning"
                status_text ="Operational with issues"
            else :
                tone ="success"
                status_text ="Fully operational"

            overview =(
            f"**Status:** {status_text}\n"
            f"**Method:** {str(verification_method).title()}\n"
            f"**Channel:** {verification_channel.mention if verification_channel else 'not found'}\n"
            f"**Role:** {verified_role.mention if verified_role else 'not found'}\n"
            f"**Logs:** {log_channel.mention if log_channel else 'not set'}"
            )

            numbers =(
            f"**Total verified:** {total_verifications}\n"
            f"**Last 24 hours:** {recent_verifications}"
            )
            if method_stats :
                numbers +="\n"+"\n".join (
                f"**{str(method).title()}:** {count}"for method ,count in method_stats 
                )

            sections =[overview ,numbers ]
            if issues :
                sections .append (
                "**Needs attention**\n"+"\n".join (f"• {i}"for i in issues )
                +"\n\nRun `verification fix` to repair channel permissions."
                )

            embed =VCard ("Verification System Status",*sections ,tone =tone )
            await ctx .send (view =embed )

        except Exception as e :
            logger .error (f"Error checking verification status: {e}")
            embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            await ctx .send (view =embed )

    @verification .command (name ="fix",description ="Auto-fix channel permissions for verification system.")
    @blacklist_check ()
    @ignore_check ()
    @commands .has_permissions (administrator =True )
    async def verification_fix (self ,ctx ):
        try :
            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verification_channel_id, verified_role_id FROM verification_config WHERE guild_id = ? AND enabled = 1",
                    (ctx .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        embed =VCard("Not Configured", "Verification system is not set up or disabled.", tone='error')
                        await ctx .send (view =embed )
                        return 

                    verification_channel =ctx .guild .get_channel (result [0 ])
                    verified_role =ctx .guild .get_role (result [1 ])

                    if not verification_channel or not verified_role :
                        embed =VCard("Verification", "Verification channel or role not found.", tone='error')
                        await ctx .send (view =embed )
                        return 


            failed_count =await auto_fix_permissions (ctx .guild ,verification_channel ,verified_role )

            if failed_count ==-1 :
                embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            elif failed_count >0 :
                embed =VCard("Permissions Partially Fixed", f"Permissions have been auto-fixed for most channels.\n"
                f"{failed_count} channels couldn't be fixed due to permission restrictions.", tone='warning')
            else :
                embed =VCard("Permissions Fixed", "All channel permissions have been auto-fixed successfully!", tone='success')

            await ctx .send (view =embed )

        except Exception as e :
            logger .error (f"Error fixing verification permissions: {e}")
            embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            await ctx .send (view =embed )

    @verification .command (name ="disable",description ="Disable the verification system and reset all channel permissions.")
    @blacklist_check ()
    @ignore_check ()
    @commands .has_permissions (administrator =True )
    async def verification_disable (self ,ctx ):
        try :
            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verification_channel_id, verified_role_id FROM verification_config WHERE guild_id = ?",
                    (ctx .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        await ctx .send ("Verification system is not set up.")
                        return 


                    await cur .execute (
                    "UPDATE verification_config SET enabled = 0 WHERE guild_id = ?",
                    (ctx .guild .id ,)
                    )
                    await db .commit ()


            verification_channel =ctx .guild .get_channel (result [0 ])if result [0 ]else None 
            verified_role =ctx .guild .get_role (result [1 ])if result [1 ]else None 
            everyone_role =ctx .guild .default_role 
            count =0 
            failed_count =0 


            for channel in ctx .guild .channels :
                if isinstance (channel ,(discord .TextChannel ,discord .VoiceChannel ,discord .CategoryChannel )):
                    try :

                        overwrites =channel .overwrites .copy ()


                        if everyone_role in overwrites :
                            del overwrites [everyone_role ]
                        if verified_role and verified_role in overwrites :
                            del overwrites [verified_role ]


                        await channel .edit (overwrites =overwrites ,reason ="Verification system disabled - restoring public access")
                        count +=1 
                    except discord .Forbidden :
                        failed_count +=1 
                    except Exception as e :
                        logger .error (f"Error resetting permissions for channel {channel.name}: {e}")
                        failed_count +=1 

            embed =VCard("Verification System Disabled", f"The verification system has been disabled and all channels have been reset to public access.\n\n"
            f"**Channels Reset:** {count}\n"
            f"**Failed to Reset:** {failed_count}"+(f" (due to permission restrictions)"if failed_count >0 else ""), tone='success')
            await ctx .send (view =embed )

        except Exception as e :
            logger .error (f"Error disabling verification: {e}")
            embed =VCard("Something went wrong", "The action could not be completed. Please try again.", tone='error')
            await ctx .send (view =embed )

    @verification .command (name ="enable",description ="Enable the verification system.")
    @blacklist_check ()
    @ignore_check ()
    @commands .has_permissions (administrator =True )
    async def verification_enable (self ,ctx ):
        try :
            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verified_role_id FROM verification_config WHERE guild_id = ?",
                    (ctx .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        await ctx .send ("Verification system is not set up. Use `/verification setup` first.")
                        return 


                    verified_role =ctx .guild .get_role (result [0 ])
                    if not verified_role :
                        await ctx .send ("Verified role no longer exists. Please run setup again.")
                        return 

                    if not validate_role_hierarchy (ctx .guild ,verified_role ):
                        await ctx .send ("Bot cannot manage the verified role due to role hierarchy. Please fix role positions.")
                        return 


                    missing_perms =await check_bot_permissions (ctx .guild )
                    if missing_perms ['guild']:
                        await ctx .send (
                        f"Bot is missing required permissions: "
                        f"{', '.join(missing_perms['guild'])}. Please grant these permissions first."
                        )
                        return 

                    await cur .execute (
                    "UPDATE verification_config SET enabled = 1 WHERE guild_id = ?",
                    (ctx .guild .id ,)
                    )
                    await db .commit ()

            embed =VCard("Verification System Enabled", "The verification system has been enabled.", tone='success')
            await ctx .send (view =embed )

        except Exception as e :
            logger .error (f"Error enabling verification: {e}")
            pass 

    @verification .command (name ="logs",description ="View recent verification logs.")
    @blacklist_check ()
    @ignore_check ()
    @commands .has_permissions (administrator =True )
    async def verification_logs (self ,ctx ,limit :int =10 ):
        try :
            if limit >50 :
                limit =50 

            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    """SELECT user_id, verification_method, verified_at 
                           FROM verification_logs WHERE guild_id = ? 
                           ORDER BY verified_at DESC LIMIT ?""",
                    (ctx .guild .id ,limit )
                    )
                    logs =await cur .fetchall ()

                    if not logs :
                        await ctx .send ("No verification logs found.")
                        return 

            log_text =""
            for user_id ,method ,verified_at in logs :
                user =ctx .guild .get_member (user_id )
                user_name =user .display_name if user else f"Unknown User ({user_id})"
                log_text +=f"**{user_name}** — {method.upper()} — {verified_at}\n"

            await ctx .send (view =VCard (
            f"Recent verifications ({len(logs)})",log_text ,tone ="info"))

        except Exception as e :
            logger .error (f"Error retrieving verification logs: {e}")
            pass 

    @verification .command (name ="reset",description ="Reset all channel permissions (remove verification restrictions).")
    @blacklist_check ()
    @ignore_check ()
    @commands .has_permissions (administrator =True )
    async def verification_reset (self ,ctx ):
        try :
            view =discord .ui .View (timeout =60 )

            async def confirm_reset (interaction ):
                if interaction .user !=ctx .author :
                    await interaction .response .send_message ("This action is not for you!",ephemeral =True )
                    return 

                await interaction .response .defer ()


                everyone_role =ctx .guild .default_role 
                count =0 
                failed_count =0 

                for channel in ctx .guild .channels :
                    if isinstance (channel ,(discord .TextChannel ,discord .VoiceChannel ,discord .CategoryChannel )):
                        try :
                            await channel .set_permissions (
                            everyone_role ,
                            overwrite =None ,
                            reason ="Verification system reset"
                            )
                            count +=1 
                        except discord .Forbidden :
                            failed_count +=1 

                success_embed =VCard("Permissions Reset Complete", f"Successfully reset permissions for {count} channels.\n"
                f"{f'Failed to reset {failed_count} channels due to permission restrictions.' if failed_count > 0 else ''}\n\n"
                f"The verification system configuration has been preserved.\n"
                f"You can re-enable restrictions using `/verification setup`.", tone='success')
                await interaction .edit_original_response (view =success_embed )

            async def cancel_reset (interaction ):
                if interaction .user !=ctx .author :
                    await interaction .response .send_message ("This action is not for you!",ephemeral =True )
                    return 
                # A V2 layout cannot be mixed with `content`, so the cancel
                # state is a card as well.
                await interaction .response .edit_message (
                view =VCard ("Reset cancelled","No permissions were changed.",tone ="info"))

            confirm_button =discord .ui .Button (label ="Confirm Reset", emoji=WARNING,style =discord .ButtonStyle .red )
            cancel_button =discord .ui .Button (label ="Cancel", emoji=CROSS,style =discord .ButtonStyle .grey )

            confirm_button .callback =confirm_reset 
            cancel_button .callback =cancel_reset 

            view .add_item (confirm_button )
            view .add_item (cancel_button )

            # The warning text and the buttons belong to the same container,
            # otherwise the confirmation prompt shows bare buttons with no
            # explanation of what is about to happen.
            confirm_card =LayoutView (timeout =60 )
            confirm_card .add_item (build_container (
            TextDisplay ("### !  Reset channel permissions"),
            Separator (visible =True ),
            TextDisplay (
            "This removes every verification-related channel restriction.\n\n"
            "**This cannot be undone** and may take a while. All channels "
            "become visible to @everyone again."
            ),
            Separator (visible =True ),
            ActionRow (confirm_button ,cancel_button ),
            accent_color =TONE_COLORS ["warning"],
            ))

            await ctx .send (view =confirm_card )

        except Exception as e :
            logger .error (f"Error in verification reset: {e}")
            pass 

    @verification .command (name ="verify",description ="Manually verify a user (Admin only).")
    @blacklist_check ()
    @ignore_check ()
    @commands .has_permissions (administrator =True )
    async def verification_verify (self ,ctx ,user :discord .Member ):
        try :
            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    await cur .execute (
                    "SELECT verified_role_id FROM verification_config WHERE guild_id = ? AND enabled = 1",
                    (ctx .guild .id ,)
                    )
                    result =await cur .fetchone ()

                    if not result :
                        await ctx .send ("Verification system is not set up or disabled.")
                        return 

                    verified_role =ctx .guild .get_role (result [0 ])
                    if not verified_role :
                        await ctx .send ("Verified role not found.")
                        return 

                    if not validate_role_hierarchy (ctx .guild ,verified_role ):
                        await ctx .send ("Bot cannot manage the verified role due to role hierarchy.")
                        return 

                    if verified_role in user .roles :
                        await ctx .send (f"{user.mention} is already verified.")
                        return 


            if not ctx .guild .me .guild_permissions .manage_roles :
                await ctx .send ("Bot lacks 'Manage Roles' permission.")
                return 


            await user .add_roles (verified_role ,reason =f"Manual verification by {ctx.author}")


            async with aiosqlite .connect (DATABASE_PATH )as db :
                async with db .cursor ()as cur :
                    current_time =utc_to_ist (discord .utils .utcnow ())
                    await cur .execute (
                    "INSERT INTO verification_logs (guild_id, user_id, verification_method, verified_at) VALUES (?, ?, ?, ?)",
                    (ctx .guild .id ,user .id ,"manual",current_time .isoformat ())
                    )
                    await db .commit ()

            current_time =utc_to_ist (discord .utils .utcnow ())
            embed =VCard("User Manually Verified", f"{user.mention} has been manually verified by {ctx.author.mention}.", tone='success')
            await ctx .send (view =embed )

        except discord .Forbidden :
            await ctx .send ("Bot lacks permission to assign roles.")
        except Exception as e :
            logger .error (f"Error manually verifying user: {e}")
            pass 

async def setup (bot):
    await bot.add_cog(Verification (bot))
    logger .info ("Advanced verification cog loaded successfully")
