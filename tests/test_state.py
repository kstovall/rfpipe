import pytest
import rfpipe
from astropy import time
import sys, os
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../')


def test_create():
    st = rfpipe.state.State()
    assert st.metadata.atdefaults()


@pytest.fixture(scope="module")
def mockstate():
        t0 = time.Time.now().mjd
        meta = rfpipe.metadata.mock_metadata(t0, t0+0.3/(24*3600), 27, 4, 2,
                                             5e3, datasource='sim')
        return rfpipe.state.State(inmeta=meta)


def test_mock(mockstate):
        assert mockstate.datashape == (60, 351, 128, 2)


def test_mocknseg(mockstate):
    assert mockstate.nsegment == 1
