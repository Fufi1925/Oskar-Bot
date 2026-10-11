# CloudTIX Bot-Emojis: Farbe

249 Symbole auf abgerundeten farbigen Kacheln.
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
| vivid_shield | security | [Bild](vivid_shield.png) | `SHIELD` |
| vivid_anti_nuke | yellow | [Bild](vivid_anti_nuke.png) | `ANTI_NUKE` |
| vivid_automod | security | [Bild](vivid_automod.png) | `AUTOMOD` |
| vivid_jail | security | [Bild](vivid_jail.png) | `JAIL`, `LOCK` |
| vivid_ticket | support | [Bild](vivid_ticket.png) | `TICKET` |
| vivid_verification | support | [Bild](vivid_verification.png) | `VERIFICATION`, `ZSAFE`, `CERTIFIED_MODERATOR` |
| vivid_applications | support | [Bild](vivid_applications.png) | `APPLICATIONS` |
| vivid_level | community | [Bild](vivid_level.png) | `LEVEL_UP` |
| vivid_rank | community | [Bild](vivid_rank.png) | `RANK` |
| vivid_giveaway | community | [Bild](vivid_giveaway.png) | `GIVEAWAY`, `ZTADA`, `TADAA`, `CELEBRATE` |
| vivid_welcome | community | [Bild](vivid_welcome.png) | `WELCOME` |
| vivid_play | music | [Bild](vivid_play.png) | `ZPLAY` |
| vivid_pause | music | [Bild](vivid_pause.png) | `ICONS_PAUSE`, `ZMUSICPAUSE`, `ZPAUSE` |
| vivid_headphones | music | [Bild](vivid_headphones.png) | `MUSIC`, `ICONS_MUSIC`, `MUSIC_ALT1` |
| vivid_volume | music | [Bild](vivid_volume.png) | `VOLUME`, `ZUNMUTE` |
| vivid_checkmark | ui | [Bild](vivid_checkmark.png) | `TICK`, `TICK_ALT`, `ZTICK`, `SUCCESS`, `ENABLE`, `CHECKMARK`, `OK` |
| vivid_cross | red | [Bild](vivid_cross.png) | `CROSS`, `CROSS_ALT`, `ML_CROSS`, `ZCROSS`, `ERROR`, `DENIED`, `DISABLE`, `ERROR_UNICODE`, `BLOCK`, `CHECK`, `FAIL`, `NOT_OK`, `CROSS_MARK` |
| vivid_arrow | ui | [Bild](vivid_arrow.png) | `ZARROW`, `ARROWRED`, `ARROW_RIGHT` |
| vivid_info | ui | [Bild](vivid_info.png) | `INFO` |
| vivid_warning | yellow | [Bild](vivid_warning.png) | `WARNING`, `WARNING_ALT`, `ZWARNING`, `ICONS_WARNING`, `ICONS_WARNING_ALT1`, `_37496ALERT`, `WARNING_UNICODE` |
| vivid_loading | ui | [Bild](vivid_loading.gif) | `LOADING`, `LOADING_ALT1`, `LOADINGRED` |
| vivid_back | ui | [Bild](vivid_back.png) | `ZBACK`, `ARROW_LEFT` |
| vivid_stop | music | [Bild](vivid_stop.png) | `MUSICSTOP_ICONS`, `STOP_BUTTON` |
| vivid_skip | music | [Bild](vivid_skip.png) | `NEXT`, `NEXT_ALT1`, `SKIP`, `FORWARD` |
| vivid_previous | music | [Bild](vivid_previous.png) | `PREVIOUS` |
| vivid_settings | ui | [Bild](vivid_settings.png) | `ZSETTINGS` |
| vivid_members | community | [Bild](vivid_members.png) | `ZPEOPLE`, `HUMAN`, `ZHUMAN` |
| vivid_message | support | [Bild](vivid_message.png) | `MESSAGE` |
| vivid_refresh | ui | [Bild](vivid_refresh.png) | `REFRESH`, `ICONLOAD` |
| vivid_plus | ui | [Bild](vivid_plus.png) | `ZPLUS`, `ICONS_PLUS` |
| vivid_delete | ui | [Bild](vivid_delete.png) | `DELETE`, `DELETE_ALT1` |
| vivid_mute | music | [Bild](vivid_mute.png) | `MUTE`, `ZMUTE` |
| vivid_unlock | security | [Bild](vivid_unlock.png) | `UNLOCK` |
| vivid_star | community | [Bild](vivid_star.png) | `STAR`, `STAR_ALT1`, `STAR_ALT2`, `SYSTEM`, `STAR_UNICODE` |
| vivid_cloud | ui | [Bild](vivid_cloud.png) | `ZCLOUD` |
| vivid_ban | red | [Bild](vivid_ban.png) | `ZBAN`, `universitybotHAMMER`, `SWORD` |
| vivid_kick | red | [Bild](vivid_kick.png) | `KICK` |
| vivid_timeout | security | [Bild](vivid_timeout.png) | `TIMER`, `TIMER_ALT1` |
| vivid_warn | yellow | [Bild](vivid_warn.png) | `WARN` |
| vivid_audit_log | security | [Bild](vivid_audit_log.png) | `AUDIT_LOG` |
| vivid_permissions | security | [Bild](vivid_permissions.png) | `PERMISSIONS` |
| vivid_firewall | security | [Bild](vivid_firewall.png) | `FIREWALL` |
| vivid_quarantine | security | [Bild](vivid_quarantine.png) | `QUARANTINE` |
| vivid_scan | security | [Bild](vivid_scan.png) | `SCAN` |
| vivid_fingerprint | security | [Bild](vivid_fingerprint.png) | `FINGERPRINT` |
| vivid_password | security | [Bild](vivid_password.png) | `PASSWORD` |
| vivid_incognito | security | [Bild](vivid_incognito.png) | `INCOGNITO` |
| vivid_lockdown | red | [Bild](vivid_lockdown.png) | `LOCKDOWN`, `LOCK_UNICODE` |
| vivid_protection | security | [Bild](vivid_protection.png) | `PROTECTION` |
| vivid_report | yellow | [Bild](vivid_report.png) | `REPORT` |
| vivid_ticket_open | support | [Bild](vivid_ticket_open.png) | `TICKET_OPEN` |
| vivid_ticket_close | red | [Bild](vivid_ticket_close.png) | `TICKET_CLOSE` |
| vivid_ticket_claim | support | [Bild](vivid_ticket_claim.png) | `TICKET_CLAIM` |
| vivid_transcript | support | [Bild](vivid_transcript.png) | `TRANSCRIPT`, `PAPER` |
| vivid_support | support | [Bild](vivid_support.png) | `SUPPORT`, `HANDSHAKE`, `MINGLE` |
| vivid_faq | support | [Bild](vivid_faq.png) | `FAQ` |
| vivid_mail | support | [Bild](vivid_mail.png) | `MAIL` |
| vivid_inbox | support | [Bild](vivid_inbox.png) | `INBOX` |
| vivid_form | support | [Bild](vivid_form.png) | `FORM` |
| vivid_accept | support | [Bild](vivid_accept.png) | `ACCEPT` |
| vivid_reject | red | [Bild](vivid_reject.png) | `REJECT` |
| vivid_feedback | support | [Bild](vivid_feedback.png) | `FEEDBACK` |
| vivid_boost | community | [Bild](vivid_boost.png) | `ZROCKET`, `BOOST`, `BOOSTS`, `NITRO_BOOST` |
| vivid_birthday | community | [Bild](vivid_birthday.png) | `BIRTHDAY` |
| vivid_event | community | [Bild](vivid_event.png) | `EVENT` |
| vivid_announcement | community | [Bild](vivid_announcement.png) | `ANNOUNCEMENT` |
| vivid_invite | community | [Bild](vivid_invite.png) | `INVITE` |
| vivid_leave | community | [Bild](vivid_leave.png) | `LEAVE` |
| vivid_role | community | [Bild](vivid_role.png) | `ROLE`, `HEADMOD`, `MANAGER`, `U_ADMIN`, `STAFF` |
| vivid_leaderboard | community | [Bild](vivid_leaderboard.png) | `LEADERBOARD` |
| vivid_xp | community | [Bild](vivid_xp.png) | `XP`, `SPARKLE` |
| vivid_poll | community | [Bild](vivid_poll.png) | `POLL` |
| vivid_counting | community | [Bild](vivid_counting.png) | `ZCOUNTING` |
| vivid_heart | community | [Bild](vivid_heart.png) | `ZDIL`, `HEART_EM`, `HEART3`, `REDHEART`, `EARLY_SUPPORTER`, `HEARTS` |
| vivid_game | community | [Bild](vivid_game.png) | `GAMES`, `GAME_CONTROLLER`, `MINECRAFT`, `MAX__A` |
| vivid_crown | community | [Bild](vivid_crown.png) | `KING`, `KING_ALT1`, `BLACKCROWN` |
| vivid_premium | community | [Bild](vivid_premium.png) | `PREMIUM`, `PARTNER_BADGE` |
| vivid_shuffle | music | [Bild](vivid_shuffle.png) | `SHUFFLE` |
| vivid_repeat | music | [Bild](vivid_repeat.png) | `REPEAT` |
| vivid_repeat_one | music | [Bild](vivid_repeat_one.png) | `REPEAT_ONE` |
| vivid_queue | music | [Bild](vivid_queue.png) | `QUEUE` |
| vivid_playlist | music | [Bild](vivid_playlist.png) | `PLAYLIST` |
| vivid_note | music | [Bild](vivid_note.png) | `MUSIC_NOTE`, `NOTE` |
| vivid_microphone | music | [Bild](vivid_microphone.png) | `MICROPHONE` |
| vivid_microphone_off | music | [Bild](vivid_microphone_off.png) | `MICROPHONE_OFF` |
| vivid_voice | music | [Bild](vivid_voice.png) | `VOICE` |
| vivid_equalizer | music | [Bild](vivid_equalizer.png) | `EQUALIZER` |
| vivid_seek_forward | music | [Bild](vivid_seek_forward.png) | `SEEK_FORWARD` |
| vivid_rewind | music | [Bild](vivid_rewind.png) | `REWIND`, `REWIND_ALT1` |
| vivid_home | ui | [Bild](vivid_home.png) | `HOME` |
| vivid_dashboard | ui | [Bild](vivid_dashboard.png) | `DASHBOARD` |
| vivid_channel | ui | [Bild](vivid_channel.png) | `CHANNEL`, `ICONS_CHANNEL` |
| vivid_search | ui | [Bild](vivid_search.png) | `universitybot_SEARCH`, `universitybot_CODE`, `universitybot_COMMAND` |
| vivid_edit | ui | [Bild](vivid_edit.png) | `EDIT` |
| vivid_save | ui | [Bild](vivid_save.png) | `SAVE` |
| vivid_copy | ui | [Bild](vivid_copy.png) | `COPY` |
| vivid_download | ui | [Bild](vivid_download.png) | `DOWNLOAD` |
| vivid_upload | ui | [Bild](vivid_upload.png) | `UPLOAD` |
| vivid_link | ui | [Bild](vivid_link.png) | `links`, `universitybotLINKS` |
| vivid_external_link | ui | [Bild](vivid_external_link.png) | `EXTERNAL_LINK` |
| vivid_arrow_up | ui | [Bild](vivid_arrow_up.png) | `ARROW_UP` |
| vivid_arrow_down | ui | [Bild](vivid_arrow_down.png) | `ARROW_DOWN` |
| vivid_menu | ui | [Bild](vivid_menu.png) | `MENU`, `INDEX` |
| vivid_close_panel | ui | [Bild](vivid_close_panel.png) | `CLOSE_PANEL` |
| vivid_open_panel | ui | [Bild](vivid_open_panel.png) | `OPEN_PANEL` |
| vivid_notification | ui | [Bild](vivid_notification.png) | `NOTIFICATION` |
| vivid_pin | ui | [Bild](vivid_pin.png) | `PIN`, `RED_PIN` |
| vivid_clock | ui | [Bild](vivid_clock.png) | `TIME`, `CLOCK` |
| vivid_bot | ui | [Bild](vivid_bot.png) | `ZBOT`, `universitybotSYS` |
| vivid_tools | ui | [Bild](vivid_tools.png) | `ZWRENCH`, `TOOLS` |
| vivid_bug_hunter | badges | [Bild](vivid_bug_hunter.png) | `BUG_HUNTER`, `BUG_HUNTER_LVL2` |
| vivid_developer | badges | [Bild](vivid_developer.png) | `CODEBASE`, `CODED`, `ACTIVE_DEVELOPER`, `Developer`, `EARLY_VERIFIED_BOT_DEV` |
| vivid_hypesquad | badges | [Bild](vivid_hypesquad.png) | `HYPESQUAD_BRILLIANCE`, `HYPESQUAD_BALANCE`, `HYPESQUAD_BRAVERY`, `HYPESQUAD_EVENTS` |
| vivid_browser | ui | [Bild](vivid_browser.png) | `ICON_BROWSER`, `universitybot_GLOBAL` |
| vivid_owner | badges | [Bild](vivid_owner.png) | `universitybot_OWNER` |
| vivid_mention | ui | [Bild](vivid_mention.png) | `MENTION`, `MENTION_ALT1` |
| vivid_new | ui | [Bild](vivid_new.png) | `NEW` |
| vivid_pc | ui | [Bild](vivid_pc.png) | `PC` |
| vivid_mobile | ui | [Bild](vivid_mobile.png) | `MOBILE` |
| vivid_connection | ui | [Bild](vivid_connection.png) | `WIFI`, `UPTIME`, `universitybotCONNECTION` |
| vivid_ai | ui | [Bild](vivid_ai.png) | `ZAI` |
| vivid_module | ui | [Bild](vivid_module.png) | `ZMODULE` |
| vivid_seed | community | [Bild](vivid_seed.png) | `SEED` |
| vivid_thunder | community | [Bild](vivid_thunder.png) | `THUNDER` |
| vivid_circle | ui | [Bild](vivid_circle.png) | `ZCIRCLE`, `ZCIRCLE_ALT1`, `RED_BUTTON`, `REDDOT` |
| vivid_online | status | [Bild](vivid_online.png) | `ONLINE` |
| vivid_offline | status | [Bild](vivid_offline.png) | `OFFLINE` |
| vivid_idle | yellow | [Bild](vivid_idle.png) | `IDLE` |
| vivid_dnd | red | [Bild](vivid_dnd.png) | `DND` |
| vivid_cast | music | [Bild](vivid_cast.png) | `CAST` |
| vivid_cute | community | [Bild](vivid_cute.png) | `CUTE_CUTE_CUTE`, `BLOBPART`, `LAUGH1`, `LAUGH2`, `LAUGH3`, `UPSIDE_DOWN`, `TONGUE_OUT` |
| vivid_panda | community | [Bild](vivid_panda.png) | `HAPPY_PANDA` |
| vivid_dance | community | [Bild](vivid_dance.png) | `HEERIYE`, `SG_RD` |
| vivid_sticker | community | [Bild](vivid_sticker.png) | `EMOTE`, `GIFD`, `GIFN` |
| vivid_racecar | community | [Bild](vivid_racecar.png) | `RACECAR64` |
| vivid_tea | community | [Bild](vivid_tea.png) | `BUBBLE_TEA` |
| vivid_cherries | community | [Bild](vivid_cherries.png) | `CHERRIES` |
| vivid_cookie | community | [Bild](vivid_cookie.png) | `COOKIE` |
| vivid_cursor | ui | [Bild](vivid_cursor.png) | `CURSOR` |
| vivid_dizzy | community | [Bild](vivid_dizzy.png) | `DIZZY` |
| vivid_coffee | community | [Bild](vivid_coffee.png) | `JAVA_COFFEE` |
| vivid_money | community | [Bild](vivid_money.png) | `MONEY` |
| vivid_moon | community | [Bild](vivid_moon.png) | `MOON` |
| vivid_peach | community | [Bild](vivid_peach.png) | `PEACH` |
| vivid_rock | community | [Bild](vivid_rock.png) | `ROCK` |
| vivid_scissors | community | [Bild](vivid_scissors.png) | `SCISSORS` |
| vivid_shocked | community | [Bild](vivid_shocked.png) | `SHOCKED` |
| vivid_target | community | [Bild](vivid_target.png) | `TARGET` |
| vivid_rules | regelwerk | [Bild](vivid_rules.png) | `RULES`, `REGELWERK`, `REDRULESBOOK` |
| vivid_guidelines | regelwerk | [Bild](vivid_guidelines.png) | `GUIDELINES` |
| vivid_rules_accept | regelwerk | [Bild](vivid_rules_accept.png) | `RULES_ACCEPT` |
| vivid_rules_faq | regelwerk | [Bild](vivid_rules_faq.png) | `RULES_FAQ` |
| vivid_privacy_policy | regelwerk | [Bild](vivid_privacy_policy.png) | `PRIVACY_POLICY` |
| vivid_terms | regelwerk | [Bild](vivid_terms.png) | `TERMS` |
| vivid_changelog | ui | [Bild](vivid_changelog.png) | `CHANGELOG` |
| vivid_server_info | ui | [Bild](vivid_server_info.png) | `SERVER_INFO` |
| vivid_exclamation | yellow | [Bild](vivid_exclamation.png) | `CATALOG_EXCLAMATION` |
| vivid_question | ui | [Bild](vivid_question.png) | `CATALOG_QUESTION` |
| vivid_globe | ui | [Bild](vivid_globe.png) | `CATALOG_GLOBE` |
| vivid_globe_languages | ui | [Bild](vivid_globe_languages.png) | `CATALOG_GLOBE_LANGUAGES` |
| vivid_member | community | [Bild](vivid_member.png) | `CATALOG_MEMBER` |
| vivid_member_verified | community | [Bild](vivid_member_verified.png) | `CATALOG_MEMBER_VERIFIED` |
| vivid_member_add | community | [Bild](vivid_member_add.png) | `CATALOG_MEMBER_ADD` |
| vivid_member_remove | community | [Bild](vivid_member_remove.png) | `CATALOG_MEMBER_REMOVE` |
| vivid_member_banned | red | [Bild](vivid_member_banned.png) | `CATALOG_MEMBER_BANNED` |
| vivid_user_profile | community | [Bild](vivid_user_profile.png) | `CATALOG_USER_PROFILE` |
| vivid_text_channel | server | [Bild](vivid_text_channel.png) | `CATALOG_TEXT_CHANNEL` |
| vivid_voice_channel | server | [Bild](vivid_voice_channel.png) | `CATALOG_VOICE_CHANNEL` |
| vivid_forum_channel | server | [Bild](vivid_forum_channel.png) | `CATALOG_FORUM_CHANNEL` |
| vivid_stage_channel | server | [Bild](vivid_stage_channel.png) | `CATALOG_STAGE_CHANNEL` |
| vivid_category_folder | server | [Bild](vivid_category_folder.png) | `CATALOG_CATEGORY_FOLDER` |
| vivid_thread | server | [Bild](vivid_thread.png) | `CATALOG_THREAD` |
| vivid_unban | moderation | [Bild](vivid_unban.png) | `CATALOG_UNBAN` |
| vivid_softban | red | [Bild](vivid_softban.png) | `CATALOG_SOFTBAN` |
| vivid_tempban | red | [Bild](vivid_tempban.png) | `CATALOG_TEMPBAN` |
| vivid_mute_member | moderation | [Bild](vivid_mute_member.png) | `CATALOG_MUTE_MEMBER` |
| vivid_unmute_member | moderation | [Bild](vivid_unmute_member.png) | `CATALOG_UNMUTE_MEMBER` |
| vivid_remove_timeout | moderation | [Bild](vivid_remove_timeout.png) | `CATALOG_REMOVE_TIMEOUT` |
| vivid_warn_remove | moderation | [Bild](vivid_warn_remove.png) | `CATALOG_WARN_REMOVE` |
| vivid_warn_list | yellow | [Bild](vivid_warn_list.png) | `CATALOG_WARN_LIST` |
| vivid_mod_log | moderation | [Bild](vivid_mod_log.png) | `CATALOG_MOD_LOG` |
| vivid_appeal | moderation | [Bild](vivid_appeal.png) | `CATALOG_APPEAL` |
| vivid_evidence | moderation | [Bild](vivid_evidence.png) | `CATALOG_EVIDENCE` |
| vivid_slowmode | moderation | [Bild](vivid_slowmode.png) | `CATALOG_SLOWMODE` |
| vivid_nsfw | moderation | [Bild](vivid_nsfw.png) | `CATALOG_NSFW` |
| vivid_anti_spam | moderation | [Bild](vivid_anti_spam.png) | `CATALOG_ANTI_SPAM` |
| vivid_anti_raid | moderation | [Bild](vivid_anti_raid.png) | `CATALOG_ANTI_RAID` |
| vivid_purge | moderation | [Bild](vivid_purge.png) | `CATALOG_PURGE` |
| vivid_server | server | [Bild](vivid_server.png) | `CATALOG_SERVER` |
| vivid_server_settings | server | [Bild](vivid_server_settings.png) | `CATALOG_SERVER_SETTINGS` |
| vivid_server_stats | server | [Bild](vivid_server_stats.png) | `CATALOG_SERVER_STATS` |
| vivid_server_boost | server | [Bild](vivid_server_boost.png) | `CATALOG_SERVER_BOOST` |
| vivid_server_owner | server | [Bild](vivid_server_owner.png) | `CATALOG_SERVER_OWNER` |
| vivid_admin | server | [Bild](vivid_admin.png) | `CATALOG_ADMIN` |
| vivid_moderator | server | [Bild](vivid_moderator.png) | `CATALOG_MODERATOR` |
| vivid_staff | server | [Bild](vivid_staff.png) | `CATALOG_STAFF` |
| vivid_newcomer | server | [Bild](vivid_newcomer.png) | `CATALOG_NEWCOMER` |
| vivid_bot_add | server | [Bild](vivid_bot_add.png) | `CATALOG_BOT_ADD` |
| vivid_server_join | server | [Bild](vivid_server_join.png) | `CATALOG_SERVER_JOIN` |
| vivid_server_leave | server | [Bild](vivid_server_leave.png) | `CATALOG_SERVER_LEAVE` |
| vivid_goodbye | server | [Bild](vivid_goodbye.png) | `CATALOG_GOODBYE` |
| vivid_welcome_wave | server | [Bild](vivid_welcome_wave.png) | `CATALOG_WELCOME_WAVE` |
| vivid_bug_report | support | [Bild](vivid_bug_report.png) | `CATALOG_BUG_REPORT` |
| vivid_suggestion | support | [Bild](vivid_suggestion.png) | `CATALOG_SUGGESTION` |
| vivid_help | support | [Bild](vivid_help.png) | `CATALOG_HELP` |
| vivid_ticket_reopen | support | [Bild](vivid_ticket_reopen.png) | `CATALOG_TICKET_REOPEN` |
| vivid_ticket_transfer | support | [Bild](vivid_ticket_transfer.png) | `CATALOG_TICKET_TRANSFER` |
| vivid_ticket_archive | support | [Bild](vivid_ticket_archive.png) | `CATALOG_TICKET_ARCHIVE` |
| vivid_ticket_priority | yellow | [Bild](vivid_ticket_priority.png) | `CATALOG_TICKET_PRIORITY` |
| vivid_ticket_pending | support | [Bild](vivid_ticket_pending.png) | `CATALOG_TICKET_PENDING` |
| vivid_ticket_resolved | support | [Bild](vivid_ticket_resolved.png) | `CATALOG_TICKET_RESOLVED` |
| vivid_ticket_category | support | [Bild](vivid_ticket_category.png) | `CATALOG_TICKET_CATEGORY` |
| vivid_rules_violation | red | [Bild](vivid_rules_violation.png) | `CATALOG_RULES_VIOLATION` |
| vivid_rules_update | regelwerk | [Bild](vivid_rules_update.png) | `CATALOG_RULES_UPDATE` |
| vivid_rules_pending | yellow | [Bild](vivid_rules_pending.png) | `CATALOG_RULES_PENDING` |
| vivid_age_limit | yellow | [Bild](vivid_age_limit.png) | `CATALOG_AGE_LIMIT` |
| vivid_agreement | regelwerk | [Bild](vivid_agreement.png) | `CATALOG_AGREEMENT` |
| vivid_announcement_rules | regelwerk | [Bild](vivid_announcement_rules.png) | `CATALOG_ANNOUNCEMENT_RULES` |
| vivid_wallet | economy | [Bild](vivid_wallet.png) | `CATALOG_WALLET` |
| vivid_coins | economy | [Bild](vivid_coins.png) | `CATALOG_COINS` |
| vivid_bank | economy | [Bild](vivid_bank.png) | `CATALOG_BANK` |
| vivid_shop | economy | [Bild](vivid_shop.png) | `CATALOG_SHOP` |
| vivid_cart | economy | [Bild](vivid_cart.png) | `CATALOG_CART` |
| vivid_reward | economy | [Bild](vivid_reward.png) | `CATALOG_REWARD` |
| vivid_daily | economy | [Bild](vivid_daily.png) | `CATALOG_DAILY` |
| vivid_trade | economy | [Bild](vivid_trade.png) | `CATALOG_TRADE` |
| vivid_inventory | economy | [Bild](vivid_inventory.png) | `CATALOG_INVENTORY` |
| vivid_receipt | economy | [Bild](vivid_receipt.png) | `CATALOG_RECEIPT` |
| vivid_party | community | [Bild](vivid_party.png) | `CATALOG_PARTY` |
| vivid_fire | community | [Bild](vivid_fire.png) | `CATALOG_FIRE` |
| vivid_gift_claim | community | [Bild](vivid_gift_claim.png) | `CATALOG_GIFT_CLAIM` |
| vivid_timer_event | community | [Bild](vivid_timer_event.png) | `CATALOG_TIMER_EVENT` |
| vivid_image | media | [Bild](vivid_image.png) | `CATALOG_IMAGE` |
| vivid_camera | media | [Bild](vivid_camera.png) | `CATALOG_CAMERA` |
| vivid_video | media | [Bild](vivid_video.png) | `CATALOG_VIDEO` |
| vivid_streaming | media | [Bild](vivid_streaming.png) | `CATALOG_STREAMING` |
| vivid_maintenance | yellow | [Bild](vivid_maintenance.png) | `CATALOG_MAINTENANCE` |
| vivid_outage | red | [Bild](vivid_outage.png) | `CATALOG_OUTAGE` |
| vivid_scheduled | status | [Bild](vivid_scheduled.png) | `CATALOG_SCHEDULED` |
| vivid_complete | status | [Bild](vivid_complete.png) | `CATALOG_COMPLETE` |
| vivid_booster | badges | [Bild](vivid_booster.png) | `CATALOG_BOOSTER` |
| vivid_paint | media | [Bild](vivid_paint.png) | `CATALOG_PAINT` |
| vivid_github | media | [Bild](vivid_github.png) | `CATALOG_GITHUB` |
| vivid_youtube | media | [Bild](vivid_youtube.png) | `CATALOG_YOUTUBE` |
| vivid_partner | badges | [Bild](vivid_partner.png) | `CATALOG_PARTNER` |
| vivid_supporter | badges | [Bild](vivid_supporter.png) | `CATALOG_SUPPORTER` |
| vivid_ambassador | badges | [Bild](vivid_ambassador.png) | `CATALOG_AMBASSADOR` |
| vivid_rocket | community | [Bild](vivid_rocket.png) | `CATALOG_ROCKET` |
| vivid_trophy | community | [Bild](vivid_trophy.png) | `CATALOG_TROPHY` |
