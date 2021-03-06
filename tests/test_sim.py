import rfpipe
import pytest
from astropy import time
import sys
import os
import distributed

# ** is this needed?
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../')

# simulate no flag, transient/no flag, transient/flag
inprefs = [{'flaglist': [], 'npix_max': 512},
#           {'read_tdownsample': 2, 'read_fdownsample': 2, 'npix_max': 512},
           {'simulated_transient': [(1., 30, 25, 5e-3, 0.001, 0.001)],
            'maxdm': 50, 'dtarr': [1, 2], 'npix_max': 512, 'savecands': True,
            'savenoise': True}]


@pytest.fixture(scope="module", params=inprefs)
def mockstate(request):
    t0 = time.Time.now().mjd
    meta = rfpipe.metadata.mock_metadata(t0, t0+0.5/(24*3600), 27, 4, 2, 5e3,
                                         datasource='sim')
    return rfpipe.state.State(inmeta=meta, inprefs=request.param)


# simulate two DMs
@pytest.fixture(scope="module")
def mockdata(mockstate):
    segment = 0
    data = rfpipe.source.read_segment(mockstate, segment)
    return rfpipe.source.data_prep(mockstate, data)


@pytest.fixture(scope="module", params=[10, 100])
def mockdm(request, mockstate, mockdata):
    delay = rfpipe.util.calc_delay(mockstate.freq, mockstate.freq.max(),
                                   request.param, mockstate.inttime)
    return rfpipe.search.dedisperse(mockdata, delay)


@pytest.fixture(scope="module")
def wisdom(mockstate):
    return rfpipe.search.set_wisdom(mockstate.npixx, mockstate.npixy)


def test_dataprep(mockstate, mockdata):
    assert mockdata.shape == mockstate.datashape


def test_search(mockstate, mockdm, wisdom):
    segment = 0
    dmind = 0
    dtind = 0
    canddatalist = rfpipe.search.search_thresh(mockstate, mockdm, segment,
                                               dmind, dtind, wisdom=wisdom)

    features = rfpipe.candidates.calc_features(canddatalist)
    assert type(features) == dict

    if mockstate.prefs.simulated_transient:
        print(mockstate.prefs.simulated_transient, mockstate.prefs.flaglist)
        assert len(features)


def test_pipeline(mockstate):
    res = rfpipe.pipeline.pipeline_seg(mockstate, 0)

    assert len(res) == len(mockstate.dmarr)*len(mockstate.dtarr)


def test_pipeline_distributed(mockstate):
    cl = distributed.client.Client()
    res = rfpipe.pipeline.pipeline_seg(mockstate, 0, cl=cl)

    assert len(res) == len(mockstate.dmarr)*len(mockstate.dtarr)
