"""Persistent community ideas, votes, comments, moderation and rewards."""
from __future__ import annotations
import json, os, secrets, sqlite3, time

DB_PATH = "db/ideas.db"
STATUSES = {"open", "planned", "working", "implemented", "rejected", "needs_info"}

def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db

def ensure():
    with _db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS ideas(
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, user_name TEXT NOT NULL,
          avatar TEXT DEFAULT '', title TEXT NOT NULL, description TEXT NOT NULL,
          images TEXT DEFAULT '[]', status TEXT DEFAULT 'open', admin_note TEXT DEFAULT '',
          reward_granted INTEGER DEFAULT 0, views INTEGER DEFAULT 0,
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS idea_votes(
          idea_id TEXT NOT NULL, user_id TEXT NOT NULL, value INTEGER NOT NULL,
          created_at INTEGER NOT NULL, PRIMARY KEY(idea_id,user_id));
        CREATE TABLE IF NOT EXISTS idea_comments(
          id INTEGER PRIMARY KEY AUTOINCREMENT, idea_id TEXT NOT NULL, user_id TEXT NOT NULL,
          user_name TEXT NOT NULL, avatar TEXT DEFAULT '', body TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS idea_blacklist(
          user_id TEXT PRIMARY KEY, reason TEXT DEFAULT '', created_by TEXT DEFAULT '', created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS idea_rewards(
          idea_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, claimed_guild_id TEXT,
          claimed_at INTEGER, expires_at INTEGER, created_at INTEGER NOT NULL);
        """)
        columns={row[1] for row in db.execute("PRAGMA table_info(ideas)")}
        if "views" not in columns:
            db.execute("ALTER TABLE ideas ADD COLUMN views INTEGER DEFAULT 0")

def _one(row):
    if not row: return None
    item = dict(row)
    if "images" in item:
        try: item["images"] = json.loads(item["images"] or "[]")
        except Exception: item["images"] = []
    return item

def blocked(user_id: str):
    ensure()
    with _db() as db:
        row=db.execute("SELECT reason FROM idea_blacklist WHERE user_id=?",(str(user_id),)).fetchone()
    return str(row[0] or "") if row else None

def create(user_id,user_name,avatar,title,description,images):
    ensure(); now=int(time.time()); iid="IDEA-"+secrets.token_hex(4).upper()
    with _db() as db:
        db.execute("INSERT INTO ideas VALUES(?,?,?,?,?,?,?,'open','',0,0,?,?)",
          (iid,str(user_id),str(user_name)[:80],str(avatar)[:500],str(title)[:100],str(description)[:2000],json.dumps(list(images)[:3]),now,now))
    return get(iid,str(user_id),False)

def get(iid, viewer="", count_view=True):
    ensure()
    with _db() as db:
        if count_view:
            db.execute("UPDATE ideas SET views=views+1 WHERE id=?",(iid,))
        row=db.execute("SELECT * FROM ideas WHERE id=?",(iid,)).fetchone()
        if not row:return None
        out=_one(row)
        counts=db.execute("SELECT COALESCE(SUM(value=1),0),COALESCE(SUM(value=-1),0) FROM idea_votes WHERE idea_id=?",(iid,)).fetchone()
        out["upvotes"],out["downvotes"]=int(counts[0]),int(counts[1])
        vote=db.execute("SELECT value FROM idea_votes WHERE idea_id=? AND user_id=?",(iid,str(viewer),)).fetchone() if viewer else None
        out["my_vote"]=int(vote[0]) if vote else 0
        out["comments"]=[dict(x) for x in db.execute("SELECT * FROM idea_comments WHERE idea_id=? ORDER BY created_at",(iid,)).fetchall()]
        return out

def listing(status="",sort="new",q="",limit=50,offset=0,viewer=""):
    ensure(); where=[]; args=[]
    if status and status in STATUSES: where.append("i.status=?");args.append(status)
    if q: where.append("(i.title LIKE ? OR i.description LIKE ?)");args += [f"%{q[:100]}%",f"%{q[:100]}%"]
    order="score DESC, i.created_at DESC" if sort=="popular" else "i.created_at DESC"
    sql="SELECT i.*, (SELECT COALESCE(SUM(value),0) FROM idea_votes WHERE idea_id=i.id) score, (SELECT COUNT(*) FROM idea_votes WHERE idea_id=i.id AND value=1) upvotes, (SELECT COUNT(*) FROM idea_votes WHERE idea_id=i.id AND value=-1) downvotes, (SELECT COUNT(*) FROM idea_comments WHERE idea_id=i.id) comment_count FROM ideas i"
    if where: sql += " WHERE "+" AND ".join(where)
    sql += " ORDER BY "+order+" LIMIT ? OFFSET ?"; args += [min(100,max(1,limit)),max(0,offset)]
    with _db() as db: rows=[_one(r) for r in db.execute(sql,args).fetchall()]
    # Reference images can be several megabytes. The overview never renders
    # them, so only the detail route should transport that payload.
    for row in rows:
        row["image_count"] = len(row.get("images") or [])
        row["images"] = []
    return rows

def admin_overview(status="", q=""):
    ensure()
    ideas = listing(status, "new", q, 100, 0)
    with _db() as db:
        counts = {row[0]: int(row[1]) for row in db.execute(
            "SELECT status, COUNT(*) FROM ideas GROUP BY status"
        ).fetchall()}
        blacklisted = [dict(row) for row in db.execute(
            "SELECT * FROM idea_blacklist ORDER BY created_at DESC"
        ).fetchall()]
    return ideas, counts, blacklisted


def mine(user_id):
    ensure()
    with _db() as db:
        ideas=[_one(r) for r in db.execute("SELECT * FROM ideas WHERE user_id=? ORDER BY created_at DESC",(str(user_id),)).fetchall()]
        for item in ideas:
            item["image_count"] = len(item.get("images") or [])
            item["images"] = []
        rewards=[dict(r) for r in db.execute("SELECT r.*,i.title FROM idea_rewards r JOIN ideas i ON i.id=r.idea_id WHERE r.user_id=? ORDER BY r.created_at DESC",(str(user_id),)).fetchall()]
    return ideas,rewards

def vote(iid,user_id,value):
    ensure(); value=int(value)
    if value not in (-1,0,1): raise ValueError("vote")
    with _db() as db:
        if value: db.execute("INSERT OR REPLACE INTO idea_votes VALUES(?,?,?,?)",(iid,str(user_id),value,int(time.time())))
        else: db.execute("DELETE FROM idea_votes WHERE idea_id=? AND user_id=?",(iid,str(user_id)))
    return get(iid,str(user_id),False)

def comment(iid,user_id,user_name,avatar,body):
    ensure(); body=str(body).strip()
    if not body or len(body)>1000: raise ValueError("comment")
    with _db() as db: db.execute("INSERT INTO idea_comments(idea_id,user_id,user_name,avatar,body,created_at) VALUES(?,?,?,?,?,?)",(iid,str(user_id),str(user_name)[:80],str(avatar)[:500],body,int(time.time())))
    return get(iid,str(user_id),False)

def decide(iid,status,note,reward=False):
    ensure()
    if status not in STATUSES: raise ValueError("status")
    now=int(time.time())
    with _db() as db:
        row=db.execute("SELECT user_id FROM ideas WHERE id=?",(iid,)).fetchone()
        if not row:return None
        db.execute("UPDATE ideas SET status=?,admin_note=?,reward_granted=?,updated_at=? WHERE id=?",(status,str(note)[:500],int(bool(reward)),now,iid))
        if reward: db.execute("INSERT OR IGNORE INTO idea_rewards(idea_id,user_id,created_at) VALUES(?,?,?)",(iid,row[0],now))
    return get(iid,count_view=False)

def delete(iid):
    ensure()
    with _db() as db:
        found=db.execute("SELECT 1 FROM ideas WHERE id=?",(iid,)).fetchone()
        for table in ("idea_votes","idea_comments","idea_rewards"):db.execute(f"DELETE FROM {table} WHERE idea_id=?",(iid,))
        db.execute("DELETE FROM ideas WHERE id=?",(iid,))
    return bool(found)

def blacklist(user_id,reason,admin,enabled=True):
    ensure()
    with _db() as db:
        if enabled: db.execute("INSERT OR REPLACE INTO idea_blacklist VALUES(?,?,?,?)",(str(user_id),str(reason)[:300],str(admin),int(time.time())))
        else: db.execute("DELETE FROM idea_blacklist WHERE user_id=?",(str(user_id),))

def claim(iid,user_id,guild_id):
    ensure(); now=int(time.time()); expires=now+3*86400
    with _db() as db:
        row=db.execute("SELECT claimed_at FROM idea_rewards WHERE idea_id=? AND user_id=?",(iid,str(user_id))).fetchone()
        if not row: raise ValueError("reward")
        if row[0]: raise RuntimeError("claimed")
        db.execute("UPDATE idea_rewards SET claimed_guild_id=?,claimed_at=?,expires_at=? WHERE idea_id=?",(str(guild_id),now,expires,iid))
    return expires
