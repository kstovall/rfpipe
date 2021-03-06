from __future__ import print_function, division, absolute_import #, unicode_literals # not casa compatible
from builtins import bytes, dict, object, range, map, input#, str # not casa compatible
from future.utils import itervalues, viewitems, iteritems, listvalues, listitems
from io import open

import distributed
from rfpipe import source, search, util, candidates

import logging
logger = logging.getLogger(__name__)
vys_timeout_default = 10


def pipeline_scan_distributed(st, segments=None, host='cbe-node-01',
                              cfile=None, vys_timeout=vys_timeout_default):
    """ Given rfpipe state and dask distributed client, run search pipline """

    cl = distributed.Client('{0}:{1}'.format(host, '8786'))

    saved = []
    if not isinstance(segments, list):
        segments = range(st.nsegment)

    for segment in segments:
        saved.append(pipeline_seg(st, segment, cl=cl, cfile=cfile,
                                  vys_timeout=vys_timeout))

    return saved


def pipeline_seg(st, segment, cl=None, cfile=None,
                 vys_timeout=vys_timeout_default):
    """ Submit pipeline processing of a single segment to scheduler.
    Can use distributed client or compute locally.

    Uses distributed resources parameter to control scheduling of GPUs.
    Pipeline produces jobs per DM/dt and returns the state as a handle to each.
    """

    logger.info('Building dask for observation {0}, scan {1}, segment {2}.'
                .format(st.metadata.filename, st.metadata.scan, segment))

    mode = 'single' if st.prefs.nthread == 1 else 'multi'

    if not cl:
        cl = distributed.Client(n_workers=1, threads_per_worker=1)

    # plan, if using fftw
    wisdom = cl.submit(search.set_wisdom, st.npixx, st.npixy, pure=True) if st.fftmode == 'fftw' else None

    data = cl.submit(source.read_segment, st, segment, timeout=vys_timeout,
                     cfile=cfile, pure=True)
#                     resources={'MEMORY': 1.1*st.vismem})
    data_prep = cl.submit(source.data_prep, st, data, pure=True)
#                          resources={'MEMORY': 1.1*st.vismem})

    saved = []
    for dmind in range(len(st.dmarr)):
        delay = cl.submit(util.calc_delay, st.freq, st.freq.max(),
                          st.dmarr[dmind], st.inttime, pure=True)
        data_dm = cl.submit(search.dedisperse, data_prep, delay, mode=mode,
                            pure=True)
#                           , resources={'MEMORY': 1.1*st.vismem})

        for dtind in range(len(st.dtarr)):
            data_dmdt = cl.submit(search.resample, data_dm, st.dtarr[dtind],
                                  mode=mode, pure=True)
#                                  resources={'MEMORY':
#                                             1.1*st.vismem/st.dtarr[dtind]})
            resources = None if st.fftmode == 'fftw' else {'GPU': 1}
            saved.append(cl.submit(search.search_thresh, st, data_dmdt,
                                   segment, dmind, dtind, wisdom=wisdom,
                                   pure=True, resources=resources))
#                                                'MEMORY': 1.1*st.immem})
#                                     mode='fftw', pure=True,
#                                     resources={'MEMORY': 1.1*st.immem})

    # ** or aggregate over dt or dm trials? **
    canddatalist = cl.submit(mergelists, saved, pure=True)
    features = cl.submit(candidates.calc_features, canddatalist,
                         pure=True)
    return cl.submit(candidates.save_cands, st, features, canddatalist,
                     pure=True)


def mergelists(futlists):
    """ Take list of lists and return single list
    ** TODO: could put logic here to find islands, peaks, etc?
    """

    return [fut for futlist in futlists for fut in futlist]


def pipeline_seg2(st, segment, cfile=None, vys_timeout=vys_timeout_default):
    """ Submit pipeline processing of a single segment to scheduler.
    No multi-threading or scheduling.
    """

    # plan fft
    wisdom = search.set_wisdom(st.npixx, st.npixy)

    data = source.read_segment(st, segment, timeout=vys_timeout, cfile=cfile)
    data_prep = source.data_prep(st, data)

    for dmind in range(len(st.dmarr)):
        delay = util.calc_delay(st.freq, st.freq.max(), st.dmarr[dmind],
                                st.inttime)
        data_dm = search.dedisperse(data_prep, delay)

        for dtind in range(len(st.dtarr)):
            data_dmdt = search.resample(data_dm, st.dtarr[dtind])
            canddatalist = search.search_thresh(st, data_dmdt, segment, dmind,
                                                dtind, wisdom=wisdom)

            features = candidates.calc_features(canddatalist)
            search.save_cands(st, features, canddatalist)
