"""Postgres is the allocation/operation authority, not Streamlit or provider search."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import time
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .domain import BARBARA, Blocked, choose, identity, prefer_sender


class Store:
    def __init__(self, url):
        self.url = url

    def connect(self):
        return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5, client_encoding="utf8")

    def migrate(self):
        with self.connect() as c:
            if c.execute("SHOW server_encoding").fetchone()["server_encoding"] != "UTF8":
                raise Blocked("database_utf8_required_for_local_titles")
            c.execute(Path(__file__).with_name("schema.sql").read_text())

    def audit(self, c, operation, action, detail=None):
        c.execute("INSERT INTO bridge_audit(operation,action,detail) VALUES (%s,%s,%s)",
                  (operation, action, Jsonb(detail or {})))

    def register(self, registry):
        with self.connect() as c:
            c.execute("INSERT INTO bridge_rotation(consultant) VALUES (%s) ON CONFLICT DO NOTHING", (BARBARA,))
            configured = [a["id"] for a in registry.get("senders", [])]
            c.execute("UPDATE bridge_senders SET disabled=true WHERE account->>'reviewed'='true' AND NOT(id=ANY(%s))", (configured,))
            for account in registry.get("senders", []):
                existing = c.execute("SELECT account FROM bridge_senders WHERE id=%s FOR UPDATE", (account["id"],)).fetchone()
                if existing and any(existing["account"].get(k) != account.get(k) for k in ("provider", "tenant", "subject", "calendar_id", "email", "group")):
                    raise Blocked("sender_identity_is_immutable")
                # Preserve observed health and audited disable switch across restarts.
                c.execute("""INSERT INTO bridge_senders(id,account) VALUES (%s,%s)
                    ON CONFLICT(id) DO UPDATE SET account=EXCLUDED.account ||
                    jsonb_build_object('health',COALESCE(bridge_senders.account->'health','{}'::jsonb))""",
                          (account["id"], Jsonb(account)))

    def inventory(self, c=None):
        if c is None:
            with self.connect() as conn:
                return self.inventory(conn)
        rows = c.execute("""SELECT s.*, COALESCE(cap.used,0) AS used FROM bridge_senders s
            LEFT JOIN bridge_caps cap ON cap.sender=s.id AND cap.day=(now() AT TIME ZONE 'UTC')::date
            ORDER BY s.id""").fetchall()
        return [dict(r["account"], disabled=r["disabled"] or r["account"].get("disabled", False), used=r["used"]) for r in rows]

    def health(self, sender, health):
        with self.connect() as c:
            c.execute("UPDATE bridge_senders SET account=jsonb_set(account,'{health}',%s) WHERE id=%s",
                      (Jsonb(health), sender))

    def disable(self, sender, disabled, reason):
        with self.connect() as c:
            if not c.execute("UPDATE bridge_senders SET disabled=%s WHERE id=%s RETURNING id",
                             (disabled, sender)).fetchone():
                raise Blocked("unknown_sender")
            self.audit(c, None, "sender_disable", {"sender": sender, "disabled": disabled, "reason": reason})

    def get(self, operation):
        with self.connect() as c:
            return c.execute("SELECT * FROM bridge_meetings WHERE operation=%s", (operation,)).fetchone()

    def reserve(self, command, occupancy):
        operation = BARBARA + ":" + command["task_id"]
        with self.connect() as c:
            c.execute("SET LOCAL lock_timeout = '10s'")
            rotation = c.execute("SELECT * FROM bridge_rotation WHERE consultant=%s FOR UPDATE", (BARBARA,)).fetchone()
            existing = c.execute("SELECT * FROM bridge_meetings WHERE operation=%s", (operation,)).fetchone()
            if existing:
                return existing  # task retries never reallocate or re-count
            inventory, now = self.inventory(c), time.time()
            sender, group, sticky = None, None, False
            for address in command.get("preferred_from") or []:
                match = prefer_sender(address, inventory, now)
                if match:
                    sender, group, sticky = match, match["group"], True
                    break
            if sender is None:
                group, sender = choose(command["groups"], rotation["cursor"], rotation["mailbox_cursors"],
                                       inventory, now)
            # Read fresh availability under the same consultant lock. Exclude placeholders by
            # server-reviewed title and managed IDs; add durable overlapping reservations once.
            reservations = c.execute("""SELECT * FROM bridge_meetings WHERE consultant=%s
                AND start_at < %s AND end_at > %s AND state != 'cancelled'""",
                                     (BARBARA, command["end"], command["start"])).fetchall()
            events, capacity = occupancy(command["start"], command["end"])
            managed_ids = {r["data"].get("barbara", r["data"].get("organizer", {})).get("id") for r in reservations}
            count = len([e for e in events if e["id"] not in managed_ids]) + len(reservations)
            if count >= capacity:
                raise Blocked("slot_at_capacity")
            data = dict(command, stable_id=identity(operation), sender_identity=sender,
                        crm_phase="not_started")
            c.execute("""INSERT INTO bridge_meetings(operation,consultant,task_id,sender,group_name,start_at,end_at,data)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (operation, BARBARA, command["task_id"], sender["id"],
                         group, command["start"], command["end"], Jsonb(data)))
            c.execute("""INSERT INTO bridge_caps(sender,day,used) VALUES (%s,(now() AT TIME ZONE 'UTC')::date,1)
                ON CONFLICT(sender,day) DO UPDATE SET used=bridge_caps.used+1""", (sender["id"],))
            if not sticky:
                cursors = dict(rotation["mailbox_cursors"], **{group: sender["id"]})
                c.execute("UPDATE bridge_rotation SET cursor=cursor+1,mailbox_cursors=%s WHERE consultant=%s",
                          (Jsonb(cursors), BARBARA))
            c.execute("INSERT INTO bridge_jobs(operation) VALUES (%s)", (operation,))
            self.audit(c, operation, "reserved", {"sender": sender["id"], "group": group, "sticky": sticky})
        return self.get(operation)

    @contextmanager
    def meeting_lock(self, operation):
        # Session advisory lock survives step commits. Expired job leases cannot cause
        # concurrent provider writes; connection loss/crash releases it automatically.
        with self.connect() as c:
            c.autocommit = True
            locked = c.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS locked", (operation,)).fetchone()["locked"]
            try:
                yield locked
            finally:
                if locked:
                    c.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (operation,))

    def save(self, operation, state, data, action):
        with self.connect() as c:
            from .domain import time_key
            observed = data.get("barbara", data.get("organizer"))
            if observed and "start" in observed and "end" in observed:
                start, end = time_key(observed)
                c.execute("UPDATE bridge_meetings SET start_at=%s,end_at=%s WHERE operation=%s", (start[0], end[0], operation))
            c.execute("UPDATE bridge_meetings SET state=%s,data=%s,updated_at=now() WHERE operation=%s",
                      (state, Jsonb(data), operation))
            self.audit(c, operation, action)

    def claim(self):
        token = str(uuid.uuid4())
        with self.connect() as c:
            return c.execute("""UPDATE bridge_jobs SET lease_token=%s,lease_until=now()+interval '120 seconds',
                attempts=attempts+1 WHERE operation=(SELECT operation FROM bridge_jobs
                WHERE due_at<=now() AND (lease_until IS NULL OR lease_until<now())
                ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""", (token,)).fetchone()

    def finish_job(self, job, delay, error=None):
        with self.connect() as c:
            c.execute("""UPDATE bridge_jobs SET due_at=now()+%s*interval '1 second',lease_until=NULL,
                lease_token=NULL,last_error=%s,attempts=CASE WHEN %s::text IS NULL THEN 0 ELSE attempts END
                WHERE operation=%s AND lease_token=%s""", (delay, error, error, job["operation"], job["lease_token"]))

    def enqueue(self, operation):
        with self.connect() as c:
            c.execute("UPDATE bridge_jobs SET due_at=now() WHERE operation=%s", (operation,))

    def heartbeat(self):
        with self.connect() as c:
            c.execute("INSERT INTO bridge_worker_health(name) VALUES ('worker') ON CONFLICT(name) DO UPDATE SET seen_at=now()")

    def ready(self):
        with self.connect() as c:
            version = c.execute("SELECT max(version) AS v FROM bridge_schema").fetchone()["v"]
            worker = c.execute("SELECT seen_at > now()-interval '180 seconds' AS ok FROM bridge_worker_health WHERE name='worker'").fetchone()
            return version == 1 and bool(worker and worker["ok"])


if __name__ == "__main__":
    from .config import Settings
    settings = Settings.load()
    store = Store(settings.database_url)
    store.migrate()
    store.register(settings.registry)
