"""lab.db: students, equipment, bookings and policies."""
import json,time
from collections.abc import Callable
from pathlib import Path
from app.db import connect,transaction
SCHEMA=Path(__file__).resolve().parent.parent/"schema"/"lab.sql"
class LabDb:
    def __init__(self,path: str=":memory:",clock: Callable[[],float]=time.time):
        self.conn=connect(path);self.clock=clock
    def transaction(self): return transaction(self.conn)
    def migrate(self):
        self.conn.executescript(SCHEMA.read_text())
        if self.conn.execute("SELECT count(*) FROM student").fetchone()[0]: return
        with self.transaction() as c:
            c.executemany("INSERT INTO student VALUES (?,?,?,?,?)",[(1,"22CS045","Priya Raman","CSE",1),(2,"22IT017","Arjun Kumar","IT",0),(3,"22EC031","Divya Sekar","ECE",1)])
            c.executemany("INSERT INTO equipment VALUES (?,?,?,?,?,?,0)",[(1,"Arduino Uno Kit","embedded systems",0,3,3),(2,"Digital Oscilloscope","electronics",1,1,1),(3,"FPGA Development Board","digital design",1,2,1),(4,"Raspberry Pi 5 Kit","iot",0,2,2)])
            c.executemany("INSERT INTO policy VALUES (?,?)",[("max_active_bookings",2)])
            c.execute("INSERT INTO booking(student_id,equipment_id,slot,created_at) VALUES(3,3,'2026-09-21 14:00',?)",(self.clock(),))
    def get_student(self,roll_no):
        r=self.conn.execute("SELECT * FROM student WHERE roll_no=?",(roll_no,)).fetchone();return dict(r) if r else None
    def policy(self,name): return self.conn.execute("SELECT value FROM policy WHERE name=?",(name,)).fetchone()[0]
    def active_bookings(self,student_id):
        rows=self.conn.execute("SELECT b.equipment_id,e.name,b.slot FROM booking b JOIN equipment e ON e.id=b.equipment_id WHERE b.student_id=? ORDER BY b.id",(student_id,)).fetchall();return [dict(r) for r in rows]
    def search_equipment(self,text,limit=5):
        like=f"%{text.strip()}%";rows=self.conn.execute("SELECT id,name,category,requires_training,units_available FROM equipment WHERE name LIKE ? OR category LIKE ? ORDER BY name LIMIT ?",(like,like,limit)).fetchall();return [dict(r) for r in rows]
    def get_equipment(self,equipment_id):
        r=self.conn.execute("SELECT * FROM equipment WHERE id=?",(equipment_id,)).fetchone();return dict(r) if r else None
    def count(self,table): assert table.isidentifier();return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    def book(self,student_id,equipment_id,slot):
        """Atomic and repeat-safe booking. Returns booked/already_booked/no_units."""
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM booking WHERE student_id=? AND equipment_id=? AND slot=?",(student_id,equipment_id,slot)).fetchone(): return "already_booked"
            version=c.execute("SELECT version FROM equipment WHERE id=?",(equipment_id,)).fetchone()[0]
            took=c.execute("UPDATE equipment SET units_available=units_available-1,version=version+1 WHERE id=? AND units_available>0 AND version=?",(equipment_id,version)).rowcount
            if not took:return "no_units"
            c.execute("INSERT INTO booking(student_id,equipment_id,slot,created_at) VALUES(?,?,?,?)",(student_id,equipment_id,slot,self.clock()));return "booked"
    def record_notification(self,roll_no,message,dedupe_key):
        cur=self.conn.execute("INSERT INTO notification(roll_no,message,dedupe_key,created_at) VALUES(?,?,?,?) ON CONFLICT(dedupe_key) DO NOTHING",(roll_no,message,dedupe_key,self.clock()))
        if cur.rowcount==1:return cur.lastrowid,True
        return self.conn.execute("SELECT id FROM notification WHERE dedupe_key=?",(dedupe_key,)).fetchone()[0],False
    def once(self,key,tool_name,effect):
        with self.transaction() as c:
            row=c.execute("SELECT result FROM idempotency WHERE key=?",(key,)).fetchone()
            if row:return json.loads(row["result"]),False
            result=effect();c.execute("INSERT INTO idempotency VALUES(?,?,?,?)",(key,tool_name,json.dumps(result,default=str),self.clock()));return result,True
