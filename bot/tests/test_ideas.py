#!/usr/bin/env python3
"""Regression checks for the public community ideas system."""
import importlib.util, os, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
fail=[]
def check(name,ok):
 print(("  ok   " if ok else "  FAIL ")+name)
 if not ok:fail.append(name)

spec=importlib.util.spec_from_file_location("ideas_store",ROOT/"bot/utils/ideas_store.py")
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
p=tempfile.mktemp(suffix=".db");s.DB_PATH=p
try:
 i=s.create("101","Lena","","Mehr Schutz","Eine ausführliche Beschreibung",["https://cdn/x.png"])
 check("Idee wird angelegt",i["status"]=="open" and i["user_id"]=="101")
 s.vote(i["id"],"202",1);s.comment(i["id"],"202","Tom","","Gute Idee")
 d=s.get(i["id"],"202")
 check("Votes sind pro Nutzer",d["upvotes"]==1 and d["my_vote"]==1)
 check("Kommentare gehören zur Idee",len(d["comments"])==1)
 s.decide(i["id"],"implemented","Verfügbar",True)
 _,rewards=s.mine("101")
 check("Annahme kann Belohnung erzeugen",len(rewards)==1 and not rewards[0]["claimed_at"])
 s.claim(i["id"],"101","303")
 check("Belohnung wird genau einem Server zugeordnet",s.mine("101")[1][0]["claimed_guild_id"]=="303")
 s.blacklist("101","Spam","1")
 check("Nutzer-Blacklist sperrt Einreichungen",s.blocked("101")=="Spam")
 check("Owner kann Idee löschen",s.delete(i["id"]) and s.get(i["id"]) is None)
finally:
 if os.path.exists(p):os.unlink(p)

ui=(ROOT/"dashboard/components/ideas-system.tsx").read_text()
route=(ROOT/"bot/api/routes/ideas.py").read_text()
proxy=(ROOT/"dashboard/app/api/bot/[...path]/route.ts").read_text()
home=(ROOT/"dashboard/app/page.tsx").read_text()
admin_ui=(ROOT/"dashboard/components/dashboard/ideas-admin.tsx").read_text()
admin_shell=(ROOT/"dashboard/components/dashboard/admin-content.tsx").read_text()
middleware=(ROOT/"dashboard/middleware.ts").read_text()
check("öffentliche Übersicht, Detail, Meine Ideen und Formular existieren",all((ROOT/x).exists() for x in ["dashboard/app/ideas/page.tsx","dashboard/app/ideas/new/page.tsx","dashboard/app/ideas/me/page.tsx","dashboard/app/ideas/[ideaId]/page.tsx"]))
check("öffentliche Ideen können ohne Login geladen werden",'pathname.startsWith("/api/bot/ideas")' in middleware and 'method === "GET"' in middleware)
check("Voten und Kommentieren verlangen Discord-Login",'signIn("discord"' in ui and "voteIdea" in ui and "commentIdea" in ui)
check("öffentliche Website hat den neuen responsiven Ideenaufbau",all(x in ui for x in ["Gemeinsam bauen wir den besseren University Bot", "Ideen entdecken", "Gute Ideen lohnen sich", "Deine Idee zählt"]))
check("Einreichung, Details und Belohnungen haben eigene neue Ansichten",all(x in ui for x in ["Ein Problem pro Idee", "Antwort vom University-Team", "Für diesen Server einlösen"]))
check("eigenes vollständiges Ideen-Adminsystem ist eingebaut",'id: "ideas"' in admin_shell and '<IdeasAdmin />' in admin_shell and all(x in admin_ui for x in ["Community Ideen","Gesperrte Nutzer","Entscheidung speichern & DM senden","Ideen-Blacklist"]))
check("Ideen-Adminsystem ist Owner-only",'tab.id === "access" || tab.id === "ideas"' in admin_shell)
check("Owner-Schutz wird serverseitig geprüft",'scope === "ideas"' in proxy and "isGlobalAdmin(session.user.id)" in proxy)
check("DM nutzt Components V2, Custom Emoji und Einlöse-Link","Panel(" in route and "emoji.STAR" in route and "Belohnung einlösen" in route)
check("Home zeigt die Ideen-Karte","Hilf uns, University Bot besser zu machen" in home and 'href="/ideas/new"' in home)
print(f"\n{len(fail)} Fehler")
raise SystemExit(1 if fail else 0)
