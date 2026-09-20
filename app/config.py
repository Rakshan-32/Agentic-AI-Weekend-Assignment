import os
from dotenv import load_dotenv
from app.lab_db import LabDb
from app.memory import RunStore

load_dotenv()
AGENT_DB=os.environ.get('AGENT_DB','agent.db')
LAB_DB=os.environ.get('LAB_DB','lab.db')
SUPABASE_DB_URL=os.environ.get('SUPABASE_DB_URL','').strip()
GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-2.5-flash')

def open_stores():
    if SUPABASE_DB_URL:
        from app.cloud_db import CloudRunStore,CloudLabDb
        store,db=CloudRunStore(SUPABASE_DB_URL),CloudLabDb(SUPABASE_DB_URL)
    else:
        store,db=RunStore(AGENT_DB),LabDb(LAB_DB)
    store.migrate();db.migrate();return store,db

def make_providers(mock:bool,slow:float=0.0)->dict:
    if mock:
        from app.providers import demo_providers
        return demo_providers(slow)
    from app.providers import GeminiProvider
    gemini=GeminiProvider(GEMINI_MODEL)
    return {'supervisor':gemini,'inventory':gemini,'booking':gemini}
