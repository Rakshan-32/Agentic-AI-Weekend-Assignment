"""Lab booking tools split by least privilege."""
from datetime import datetime,timezone
from app.idempotency import notification_dedupe_key
from app.lab_db import LabDb
from app.tools.dispatch import dispatch
class Toolset:
    SIDE_EFFECTS=();DELEGATES=();TOOL_NAMES=()
    def functions(self):return {n:getattr(self,n) for n in self.TOOL_NAMES}
    def call(self,name,args):return dispatch(self.functions(),name,args)
class InventoryTools(Toolset):
    """Read-only specialist: can inspect equipment but cannot book or notify."""
    TOOL_NAMES=("search_equipment","get_equipment")
    def __init__(self,db):self.db=db
    def search_equipment(self,text:str)->dict:
        """Find lab equipment by name or category. Use for availability/discovery questions; do not use to book or change stock. Read-only and changes nothing. Returns up to five equipment records with ids, training requirement and current units available."""
        if not text.strip():return {"error":"empty_query","hint":"Pass an equipment name or category."}
        rows=self.db.search_equipment(text);return {"equipment":[{"equipment_id":r["id"],"name":r["name"],"category":r["category"],"requires_training":bool(r["requires_training"]),"units_available":r["units_available"]} for r in rows]}
    def get_equipment(self,equipment_id:int)->dict:
        """Get current details for one known equipment id. Use after search_equipment when exact stock or training requirement is needed. Do not use for booking; this is read-only and changes nothing. Returns equipment details or unknown_equipment."""
        e=self.db.get_equipment(equipment_id)
        if not e:return {"error":"unknown_equipment","hint":"Use search_equipment first."}
        return {"equipment_id":e["id"],"name":e["name"],"category":e["category"],"requires_training":bool(e["requires_training"]),"units_total":e["units_total"],"units_available":e["units_available"]}
class BookingTools(Toolset):
    TOOL_NAMES=("get_student","check_can_book","book_equipment","notify_student");SIDE_EFFECTS=("book_equipment","notify_student")
    def __init__(self,db,roll_no,clock=lambda:datetime.now(timezone.utc)):self.db,self.roll_no,self.clock=db,roll_no,clock
    def _student(self):
        s=self.db.get_student(self.roll_no)
        if not s:raise LookupError(f"student {self.roll_no} not found")
        return s
    def get_student(self)->dict:
        """Get the current student's lab profile and bookings. Use for questions about training status or existing bookings; never for another roll number. Read-only and changes nothing. Returns identity, training flag, booking limit and active bookings."""
        s=self._student();return {"roll_no":s["roll_no"],"name":s["name"],"dept":s["dept"],"trained":bool(s["trained"]),"max_active_bookings":self.db.policy("max_active_bookings"),"bookings":self.db.active_bookings(s["id"])}
    def check_can_book(self,equipment_id:int)->dict:
        """Check database-backed booking policy for the current student and equipment. Use before book_equipment. Do not decide policy in the prompt. Read-only and changes nothing. Enforces training requirement and maximum active bookings stored in data."""
        s=self._student();e=self.db.get_equipment(equipment_id)
        if not e:return {"can_book":False,"reasons":["unknown equipment"]}
        reasons=[]
        if e["requires_training"] and not s["trained"]:reasons.append("required lab training is not completed")
        held=len(self.db.active_bookings(s["id"]));limit=self.db.policy("max_active_bookings")
        if held>=limit:reasons.append(f"already has {held} of {limit} allowed active bookings")
        return {"can_book":not reasons,"reasons":reasons}
    def book_equipment(self,equipment_id:int,slot:str)->dict:
        """Book one equipment unit for a requested slot. Use only after the student asks to book; the tool rechecks policy itself even if the model skipped check_can_book. CHANGES DATA by creating a booking and decrementing available units. Repeating the same booking is safe."""
        if not slot.strip():return {"error":"invalid_slot","hint":"Provide a non-empty slot."}
        verdict=self.check_can_book(equipment_id)
        if not verdict["can_book"]:return {"error":"not_allowed","reasons":verdict["reasons"],"hint":"Explain the policy reason; do not retry."}
        e=self.db.get_equipment(equipment_id);status=self.db.book(self._student()["id"],equipment_id,slot)
        if status=="no_units":return {"error":"no_units","hint":"No unit is available. Do not retry blindly."}
        return {"equipment_id":equipment_id,"name":e["name"],"slot":slot,"status":status}
    def notify_student(self,message:str)->dict:
        """Queue a short confirmation message to the current student after a successful action. CHANGES DATA by recording an outbound notification. Do not use merely to answer chat questions. Same text on the same day is deduplicated and therefore independently safe to repeat."""
        if not message.strip() or len(message)>160:return {"error":"invalid_message","hint":"message must be 1 to 160 characters."}
        key=notification_dedupe_key(self.roll_no,message,self.clock().date());nid,created=self.db.record_notification(self.roll_no,message,key);return {"notification_id":nid,"status":"queued","duplicate":not created}
