# CloudTIX Bot-Emojis: Grau

249 Symbole auf abgerundeten grauen Kacheln.
Enthält alle ursprünglichen Bot-Symbole sowie Moderation, Server, Tickets,
Regelwerk, Medien, Wirtschaft und Statusmeldungen. Deutsche Namen und Suchbegriffe
stehen im Manifest. Verwandte Aktionen werden durch kleine Statuszeichen unterschieden.
Außerhalb der Kacheln bleibt der Hintergrund transparent.
128 × 128 Pixel, maximal 256 KB. Der Ladeindikator bleibt animiert.
Ausgefüllte Motive: Font Awesome Free 6.7.2 (CC BY 4.0),
[Lizenz](LICENSE.fontawesome.txt). Statuszeichen und ältere Quellen:
[Lucide-Lizenz](LICENSE.lucide.txt). Leuchtende Kacheln im Stil der Referenzbilder.

Beide Sets werden beim Bot-Start automatisch als Application Emojis hochgeladen.
Die zentralen Bot-Konstanten verwenden die farbige Variante. Im Dashboard kann
zwischen Farbe und Grau gewählt werden. Alte IDs werden nicht gelöscht.

```python
from utils.emoji import TICKET, WARNING, ERROR, EMOJIS
await ctx.send(f"{TICKET} Dein Ticket")
await ctx.send(f"{WARNING} Bitte beachten")
# Direkter Zugriff auf die graue Variante:
await ctx.send(EMOJIS["gray_ticket"])
# Direkter Zugriff auf die farbige Variante:
await ctx.send(EMOJIS["vivid_ticket"])
```

Ohne verfügbare Discord-ID greift der Unicode-Fallback. Export:
`python scripts/export_cloudtix_gray_emojis.py --style all`.

| Name | Farbe | Vorschau | Bot-Konstanten |
| --- | --- | --- | --- |
| gray_shield | gray | [Bild](gray_shield.png) | `SHIELD` |
| gray_anti_nuke | yellow | [Bild](gray_anti_nuke.png) | `ANTI_NUKE` |
| gray_automod | gray | [Bild](gray_automod.png) | `AUTOMOD` |
| gray_jail | gray | [Bild](gray_jail.png) | `JAIL`, `LOCK` |
| gray_ticket | gray | [Bild](gray_ticket.png) | `TICKET` |
| gray_verification | gray | [Bild](gray_verification.png) | `VERIFICATION`, `ZSAFE`, `CERTIFIED_MODERATOR` |
| gray_applications | gray | [Bild](gray_applications.png) | `APPLICATIONS` |
| gray_level | gray | [Bild](gray_level.png) | `LEVEL_UP` |
| gray_rank | gray | [Bild](gray_rank.png) | `RANK` |
| gray_giveaway | gray | [Bild](gray_giveaway.png) | `GIVEAWAY`, `ZTADA`, `TADAA`, `CELEBRATE` |
| gray_welcome | gray | [Bild](gray_welcome.png) | `WELCOME` |
| gray_play | gray | [Bild](gray_play.png) | `ZPLAY` |
| gray_pause | gray | [Bild](gray_pause.png) | `ICONS_PAUSE`, `ZMUSICPAUSE`, `ZPAUSE` |
| gray_headphones | gray | [Bild](gray_headphones.png) | `MUSIC`, `ICONS_MUSIC`, `MUSIC_ALT1` |
| gray_volume | gray | [Bild](gray_volume.png) | `VOLUME`, `ZUNMUTE` |
| gray_checkmark | gray | [Bild](gray_checkmark.png) | `TICK`, `TICK_ALT`, `ZTICK`, `SUCCESS`, `ENABLE`, `CHECKMARK`, `OK` |
| gray_cross | red | [Bild](gray_cross.png) | `CROSS`, `CROSS_ALT`, `ML_CROSS`, `ZCROSS`, `ERROR`, `DENIED`, `DISABLE`, `ERROR_UNICODE`, `BLOCK`, `CHECK`, `FAIL`, `NOT_OK`, `CROSS_MARK` |
| gray_arrow | gray | [Bild](gray_arrow.png) | `ZARROW`, `ARROWRED`, `ARROW_RIGHT` |
| gray_info | gray | [Bild](gray_info.png) | `INFO` |
| gray_warning | yellow | [Bild](gray_warning.png) | `WARNING`, `WARNING_ALT`, `ZWARNING`, `ICONS_WARNING`, `ICONS_WARNING_ALT1`, `_37496ALERT`, `WARNING_UNICODE` |
| gray_loading | gray | [Bild](gray_loading.gif) | `LOADING`, `LOADING_ALT1`, `LOADINGRED` |
| gray_back | gray | [Bild](gray_back.png) | `ZBACK`, `ARROW_LEFT` |
| gray_stop | gray | [Bild](gray_stop.png) | `MUSICSTOP_ICONS`, `STOP_BUTTON` |
| gray_skip | gray | [Bild](gray_skip.png) | `NEXT`, `NEXT_ALT1`, `SKIP`, `FORWARD` |
| gray_previous | gray | [Bild](gray_previous.png) | `PREVIOUS` |
| gray_settings | gray | [Bild](gray_settings.png) | `ZSETTINGS` |
| gray_members | gray | [Bild](gray_members.png) | `ZPEOPLE`, `HUMAN`, `ZHUMAN` |
| gray_message | gray | [Bild](gray_message.png) | `MESSAGE` |
| gray_refresh | gray | [Bild](gray_refresh.png) | `REFRESH`, `ICONLOAD` |
| gray_plus | gray | [Bild](gray_plus.png) | `ZPLUS`, `ICONS_PLUS` |
| gray_delete | gray | [Bild](gray_delete.png) | `DELETE`, `DELETE_ALT1` |
| gray_mute | gray | [Bild](gray_mute.png) | `MUTE`, `ZMUTE` |
| gray_unlock | gray | [Bild](gray_unlock.png) | `UNLOCK` |
| gray_star | gray | [Bild](gray_star.png) | `STAR`, `STAR_ALT1`, `STAR_ALT2`, `SYSTEM`, `STAR_UNICODE` |
| gray_cloud | gray | [Bild](gray_cloud.png) | `ZCLOUD` |
| gray_ban | red | [Bild](gray_ban.png) | `ZBAN`, `universitybotHAMMER`, `SWORD` |
| gray_kick | red | [Bild](gray_kick.png) | `KICK` |
| gray_timeout | gray | [Bild](gray_timeout.png) | `TIMER`, `TIMER_ALT1` |
| gray_warn | yellow | [Bild](gray_warn.png) | `WARN` |
| gray_audit_log | gray | [Bild](gray_audit_log.png) | `AUDIT_LOG` |
| gray_permissions | gray | [Bild](gray_permissions.png) | `PERMISSIONS` |
| gray_firewall | gray | [Bild](gray_firewall.png) | `FIREWALL` |
| gray_quarantine | gray | [Bild](gray_quarantine.png) | `QUARANTINE` |
| gray_scan | gray | [Bild](gray_scan.png) | `SCAN` |
| gray_fingerprint | gray | [Bild](gray_fingerprint.png) | `FINGERPRINT` |
| gray_password | gray | [Bild](gray_password.png) | `PASSWORD` |
| gray_incognito | gray | [Bild](gray_incognito.png) | `INCOGNITO` |
| gray_lockdown | red | [Bild](gray_lockdown.png) | `LOCKDOWN`, `LOCK_UNICODE` |
| gray_protection | gray | [Bild](gray_protection.png) | `PROTECTION` |
| gray_report | yellow | [Bild](gray_report.png) | `REPORT` |
| gray_ticket_open | gray | [Bild](gray_ticket_open.png) | `TICKET_OPEN` |
| gray_ticket_close | red | [Bild](gray_ticket_close.png) | `TICKET_CLOSE` |
| gray_ticket_claim | gray | [Bild](gray_ticket_claim.png) | `TICKET_CLAIM` |
| gray_transcript | gray | [Bild](gray_transcript.png) | `TRANSCRIPT`, `PAPER` |
| gray_support | gray | [Bild](gray_support.png) | `SUPPORT`, `HANDSHAKE`, `MINGLE` |
| gray_faq | gray | [Bild](gray_faq.png) | `FAQ` |
| gray_mail | gray | [Bild](gray_mail.png) | `MAIL` |
| gray_inbox | gray | [Bild](gray_inbox.png) | `INBOX` |
| gray_form | gray | [Bild](gray_form.png) | `FORM` |
| gray_accept | gray | [Bild](gray_accept.png) | `ACCEPT` |
| gray_reject | red | [Bild](gray_reject.png) | `REJECT` |
| gray_feedback | gray | [Bild](gray_feedback.png) | `FEEDBACK` |
| gray_boost | gray | [Bild](gray_boost.png) | `ZROCKET`, `BOOST`, `BOOSTS`, `NITRO_BOOST` |
| gray_birthday | gray | [Bild](gray_birthday.png) | `BIRTHDAY` |
| gray_event | gray | [Bild](gray_event.png) | `EVENT` |
| gray_announcement | gray | [Bild](gray_announcement.png) | `ANNOUNCEMENT` |
| gray_invite | gray | [Bild](gray_invite.png) | `INVITE` |
| gray_leave | gray | [Bild](gray_leave.png) | `LEAVE` |
| gray_role | gray | [Bild](gray_role.png) | `ROLE`, `HEADMOD`, `MANAGER`, `U_ADMIN`, `STAFF` |
| gray_leaderboard | gray | [Bild](gray_leaderboard.png) | `LEADERBOARD` |
| gray_xp | gray | [Bild](gray_xp.png) | `XP`, `SPARKLE` |
| gray_poll | gray | [Bild](gray_poll.png) | `POLL` |
| gray_counting | gray | [Bild](gray_counting.png) | `ZCOUNTING` |
| gray_heart | gray | [Bild](gray_heart.png) | `ZDIL`, `HEART_EM`, `HEART3`, `REDHEART`, `EARLY_SUPPORTER`, `HEARTS` |
| gray_game | gray | [Bild](gray_game.png) | `GAMES`, `GAME_CONTROLLER`, `MINECRAFT`, `MAX__A` |
| gray_crown | gray | [Bild](gray_crown.png) | `KING`, `KING_ALT1`, `BLACKCROWN` |
| gray_premium | gray | [Bild](gray_premium.png) | `PREMIUM`, `PARTNER_BADGE` |
| gray_shuffle | gray | [Bild](gray_shuffle.png) | `SHUFFLE` |
| gray_repeat | gray | [Bild](gray_repeat.png) | `REPEAT` |
| gray_repeat_one | gray | [Bild](gray_repeat_one.png) | `REPEAT_ONE` |
| gray_queue | gray | [Bild](gray_queue.png) | `QUEUE` |
| gray_playlist | gray | [Bild](gray_playlist.png) | `PLAYLIST` |
| gray_note | gray | [Bild](gray_note.png) | `MUSIC_NOTE`, `NOTE` |
| gray_microphone | gray | [Bild](gray_microphone.png) | `MICROPHONE` |
| gray_microphone_off | gray | [Bild](gray_microphone_off.png) | `MICROPHONE_OFF` |
| gray_voice | gray | [Bild](gray_voice.png) | `VOICE` |
| gray_equalizer | gray | [Bild](gray_equalizer.png) | `EQUALIZER` |
| gray_seek_forward | gray | [Bild](gray_seek_forward.png) | `SEEK_FORWARD` |
| gray_rewind | gray | [Bild](gray_rewind.png) | `REWIND`, `REWIND_ALT1` |
| gray_home | gray | [Bild](gray_home.png) | `HOME` |
| gray_dashboard | gray | [Bild](gray_dashboard.png) | `DASHBOARD` |
| gray_channel | gray | [Bild](gray_channel.png) | `CHANNEL`, `ICONS_CHANNEL` |
| gray_search | gray | [Bild](gray_search.png) | `universitybot_SEARCH`, `universitybot_CODE`, `universitybot_COMMAND` |
| gray_edit | gray | [Bild](gray_edit.png) | `EDIT` |
| gray_save | gray | [Bild](gray_save.png) | `SAVE` |
| gray_copy | gray | [Bild](gray_copy.png) | `COPY` |
| gray_download | gray | [Bild](gray_download.png) | `DOWNLOAD` |
| gray_upload | gray | [Bild](gray_upload.png) | `UPLOAD` |
| gray_link | gray | [Bild](gray_link.png) | `links`, `universitybotLINKS` |
| gray_external_link | gray | [Bild](gray_external_link.png) | `EXTERNAL_LINK` |
| gray_arrow_up | gray | [Bild](gray_arrow_up.png) | `ARROW_UP` |
| gray_arrow_down | gray | [Bild](gray_arrow_down.png) | `ARROW_DOWN` |
| gray_menu | gray | [Bild](gray_menu.png) | `MENU`, `INDEX` |
| gray_close_panel | gray | [Bild](gray_close_panel.png) | `CLOSE_PANEL` |
| gray_open_panel | gray | [Bild](gray_open_panel.png) | `OPEN_PANEL` |
| gray_notification | gray | [Bild](gray_notification.png) | `NOTIFICATION` |
| gray_pin | gray | [Bild](gray_pin.png) | `PIN`, `RED_PIN` |
| gray_clock | gray | [Bild](gray_clock.png) | `TIME`, `CLOCK` |
| gray_bot | gray | [Bild](gray_bot.png) | `ZBOT`, `universitybotSYS` |
| gray_tools | gray | [Bild](gray_tools.png) | `ZWRENCH`, `TOOLS` |
| gray_bug_hunter | gray | [Bild](gray_bug_hunter.png) | `BUG_HUNTER`, `BUG_HUNTER_LVL2` |
| gray_developer | gray | [Bild](gray_developer.png) | `CODEBASE`, `CODED`, `ACTIVE_DEVELOPER`, `Developer`, `EARLY_VERIFIED_BOT_DEV` |
| gray_hypesquad | gray | [Bild](gray_hypesquad.png) | `HYPESQUAD_BRILLIANCE`, `HYPESQUAD_BALANCE`, `HYPESQUAD_BRAVERY`, `HYPESQUAD_EVENTS` |
| gray_browser | gray | [Bild](gray_browser.png) | `ICON_BROWSER`, `universitybot_GLOBAL` |
| gray_owner | gray | [Bild](gray_owner.png) | `universitybot_OWNER` |
| gray_mention | gray | [Bild](gray_mention.png) | `MENTION`, `MENTION_ALT1` |
| gray_new | gray | [Bild](gray_new.png) | `NEW` |
| gray_pc | gray | [Bild](gray_pc.png) | `PC` |
| gray_mobile | gray | [Bild](gray_mobile.png) | `MOBILE` |
| gray_connection | gray | [Bild](gray_connection.png) | `WIFI`, `UPTIME`, `universitybotCONNECTION` |
| gray_ai | gray | [Bild](gray_ai.png) | `ZAI` |
| gray_module | gray | [Bild](gray_module.png) | `ZMODULE` |
| gray_seed | gray | [Bild](gray_seed.png) | `SEED` |
| gray_thunder | gray | [Bild](gray_thunder.png) | `THUNDER` |
| gray_circle | gray | [Bild](gray_circle.png) | `ZCIRCLE`, `ZCIRCLE_ALT1`, `RED_BUTTON`, `REDDOT` |
| gray_online | gray | [Bild](gray_online.png) | `ONLINE` |
| gray_offline | gray | [Bild](gray_offline.png) | `OFFLINE` |
| gray_idle | yellow | [Bild](gray_idle.png) | `IDLE` |
| gray_dnd | red | [Bild](gray_dnd.png) | `DND` |
| gray_cast | gray | [Bild](gray_cast.png) | `CAST` |
| gray_cute | gray | [Bild](gray_cute.png) | `CUTE_CUTE_CUTE`, `BLOBPART`, `LAUGH1`, `LAUGH2`, `LAUGH3`, `UPSIDE_DOWN`, `TONGUE_OUT` |
| gray_panda | gray | [Bild](gray_panda.png) | `HAPPY_PANDA` |
| gray_dance | gray | [Bild](gray_dance.png) | `HEERIYE`, `SG_RD` |
| gray_sticker | gray | [Bild](gray_sticker.png) | `EMOTE`, `GIFD`, `GIFN` |
| gray_racecar | gray | [Bild](gray_racecar.png) | `RACECAR64` |
| gray_tea | gray | [Bild](gray_tea.png) | `BUBBLE_TEA` |
| gray_cherries | gray | [Bild](gray_cherries.png) | `CHERRIES` |
| gray_cookie | gray | [Bild](gray_cookie.png) | `COOKIE` |
| gray_cursor | gray | [Bild](gray_cursor.png) | `CURSOR` |
| gray_dizzy | gray | [Bild](gray_dizzy.png) | `DIZZY` |
| gray_coffee | gray | [Bild](gray_coffee.png) | `JAVA_COFFEE` |
| gray_money | gray | [Bild](gray_money.png) | `MONEY` |
| gray_moon | gray | [Bild](gray_moon.png) | `MOON` |
| gray_peach | gray | [Bild](gray_peach.png) | `PEACH` |
| gray_rock | gray | [Bild](gray_rock.png) | `ROCK` |
| gray_scissors | gray | [Bild](gray_scissors.png) | `SCISSORS` |
| gray_shocked | gray | [Bild](gray_shocked.png) | `SHOCKED` |
| gray_target | gray | [Bild](gray_target.png) | `TARGET` |
| gray_rules | gray | [Bild](gray_rules.png) | `RULES`, `REGELWERK`, `REDRULESBOOK` |
| gray_guidelines | gray | [Bild](gray_guidelines.png) | `GUIDELINES` |
| gray_rules_accept | gray | [Bild](gray_rules_accept.png) | `RULES_ACCEPT` |
| gray_rules_faq | gray | [Bild](gray_rules_faq.png) | `RULES_FAQ` |
| gray_privacy_policy | gray | [Bild](gray_privacy_policy.png) | `PRIVACY_POLICY` |
| gray_terms | gray | [Bild](gray_terms.png) | `TERMS` |
| gray_changelog | gray | [Bild](gray_changelog.png) | `CHANGELOG` |
| gray_server_info | gray | [Bild](gray_server_info.png) | `SERVER_INFO` |
| gray_exclamation | yellow | [Bild](gray_exclamation.png) | `CATALOG_EXCLAMATION` |
| gray_question | gray | [Bild](gray_question.png) | `CATALOG_QUESTION` |
| gray_globe | gray | [Bild](gray_globe.png) | `CATALOG_GLOBE` |
| gray_globe_languages | gray | [Bild](gray_globe_languages.png) | `CATALOG_GLOBE_LANGUAGES` |
| gray_member | gray | [Bild](gray_member.png) | `CATALOG_MEMBER` |
| gray_member_verified | gray | [Bild](gray_member_verified.png) | `CATALOG_MEMBER_VERIFIED` |
| gray_member_add | gray | [Bild](gray_member_add.png) | `CATALOG_MEMBER_ADD` |
| gray_member_remove | gray | [Bild](gray_member_remove.png) | `CATALOG_MEMBER_REMOVE` |
| gray_member_banned | red | [Bild](gray_member_banned.png) | `CATALOG_MEMBER_BANNED` |
| gray_user_profile | gray | [Bild](gray_user_profile.png) | `CATALOG_USER_PROFILE` |
| gray_text_channel | gray | [Bild](gray_text_channel.png) | `CATALOG_TEXT_CHANNEL` |
| gray_voice_channel | gray | [Bild](gray_voice_channel.png) | `CATALOG_VOICE_CHANNEL` |
| gray_forum_channel | gray | [Bild](gray_forum_channel.png) | `CATALOG_FORUM_CHANNEL` |
| gray_stage_channel | gray | [Bild](gray_stage_channel.png) | `CATALOG_STAGE_CHANNEL` |
| gray_category_folder | gray | [Bild](gray_category_folder.png) | `CATALOG_CATEGORY_FOLDER` |
| gray_thread | gray | [Bild](gray_thread.png) | `CATALOG_THREAD` |
| gray_unban | gray | [Bild](gray_unban.png) | `CATALOG_UNBAN` |
| gray_softban | red | [Bild](gray_softban.png) | `CATALOG_SOFTBAN` |
| gray_tempban | red | [Bild](gray_tempban.png) | `CATALOG_TEMPBAN` |
| gray_mute_member | gray | [Bild](gray_mute_member.png) | `CATALOG_MUTE_MEMBER` |
| gray_unmute_member | gray | [Bild](gray_unmute_member.png) | `CATALOG_UNMUTE_MEMBER` |
| gray_remove_timeout | gray | [Bild](gray_remove_timeout.png) | `CATALOG_REMOVE_TIMEOUT` |
| gray_warn_remove | gray | [Bild](gray_warn_remove.png) | `CATALOG_WARN_REMOVE` |
| gray_warn_list | yellow | [Bild](gray_warn_list.png) | `CATALOG_WARN_LIST` |
| gray_mod_log | gray | [Bild](gray_mod_log.png) | `CATALOG_MOD_LOG` |
| gray_appeal | gray | [Bild](gray_appeal.png) | `CATALOG_APPEAL` |
| gray_evidence | gray | [Bild](gray_evidence.png) | `CATALOG_EVIDENCE` |
| gray_slowmode | gray | [Bild](gray_slowmode.png) | `CATALOG_SLOWMODE` |
| gray_nsfw | gray | [Bild](gray_nsfw.png) | `CATALOG_NSFW` |
| gray_anti_spam | gray | [Bild](gray_anti_spam.png) | `CATALOG_ANTI_SPAM` |
| gray_anti_raid | gray | [Bild](gray_anti_raid.png) | `CATALOG_ANTI_RAID` |
| gray_purge | gray | [Bild](gray_purge.png) | `CATALOG_PURGE` |
| gray_server | gray | [Bild](gray_server.png) | `CATALOG_SERVER` |
| gray_server_settings | gray | [Bild](gray_server_settings.png) | `CATALOG_SERVER_SETTINGS` |
| gray_server_stats | gray | [Bild](gray_server_stats.png) | `CATALOG_SERVER_STATS` |
| gray_server_boost | gray | [Bild](gray_server_boost.png) | `CATALOG_SERVER_BOOST` |
| gray_server_owner | gray | [Bild](gray_server_owner.png) | `CATALOG_SERVER_OWNER` |
| gray_admin | gray | [Bild](gray_admin.png) | `CATALOG_ADMIN` |
| gray_moderator | gray | [Bild](gray_moderator.png) | `CATALOG_MODERATOR` |
| gray_staff | gray | [Bild](gray_staff.png) | `CATALOG_STAFF` |
| gray_newcomer | gray | [Bild](gray_newcomer.png) | `CATALOG_NEWCOMER` |
| gray_bot_add | gray | [Bild](gray_bot_add.png) | `CATALOG_BOT_ADD` |
| gray_server_join | gray | [Bild](gray_server_join.png) | `CATALOG_SERVER_JOIN` |
| gray_server_leave | gray | [Bild](gray_server_leave.png) | `CATALOG_SERVER_LEAVE` |
| gray_goodbye | gray | [Bild](gray_goodbye.png) | `CATALOG_GOODBYE` |
| gray_welcome_wave | gray | [Bild](gray_welcome_wave.png) | `CATALOG_WELCOME_WAVE` |
| gray_bug_report | gray | [Bild](gray_bug_report.png) | `CATALOG_BUG_REPORT` |
| gray_suggestion | gray | [Bild](gray_suggestion.png) | `CATALOG_SUGGESTION` |
| gray_help | gray | [Bild](gray_help.png) | `CATALOG_HELP` |
| gray_ticket_reopen | gray | [Bild](gray_ticket_reopen.png) | `CATALOG_TICKET_REOPEN` |
| gray_ticket_transfer | gray | [Bild](gray_ticket_transfer.png) | `CATALOG_TICKET_TRANSFER` |
| gray_ticket_archive | gray | [Bild](gray_ticket_archive.png) | `CATALOG_TICKET_ARCHIVE` |
| gray_ticket_priority | yellow | [Bild](gray_ticket_priority.png) | `CATALOG_TICKET_PRIORITY` |
| gray_ticket_pending | gray | [Bild](gray_ticket_pending.png) | `CATALOG_TICKET_PENDING` |
| gray_ticket_resolved | gray | [Bild](gray_ticket_resolved.png) | `CATALOG_TICKET_RESOLVED` |
| gray_ticket_category | gray | [Bild](gray_ticket_category.png) | `CATALOG_TICKET_CATEGORY` |
| gray_rules_violation | red | [Bild](gray_rules_violation.png) | `CATALOG_RULES_VIOLATION` |
| gray_rules_update | gray | [Bild](gray_rules_update.png) | `CATALOG_RULES_UPDATE` |
| gray_rules_pending | yellow | [Bild](gray_rules_pending.png) | `CATALOG_RULES_PENDING` |
| gray_age_limit | yellow | [Bild](gray_age_limit.png) | `CATALOG_AGE_LIMIT` |
| gray_agreement | gray | [Bild](gray_agreement.png) | `CATALOG_AGREEMENT` |
| gray_announcement_rules | gray | [Bild](gray_announcement_rules.png) | `CATALOG_ANNOUNCEMENT_RULES` |
| gray_wallet | gray | [Bild](gray_wallet.png) | `CATALOG_WALLET` |
| gray_coins | gray | [Bild](gray_coins.png) | `CATALOG_COINS` |
| gray_bank | gray | [Bild](gray_bank.png) | `CATALOG_BANK` |
| gray_shop | gray | [Bild](gray_shop.png) | `CATALOG_SHOP` |
| gray_cart | gray | [Bild](gray_cart.png) | `CATALOG_CART` |
| gray_reward | gray | [Bild](gray_reward.png) | `CATALOG_REWARD` |
| gray_daily | gray | [Bild](gray_daily.png) | `CATALOG_DAILY` |
| gray_trade | gray | [Bild](gray_trade.png) | `CATALOG_TRADE` |
| gray_inventory | gray | [Bild](gray_inventory.png) | `CATALOG_INVENTORY` |
| gray_receipt | gray | [Bild](gray_receipt.png) | `CATALOG_RECEIPT` |
| gray_party | gray | [Bild](gray_party.png) | `CATALOG_PARTY` |
| gray_fire | gray | [Bild](gray_fire.png) | `CATALOG_FIRE` |
| gray_gift_claim | gray | [Bild](gray_gift_claim.png) | `CATALOG_GIFT_CLAIM` |
| gray_timer_event | gray | [Bild](gray_timer_event.png) | `CATALOG_TIMER_EVENT` |
| gray_image | gray | [Bild](gray_image.png) | `CATALOG_IMAGE` |
| gray_camera | gray | [Bild](gray_camera.png) | `CATALOG_CAMERA` |
| gray_video | gray | [Bild](gray_video.png) | `CATALOG_VIDEO` |
| gray_streaming | gray | [Bild](gray_streaming.png) | `CATALOG_STREAMING` |
| gray_maintenance | yellow | [Bild](gray_maintenance.png) | `CATALOG_MAINTENANCE` |
| gray_outage | red | [Bild](gray_outage.png) | `CATALOG_OUTAGE` |
| gray_scheduled | gray | [Bild](gray_scheduled.png) | `CATALOG_SCHEDULED` |
| gray_complete | gray | [Bild](gray_complete.png) | `CATALOG_COMPLETE` |
| gray_booster | gray | [Bild](gray_booster.png) | `CATALOG_BOOSTER` |
| gray_paint | gray | [Bild](gray_paint.png) | `CATALOG_PAINT` |
| gray_github | gray | [Bild](gray_github.png) | `CATALOG_GITHUB` |
| gray_youtube | gray | [Bild](gray_youtube.png) | `CATALOG_YOUTUBE` |
| gray_partner | gray | [Bild](gray_partner.png) | `CATALOG_PARTNER` |
| gray_supporter | gray | [Bild](gray_supporter.png) | `CATALOG_SUPPORTER` |
| gray_ambassador | gray | [Bild](gray_ambassador.png) | `CATALOG_AMBASSADOR` |
| gray_rocket | gray | [Bild](gray_rocket.png) | `CATALOG_ROCKET` |
| gray_trophy | gray | [Bild](gray_trophy.png) | `CATALOG_TROPHY` |
