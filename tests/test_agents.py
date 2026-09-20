from app.agents import SupervisorTools,run_specialist,run_tool
from app.providers import ModelTurn,ScriptedProvider,ToolCall,demo_providers
from app.tools.lab_tools import InventoryTools
def test_supervisor_only_delegates(db):
 t=SupervisorTools(db,demo_providers(),'22CS045');assert set(t.functions())=={'ask_inventory','ask_booking'}
def test_inventory_specialist(db):
 r,_=run_tool(SupervisorTools(db,demo_providers(),'22CS045'),db,'k','ask_inventory',{'question':'Is the Digital Oscilloscope available?'});assert r['agent']=='inventory' and r['tools_used']==['search_equipment']
def test_booking_specialist(db):
 r,_=run_tool(SupervisorTools(db,demo_providers(),'22CS045'),db,'k','ask_booking',{'request':'Book equipment 2 (Digital Oscilloscope) for 2026-09-21 10:00 and message the student to confirm.'});assert r['tools_used']==['check_can_book','book_equipment','notify_student'];assert db.count('notification')==1
def test_repeated_delegation_safe(db):
 t=SupervisorTools(db,demo_providers(),'22CS045');a={'request':'Book equipment 2 (Digital Oscilloscope) for 2026-09-21 10:00 and message the student to confirm.'};run_tool(t,db,'same', 'ask_booking',a);run_tool(t,db,'same','ask_booking',a);assert db.count('booking')==2 and db.count('notification')==1
def test_bad_args(db):
 r,_=run_tool(SupervisorTools(db,demo_providers(),'22CS045'),db,'k','ask_booking',{'request':''});assert r['error']=='invalid_arguments'
def test_loop_stops(db):
 p=ScriptedProvider([ModelTurn(text=None,tool_calls=[ToolCall('search_equipment',{'text':'kit'})])],loop=True);r=run_specialist('inventory','sys',InventoryTools(db),db=db,provider=p,task='x',parent_key='k');assert r['error']=='specialist_step_limit'
def test_inventory_has_no_writes(db):assert InventoryTools.SIDE_EFFECTS==()
