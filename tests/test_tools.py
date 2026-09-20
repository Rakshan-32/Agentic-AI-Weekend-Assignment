import inspect,pytest
from app.tools.lab_tools import InventoryTools,BookingTools
@pytest.mark.parametrize('cls',[InventoryTools,BookingTools])
def test_every_tool_is_described(cls):
 for name in cls.TOOL_NAMES:assert len(inspect.getdoc(getattr(cls,name)) or '')>=120,name
def test_search(db):
 x=InventoryTools(db).search_equipment('Oscilloscope')['equipment'];assert x[0]['equipment_id']==2 and x[0]['units_available']==1
def test_empty_search(db):assert InventoryTools(db).search_equipment(' ')['error']=='empty_query'
def test_policy_from_db(db):
 t=BookingTools(db,'22CS045');assert t.check_can_book(1)['can_book'];db.conn.execute("UPDATE policy SET value=0 WHERE name='max_active_bookings'");assert not t.check_can_book(1)['can_book']
def test_training_rule(db):assert 'training' in BookingTools(db,'22IT017').check_can_book(2)['reasons'][0]
def test_write_rechecks_policy(db):assert BookingTools(db,'22IT017').book_equipment(2,'x')['error']=='not_allowed'
def test_repeat_booking_safe(db):
 t=BookingTools(db,'22CS045');assert t.book_equipment(2,'slot')['status']=='booked';assert t.book_equipment(2,'slot')['status']=='already_booked';assert db.get_equipment(2)['units_available']==0
def test_last_unit(db):
 assert BookingTools(db,'22CS045').book_equipment(2,'a')['status']=='booked';assert BookingTools(db,'22EC031').book_equipment(2,'b')['error']=='no_units'
def test_notification_dedupe(db):
 t=BookingTools(db,'22CS045');a=t.notify_student('Booked.');b=t.notify_student('Booked.');assert a['notification_id']==b['notification_id'] and b['duplicate']
def test_bound_identity(db):
 params={n:list(inspect.signature(getattr(BookingTools,n)).parameters) for n in BookingTools.TOOL_NAMES};assert all('roll_no' not in p for p in params.values())

def test_race_for_last_unit_only_one_wins(tmp_path):
    """Higher-grade option: two threads race for the final oscilloscope unit."""
    import threading
    from app.lab_db import LabDb
    path=str(tmp_path/'race.db')
    seed=LabDb(path);seed.migrate()
    results=[]
    def attempt(roll,slot):
        local=LabDb(path)
        results.append(BookingTools(local,roll).book_equipment(2,slot).get('status','no_units'))
    a=threading.Thread(target=attempt,args=('22CS045','slot-a'))
    b=threading.Thread(target=attempt,args=('22EC031','slot-b'))
    a.start();b.start();a.join();b.join()
    assert results.count('booked')==1
    assert LabDb(path).get_equipment(2)['units_available']==0
