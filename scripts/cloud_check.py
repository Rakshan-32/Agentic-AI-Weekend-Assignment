"""Safe connectivity check: prints counts only, never credentials."""
from app.config import SUPABASE_DB_URL,open_stores
if not SUPABASE_DB_URL:
    raise SystemExit('SUPABASE_DB_URL is not set in .env')
store,db=open_stores()
print('Supabase connection: PASS')
print('equipment:',db.count('equipment'))
print('students:',db.count('student'))
print('bookings:',db.count('booking'))
print('runs:',db.count('run'))
