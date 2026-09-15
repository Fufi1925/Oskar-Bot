"""Deterministic firewall regression tests. Run directly, not through pytest."""
import importlib.util, os, sqlite3, tempfile, time
spec=importlib.util.spec_from_file_location("firewall",os.path.join(os.path.dirname(__file__),"../utils/firewall.py"))
fw=importlib.util.module_from_spec(spec); spec.loader.exec_module(fw)

def main():
    with tempfile.TemporaryDirectory() as tmp:
        fw.DB_PATH=os.path.join(tmp,"firewall.db"); fw._hits.clear(); fw.ensure()
        # CIDR normalization and matching.
        block=fw.add_rule("block","203.0.113.9/24","test")
        assert block["value"]=="203.0.113.0/24"
        assert fw.evaluate("203.0.113.22","GET","/api/x")["allowed"] is False
        # Allow rules take priority over broader blocks.
        fw.add_rule("allow","203.0.113.22")
        assert fw.evaluate("203.0.113.22","GET","/api/x")["reason"]=="allowlist"
        # Removing the allow rule restores the block.
        fw.delete_rule(next(r["id"] for r in fw.rules() if r["kind"]=="allow"))
        assert fw.evaluate("203.0.113.22","GET","/api/x")["allowed"] is False
        # Authenticated owners and bot-local API calls are never counted or blocked.
        assert fw.evaluate("203.0.113.22","GET","/dashboard",actor_id="1",actor_is_owner=True)["reason"]=="owner_bypass"
        assert fw.evaluate("203.0.113.22","GET","/templates",trusted_internal=True)["reason"]=="trusted_internal"
        assert fw.evaluate("127.0.0.1","POST","/api/v1/firewall/check")["reason"]=="trusted_network"
        try: fw.add_rule("block","127.0.0.1")
        except ValueError: pass
        else: raise AssertionError("trusted network was blockable")
        user_rule=fw.add_rule("user_block","123456789012345678")
        assert not fw.evaluate("203.0.114.4","GET","/dashboard",actor_id="123456789012345678")["allowed"]
        assert fw.unban("user","123456789012345678")==1
        assert fw.delete_rule(user_rule["id"]) is False
        method_rule=fw.add_rule("method","DELETE")
        assert fw.inspect("203.0.114.4",path="/api/x",method="DELETE")["reason"]=="blocked_method"
        assert fw.delete_rule(method_rule["id"])
        notice=fw.log_event("203.0.114.5","GET","/api/x","browser","DE","rate_alarm","high")
        assert fw.acknowledge_incident(notice,"owner")
        assert all(event["id"]!=notice for event in fw.events(50,True))
        temporary=fw.add_rule("block","198.18.1.2",expires_at=int(time.time())+60)
        assert fw.bulk_unban("temporary")>=1 and fw.delete_rule(temporary["id"]) is False
        assert fw.apply_preset("safe")["auto_block_enabled"] is False
        # Deterministic burst detection creates a temporary reversible rule.
        fw.update_settings({"requests_per_minute":100,"burst_10_seconds":2,"auto_block_minutes":3,"auto_block_enabled":True,"confirmations_required":3})
        ip="198.51.100.4"
        # Two complete bursts only raise alarms; the third confirmation blocks.
        for confirmation in (1,2):
            assert fw.evaluate(ip,"GET","/api/x")["allowed"]
            assert fw.evaluate(ip,"GET","/api/x")["allowed"]
            alarm=fw.evaluate(ip,"GET","/api/x")
            assert alarm["allowed"] and alarm["reason"]=="rate_alarm" and alarm["confirmations"]==confirmation
        assert fw.evaluate(ip,"GET","/api/x")["allowed"]
        assert fw.evaluate(ip,"GET","/api/x")["allowed"]
        attacked=fw.evaluate(ip,"GET","/api/x")
        assert attacked["allowed"] is False and attacked["status"]==429
        auto=next(r for r in fw.rules() if r["value"]==f"{ip}/32")
        assert auto["expires_at"] and auto["expires_at"]>int(time.time())
        assert fw.delete_rule(auto["id"])
        # Manual stop marks the incident and creates a permanent reversible block.
        event=fw.log_event("192.0.2.3","POST","/api/login","ua","DE","rate_attack","critical",429,9,True)
        stopped=fw.stop_incident(event,"owner")
        assert stopped["stopped"] and stopped["rule"]["expires_at"] is None
        assert fw.delete_rule(stopped["rule"]["id"])
        # Startup cleanup keeps recent events and removes readable IP events older than 90 days.
        old=int(time.time())-fw.RETENTION_SECONDS-10
        with sqlite3.connect(fw.DB_PATH) as db:
            db.execute("INSERT INTO firewall_events(created_at,ip,method,path,category,severity) VALUES(?,?,?,?,?,?)",(old,"192.0.2.99","GET","/","test","low"))
        fw.ensure()
        assert all(e["ip"]!="192.0.2.99" for e in fw.events())
        # Self-check artifacts from the faulty v2 mount are removed by v3 migration.
        false_event=fw.log_event("10.0.0.4","POST","/api/v1/firewall/check","bot","","blocked_ip","high",403,1,True)
        with sqlite3.connect(fw.DB_PATH) as db: db.execute("UPDATE firewall_settings SET value='2' WHERE key='safety_profile_version'")
        fw.ensure()
        assert all(e["id"]!=false_event for e in fw.events())
        server=open("bot/api/server.py",encoding="utf-8").read()
        assert 'startswith("/api/v1/firewall")' in server
        panel=open("dashboard/components/dashboard/firewall-panel.tsx",encoding="utf-8").read()
        assert "<select" not in panel and "CustomSelect" in panel
        assert "bulkUnbanFirewall" in panel and "acknowledgeFirewallIncident" in panel
        # The Grok route may persist a report, but never calls mutation functions.
        route=open("bot/api/routes/firewall.py",encoding="utf-8").read()
        analyze=route[route.index('async def analyze_attack'):route.index('@router.post("/check")')]
        assert "advisory_only" in analyze
        assert "stop_incident(" not in analyze and "add_rule(" not in analyze and "update_settings(" not in analyze
    print("Firewall tests: OK")
if __name__=="__main__": main()
