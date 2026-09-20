"""Three-agent lab booking service. A supervisor delegates to least-privilege specialists.

    student -> supervisor -> ask_inventory -> inventory agent (search_equipment, get_equipment)
                          -> ask_booking   -> booking agent (get_student, check_can_book, book_equipment, notify_student)

Each specialist is an ordinary agent loop with its own system prompt and its own small tool set.
To the supervisor, a specialist is just a tool: "agent as tool", the simplest multi-agent pattern.
"""
import time
from collections.abc import Callable

from app.idempotency import idempotency_key
from app.lab_db import LabDb
from app.providers import AgentError
from app.tools.lab_tools import InventoryTools, BookingTools, Toolset

SPECIALIST_MAX_STEPS = 6

SUPERVISOR_SYSTEM = """You are the Lab Equipment Booking Assistant, talking to the student with roll number {roll_no}.
You never search the inventory or change reservations yourself. Delegate:
- ask_inventory for finding equipment and checking current availability;
- ask_booking for anything about this student's account, bookings, training policy or messages.
Give each specialist a complete, specific request, including equipment ids once you know them.
Then answer the student briefly, using only what the specialists reported."""

CATALOGUE_SYSTEM = """You are the inventory specialist of a campus lab. Find equipment and report its equipment_id, name, category, training requirement and units_available. You cannot book anything. Be brief."""

DESK_SYSTEM = """You are the booking specialist, acting for student {roll_no} only.
Always call check_can_book before book_equipment. Never decide policy yourself: report the reasons the tools give. Confirm a successful booking with notify_student. Report what you did, briefly."""


def run_tool(toolset: Toolset, db: LabDb, key: str, name: str, args: dict) -> tuple[dict, bool]:
    """Run one tool call for any agent. Returns (result, replayed). Never raises, except AgentError.

    Side effects run at most once per key (Day 3); replayed is True when the stored result was returned
    and nothing was done. Delegations hand the key down, so the specialist's side effects get keys
    derived from it: a replayed delegation replays its side effects safely too.
    """
    try:
        if name in toolset.DELEGATES:
            return toolset.delegate(name, args, key), False
        if name in toolset.SIDE_EFFECTS:
            result, fresh = db.once(key, name, lambda: toolset.call(name, args))
            return result, not fresh
        return toolset.call(name, args), False
    except AgentError:
        raise
    except NotImplementedError:
        return {"error": "not_implemented", "hint": f"{name} is not available yet."}, False
    except Exception as e:
        return {"error": "tool_failed", "hint": f"{name} failed ({type(e).__name__}). Try another way or tell the user."}, False


def run_specialist(agent: str, system: str, toolset: Toolset, *, db: LabDb, provider, task: str,
                   parent_key: str, on_step: Callable[[dict], None] | None = None) -> dict:
    """A specialist's whole agent loop, run inside one tool call of the supervisor."""
    contents = [{"role": "user", "text": task}]
    functions = list(toolset.functions().values())
    used = []
    seq = 0
    while seq < SPECIALIST_MAX_STEPS:
        turn = provider.generate(system, contents, functions)
        seq += 1
        if not turn.tool_calls:
            return {"agent": agent, "answer": turn.text or "", "tools_used": used}
        contents.append({"role": "model", "text": turn.text, "raw": turn.raw,
                         "tool_calls": [{"name": c.name, "args": c.args} for c in turn.tool_calls]})
        for call in turn.tool_calls:
            seq += 1
            key = idempotency_key(parent_key, seq, call.name, call.args)
            started = time.perf_counter()
            result, replayed = run_tool(toolset, db, key, call.name, call.args)
            used.append(call.name)
            if on_step:
                on_step({"agent": agent, "kind": "tool", "tool": call.name, "args": call.args, "result": result,
                         "ok": "error" not in result, "replayed": replayed,
                         "ms": round((time.perf_counter() - started) * 1000)})
            contents.append({"role": "tool", "name": call.name, "result": result})
    return {"agent": agent, "error": "specialist_step_limit", "tools_used": used,
            "hint": "The specialist could not finish. Tell the student to try a simpler request."}


class SupervisorTools(Toolset):
    """The supervisor's only tools are the two specialists."""

    TOOL_NAMES = ("ask_inventory", "ask_booking")
    DELEGATES = ("ask_inventory", "ask_booking")

    def __init__(self, db: LabDb, providers: dict, roll_no: str, on_step=None):
        self.db, self.providers, self.roll_no, self.on_step = db, providers, roll_no, on_step

    def ask_inventory(self, question: str) -> dict:
        """Ask the inventory specialist to find equipment or check current unit availability.

        Use for equipment discovery and availability questions. It is read-only and cannot book anything.

        Args:
            question: A complete request, e.g. "Is the Digital Oscilloscope available?"

        Returns:
            {"agent": "inventory", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def ask_booking(self, request: str) -> dict:
        """Ask the booking specialist to act on this student's account. It CAN CHANGE DATA:
        book equipment and send the student messages.

        Use for eligibility, bookings and confirmations. Include the equipment_id and requested slot
        from the inventory when booking. The booking always acts for the current student only.

        Args:
            request: A complete instruction, e.g. "Book equipment 2 for 2026-09-21 10:00 and message the student to confirm."

        Returns:
            {"agent": "booking", "answer": str, "tools_used": [str]}.
        """
        raise RuntimeError("delegations run through delegate()")

    def delegate(self, name: str, args: dict, key: str) -> dict:
        bad = self.call_check(name, args)
        if bad:
            return bad
        if self.on_step:
            self.on_step({"agent": "supervisor", "kind": "delegate", "tool": name, "args": args})
        if name == "ask_inventory":
            return run_specialist("inventory", CATALOGUE_SYSTEM, InventoryTools(self.db), db=self.db,
                                  provider=self.providers["inventory"], task=args["question"],
                                  parent_key=key, on_step=self.on_step)
        return run_specialist("booking", DESK_SYSTEM.format(roll_no=self.roll_no), BookingTools(self.db, self.roll_no),
                              db=self.db, provider=self.providers["booking"], task=args["request"],
                              parent_key=key, on_step=self.on_step)

    def call_check(self, name: str, args: dict) -> dict | None:
        """Validate a delegation's arguments the same way dispatch validates any tool call."""
        field = "question" if name == "ask_inventory" else "request"
        if set(args) != {field} or not isinstance(args[field], str) or not args[field].strip():
            return {"error": "invalid_arguments", "hint": f"{name} takes one non-empty string: {field}."}
        return None
