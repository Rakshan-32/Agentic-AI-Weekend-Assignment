"""Supabase/PostgreSQL stores. Used when SUPABASE_DB_URL is present.
SQLite remains the zero-config/offline grading path required by the brief.
"""
import json,time,uuid
from contextlib import contextmanager
from dataclasses import dataclass
from psycopg import connect
from psycopg.rows import dict_row

@dataclass(frozen=True)
class Claimed:
    run_id:str; thread_id:str; attempts:int

class PgBase:
    def __init__(self,url,clock=time.time):
        self.conn=connect(url,row_factory=dict_row,autocommit=True);self.clock=clock
    @contextmanager
    def transaction(self):
        with self.conn.transaction(): yield self.conn
    def close(self): self.conn.close()

class CloudLabDb(PgBase):
    def migrate(self):
        # Schema is provisioned in Supabase from schema/supabase.sql.
        with self.conn.cursor() as c:
            c.execute("SELECT 1 FROM equipment LIMIT 1")
    def get_student(self,roll_no):
        r=self.conn.execute("SELECT * FROM student WHERE roll_no=%s",(roll_no,)).fetchone();return dict(r) if r else None
    def policy(self,name): return self.conn.execute("SELECT value FROM policy WHERE name=%s",(name,)).fetchone()['value']
    def active_bookings(self,student_id):
        return list(self.conn.execute("SELECT b.equipment_id,e.name,b.slot FROM booking b JOIN equipment e ON e.id=b.equipment_id WHERE b.student_id=%s ORDER BY b.id",(student_id,)).fetchall())
    def search_equipment(self,text,limit=5):
        like=f"%{text.strip()}%";return list(self.conn.execute("SELECT id,name,category,requires_training,units_available FROM equipment WHERE name ILIKE %s OR category ILIKE %s ORDER BY name LIMIT %s",(like,like,limit)).fetchall())
    def get_equipment(self,equipment_id):
        r=self.conn.execute("SELECT * FROM equipment WHERE id=%s",(equipment_id,)).fetchone();return dict(r) if r else None
    def count(self,table):
        allowed={'student','equipment','policy','booking','notification','idempotency','thread','message','run','run_step','tool_call'}
        if table not in allowed: raise ValueError('invalid table')
        return self.conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()['n']
    def book(self,student_id,equipment_id,slot):
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM booking WHERE student_id=%s AND equipment_id=%s AND slot=%s",(student_id,equipment_id,slot)).fetchone(): return 'already_booked'
            row=c.execute("UPDATE equipment SET units_available=units_available-1,version=version+1 WHERE id=%s AND units_available>0 RETURNING id",(equipment_id,)).fetchone()
            if not row:return 'no_units'
            c.execute("INSERT INTO booking(student_id,equipment_id,slot,created_at) VALUES(%s,%s,%s,now())",(student_id,equipment_id,slot));return 'booked'
    def record_notification(self,roll_no,message,dedupe_key):
        with self.transaction() as c:
            r=c.execute("INSERT INTO notification(roll_no,message,dedupe_key,created_at) VALUES(%s,%s,%s,now()) ON CONFLICT(dedupe_key) DO NOTHING RETURNING id",(roll_no,message,dedupe_key)).fetchone()
            if r:return r['id'],True
            return c.execute("SELECT id FROM notification WHERE dedupe_key=%s",(dedupe_key,)).fetchone()['id'],False
    def once(self,key,tool_name,effect):
        # Advisory lock serializes the same deterministic idempotency key across workers.
        with self.transaction() as c:
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(key,))
            row=c.execute("SELECT result FROM idempotency WHERE key=%s",(key,)).fetchone()
            if row:return row['result'] if isinstance(row['result'],dict) else json.loads(row['result']),False
            result=effect();c.execute("INSERT INTO idempotency(key,tool_name,result,created_at) VALUES(%s,%s,%s::jsonb,now())",(key,tool_name,json.dumps(result,default=str)));return result,True

class CloudRunStore(PgBase):
    def migrate(self): self.conn.execute("SELECT 1 FROM run LIMIT 1")
    def create_thread(self,student_id):
        tid=str(uuid.uuid4());self.conn.execute("INSERT INTO thread(id,student_id) VALUES(%s,%s)",(tid,student_id));return tid
    def get_thread(self,thread_id):
        r=self.conn.execute("SELECT * FROM thread WHERE id=%s",(thread_id,)).fetchone();return dict(r) if r else None
    def append_message(self,thread_id,role,text):
        r=self.conn.execute("INSERT INTO message(thread_id,seq,role,text) VALUES(%s,(SELECT COALESCE(MAX(seq),0)+1 FROM message WHERE thread_id=%s),%s,%s) RETURNING seq",(thread_id,thread_id,role,text)).fetchone();return r['seq']
    def load_history(self,thread_id): return list(self.conn.execute("SELECT seq,role,text FROM message WHERE thread_id=%s ORDER BY seq",(thread_id,)).fetchall())
    def record_model_step(self,run_id,seq,tokens_in,tokens_out,text,tool_calls):
        with self.transaction() as c:
            r=c.execute("INSERT INTO run_step(run_id,seq,kind,tokens_in,tokens_out,text,tool_calls) VALUES(%s,%s,'model',%s,%s,%s,%s::jsonb) RETURNING id",(run_id,seq,tokens_in,tokens_out,text,json.dumps(tool_calls))).fetchone()
            c.execute("UPDATE run SET tokens_in=tokens_in+%s,tokens_out=tokens_out+%s WHERE id=%s",(tokens_in,tokens_out,run_id));return r['id']
    def record_tool_call(self,run_id,seq,name,args,result,ok,latency_ms,idempotency_key=None):
        with self.transaction() as c:
            sid=c.execute("INSERT INTO run_step(run_id,seq,kind) VALUES(%s,%s,'tool') RETURNING id",(run_id,seq)).fetchone()['id']
            c.execute("INSERT INTO tool_call(run_step_id,tool_name,args,result,ok,latency_ms,idempotency_key) VALUES(%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)",(sid,name,json.dumps(args,default=str),json.dumps(result,default=str),ok,latency_ms,idempotency_key));return sid
    def load_steps(self,run_id):
        rows=self.conn.execute("SELECT s.seq,s.kind,s.text,s.tool_calls,t.tool_name,t.args,t.result,t.ok FROM run_step s LEFT JOIN tool_call t ON t.run_step_id=s.id WHERE s.run_id=%s ORDER BY s.seq",(run_id,)).fetchall();return [dict(r) for r in rows]
    def get_run(self,run_id):
        r=self.conn.execute("SELECT * FROM run WHERE id=%s",(run_id,)).fetchone();return {**dict(r),'steps':self.load_steps(run_id)} if r else None
    def enqueue(self,thread_id,text,model,max_attempts=3):
        rid=str(uuid.uuid4())
        with self.transaction() as c:
            self.append_message(thread_id,'user',text);c.execute("INSERT INTO run(id,thread_id,status,model,max_attempts,available_at) VALUES(%s,%s,'queued',%s,%s,%s)",(rid,thread_id,model,max_attempts,self.clock()))
        return rid
    def claim_next(self,worker_id,lease_seconds):
        now=self.clock()
        with self.transaction() as c:
            row=c.execute("SELECT id,thread_id,attempts FROM run WHERE status='queued' AND available_at<=%s ORDER BY available_at,created_at FOR UPDATE SKIP LOCKED LIMIT 1",(now,)).fetchone()
            if not row:return None
            c.execute("UPDATE run SET status='running',lease_owner=%s,lease_until=%s,attempts=attempts+1,started_at=COALESCE(started_at,now()) WHERE id=%s",(worker_id,now+lease_seconds,row['id']));return Claimed(row['id'],row['thread_id'],row['attempts']+1)
    def heartbeat(self,run_id,worker_id,lease_seconds): return self.conn.execute("UPDATE run SET lease_until=%s WHERE id=%s AND status='running' AND lease_owner=%s",(self.clock()+lease_seconds,run_id,worker_id)).rowcount==1
    def reap_expired(self):
        now=self.clock()
        with self.transaction() as c:
            rows=c.execute("SELECT id,attempts,max_attempts FROM run WHERE status='running' AND lease_until<%s FOR UPDATE",(now,)).fetchall()
            for r in rows:
                if r['attempts']>=r['max_attempts']:c.execute("UPDATE run SET status='dead',error_code='lease_expired',lease_owner=NULL,lease_until=NULL,finished_at=now() WHERE id=%s",(r['id'],))
                else:c.execute("UPDATE run SET status='queued',error_code='lease_expired',lease_owner=NULL,lease_until=NULL,available_at=%s WHERE id=%s",(now,r['id']))
            return [r['id'] for r in rows]
    def complete(self,run_id,worker_id,reply):
        with self.transaction() as c:
            row=c.execute("SELECT thread_id FROM run WHERE id=%s AND status='running' AND lease_owner=%s FOR UPDATE",(run_id,worker_id)).fetchone()
            if not row:return False
            self.append_message(row['thread_id'],'model',reply);c.execute("UPDATE run SET status='succeeded',lease_owner=NULL,lease_until=NULL,error_code=NULL,finished_at=now() WHERE id=%s",(run_id,));return True
    def request_cancel(self,run_id):
        with self.transaction() as c:
            row=c.execute("SELECT status FROM run WHERE id=%s FOR UPDATE",(run_id,)).fetchone()
            if not row:return None
            if row['status']=='queued':c.execute("UPDATE run SET status='cancelled',finished_at=now() WHERE id=%s",(run_id,));return 'cancelled'
            if row['status']=='running':c.execute("UPDATE run SET cancel_requested=true WHERE id=%s",(run_id,))
            return row['status']
    def cancel_requested(self,run_id):
        r=self.conn.execute("SELECT cancel_requested FROM run WHERE id=%s",(run_id,)).fetchone();return bool(r['cancel_requested'])
    def mark_cancelled(self,run_id,worker_id): return self.conn.execute("UPDATE run SET status='cancelled',lease_owner=NULL,lease_until=NULL,finished_at=now() WHERE id=%s AND status='running' AND lease_owner=%s",(run_id,worker_id)).rowcount==1
    def fail_attempt(self,run_id,worker_id,error_code,retryable,backoff_seconds=2.0):
        with self.transaction() as c:
            row=c.execute("SELECT attempts,max_attempts FROM run WHERE id=%s AND status='running' AND lease_owner=%s FOR UPDATE",(run_id,worker_id)).fetchone()
            if not row:return None
            if retryable and row['attempts']<row['max_attempts']:
                delay=backoff_seconds*2**(row['attempts']-1);c.execute("UPDATE run SET status='queued',error_code=%s,lease_owner=NULL,lease_until=NULL,available_at=%s WHERE id=%s",(error_code,self.clock()+delay,run_id));return 'queued'
            status='dead' if retryable else 'failed';c.execute("UPDATE run SET status=%s,error_code=%s,lease_owner=NULL,lease_until=NULL,finished_at=now() WHERE id=%s",(status,error_code,run_id));return status
