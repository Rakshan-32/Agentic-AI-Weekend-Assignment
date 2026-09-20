"""End-to-end proof. Run: python -m scripts.demo | python -m scripts.demo --crash"""
import argparse,os,tempfile
from scripts._term import CYAN,DIM,GREEN,RED,RESET,print_step
QUESTIONS=[("22CS045","Is the Digital Oscilloscope available? If it is, book it for 2026-09-21 10:00 and send me a message."),("22IT017","Can I book the FPGA Development Board for 2026-09-21 11:00?")]
class Crash(BaseException):pass
def counts(db):return f"bookings {db.count('booking')}   notifications {db.count('notification')}   idempotency keys {db.count('idempotency')}"
def main():
 p=argparse.ArgumentParser();p.add_argument('--real',action='store_true');p.add_argument('--crash',action='store_true');a=p.parse_args()
 tmp=tempfile.mkdtemp(prefix='lab-agent-demo-');os.environ['AGENT_DB'],os.environ['LAB_DB']=os.path.join(tmp,'agent.db'),os.path.join(tmp,'lab.db')
 from app.config import make_providers,open_stores
 from app.worker import Worker
 store,db=open_stores();providers=make_providers(mock=not a.real);print(f"{DIM}databases in {tmp}   model: {providers['supervisor'].model}{RESET}");print(f"{DIM}before: {counts(db)}{RESET}\n")
 for roll_no,text in (QUESTIONS[:1] if a.crash else QUESTIONS):
  thread=store.create_thread(roll_no);run_id=store.enqueue(thread,text,providers['supervisor'].model);print(f"{CYAN}{roll_no}>{RESET} {text}")
  if a.crash:
   real_once=db.once
   def once_then_die(key,tool_name,effect):
    result=real_once(key,tool_name,effect)
    if tool_name=='book_equipment':raise Crash()
    return result
   db.once=once_then_die
   try:Worker(store,db,providers,worker_id='worker-A',lease_seconds=60,on_step=print_step).run_once()
   except Crash:
    db.once=real_once;print(f"\n  {RED}worker-A died right after writing the booking{RESET}");print(f"  {DIM}{counts(db)}; run is '{store.get_run(run_id)['status']}'{RESET}");store.clock=lambda:__import__('time').time()+61;print(f"  {DIM}...lease expires, worker-B claims the run{RESET}\n")
   Worker(store,db,providers,worker_id='worker-B',lease_seconds=60,on_step=print_step).run_until_idle()
  else:Worker(store,db,providers,worker_id='demo-worker',on_step=print_step).run_until_idle()
  run=store.get_run(run_id);colour=GREEN if run['status']=='succeeded' else RED;reply=store.load_history(thread)[-1]['text'] if run['status']=='succeeded' else run['error_code'];print(f"{colour}assistant>{RESET} {reply}");print(f"{DIM}run {run_id[:8]} {run['status']} after {run['attempts']} attempt(s){RESET}\n")
 print(f"after:  {counts(db)}")
 if a.crash:
  ok=db.count('booking')==2 and db.count('notification')==1;print(f"{GREEN}PASS: one new booking, one message; crash replay created no duplicates{RESET}" if ok else f"{RED}FAIL: duplicates{RESET}")
if __name__=='__main__':main()
