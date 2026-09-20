import pytest
from app.providers import demo_providers
from app.worker import Worker
from tests.conftest import SimulatedCrash
Q='Is the Digital Oscilloscope available? If it is, book it for 2026-09-21 10:00 and send me a message.'
def ask(store,roll,text):
 t=store.create_thread(roll);return t,store.enqueue(t,text,'mock')
def test_end_to_end(store,db):
 t,r=ask(store,'22CS045',Q);assert Worker(store,db,demo_providers(),worker_id='w').run_until_idle()==[(r,'succeeded')];assert db.count('booking')==2 and db.count('notification')==1
def test_refusal(store,db):
 t,r=ask(store,'22IT017','Can I book the FPGA Development Board for 2026-09-21 11:00?');Worker(store,db,demo_providers(),worker_id='w').run_until_idle();assert store.get_run(r)['status']=='succeeded' and db.count('booking')==1
def test_crash_replay(store,db,clock):
 _,r=ask(store,'22CS045',Q);real=db.once
 def die(key,name,effect):
  result=real(key,name,effect)
  if name=='book_equipment':raise SimulatedCrash()
  return result
 db.once=die
 with pytest.raises(SimulatedCrash):Worker(store,db,demo_providers(),worker_id='A',lease_seconds=30).run_once()
 db.once=real;assert db.count('booking')==2 and store.get_run(r)['status']=='running';clock.advance(31);assert Worker(store,db,demo_providers(),worker_id='B',lease_seconds=30).run_until_idle()==[(r,'succeeded')];assert db.count('booking')==2 and db.count('notification')==1 and store.get_run(r)['attempts']==2
def test_two_requests_still_one_booking(store,db):
 ask(store,'22CS045',Q);ask(store,'22CS045',Q);Worker(store,db,demo_providers(),worker_id='w').run_until_idle();assert db.count('booking')==2 and db.count('notification')==1
