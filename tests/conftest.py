import pytest
from app.lab_db import LabDb
from app.memory import RunStore
class FakeClock:
 def __init__(self,start=1790000000.0):self.now=start
 def __call__(self):return self.now
 def advance(self,seconds):self.now+=seconds
class SimulatedCrash(BaseException):pass
@pytest.fixture
def clock():return FakeClock()
@pytest.fixture
def db():
 d=LabDb(':memory:');d.migrate();return d
@pytest.fixture
def store(clock):
 s=RunStore(':memory:',clock);s.migrate();return s
