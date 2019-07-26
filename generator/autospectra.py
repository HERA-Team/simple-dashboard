#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""
Generate a simple dashboard page for the autocorelation spectra.

Adapted from https://github.com/HERA-Team/hera_corr_cm/blob/master/hera_today/redis_autocorr_to_html.py
"""

from __future__ import absolute_import, division, print_function

import time
import re
import redis
import numpy as np
import argparse
from astropy.time import Time

# Two redis instances run on this server.
# port 6379 is the hera-digi mirror
# port 6380 is the paper1 mirror

parser = argparse.ArgumentParser(
    description=('Create auto-correlation spectra plot for heranow dashboard')
)
parser.add_argument('--redishost', dest='redishost', type=str,
                    default='redishost',
                    help=('The host name for redis to connect to, defaults to "redishost"'))
parser.add_argument('--port', dest='port', type=int, default=6379,
                    help='Redis port to connect.')
args = parser.parse_args()
r = redis.Redis(args.redishost, port=args.port)

keys = [k.decode() for k in r.keys()
        if k.startswith(b'auto') and not k.endswith(b'timestamp')]

ants = []
for key in keys:
    match = re.search(r'auto:(?P<ant>\d+)(?P<pol>e|n)', key)
    if match is not None:
        ant, pol = int(match.group('ant')), match.group('pol')
        ants.append(ant)

ants = np.unique(ants)

n_ants = ants.size
# Generate frequency axis
NCHANS = int(2048 // 4 * 3)
NCHANS_F = 8192
NCHAN_SUM = 4
frange = np.linspace(0, 250e6, NCHANS_F + 1)[1536:1536 + (8192 // 4 * 3)]
# average over channels
frange = frange.reshape(NCHANS, NCHAN_SUM).sum(axis=1) / NCHAN_SUM
frange_str = ', '.join('%f' % freq for freq in frange)
linenames = []

# All this code does is build an html file
# containing a bunch of javascript nonsense.
# define the start and end text of the file here,
# then dynamically populate the data sections.

html_preamble = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HERA Auto Spectra Dashboard</title>
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap-theme.min.css">
  <!--[if lt IE 9]>
    <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
    <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
  <![endif]-->
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
"""

plotly_preamble = '''
<div class="container">
  <div class="row">
   <!-- Plotly chart will be drawn inside this div -->
   <div id="plotly-div" class="col-md-12" style="height: 80vh"></div>
   <script>


'''

plotly_postamble = '''
    layout = {
      xaxis: {title: 'Frequency [MHz]'},
      yaxis: {title: 'Power [dB]'},
      autosize: true,
      showlegend: true,
      legend: {
        x: 1,
        y: 1,
      },
      // title: 'Autocorrelation Powers',
      margin: {l: 40, b: 0, r: 40, t: 30},
      hovermode: 'closest'
    };
    Plotly.plot('plotly-div', {data:data, layout:layout}, {responsive: true});

    </script>
'''

html_postamble = '''
    </div>
  </div>
  </body>
</html>
'''

got_time = False
n_signals = 0
with open('spectra.html', 'w') as fh:
    fh.write(html_preamble)
    fh.write(plotly_preamble)
    # Get time of plot
    t_plot_jd = np.frombuffer(r['auto:timestamp'], dtype=np.float64)[0]
    t_plot_unix = Time(t_plot_jd, format='jd').unix
    print(t_plot_jd, t_plot_unix)
    got_time = True
    # grab data from redis and format it according to plotly's javascript api
    for i in range(n_ants):
        for pol in ['e', 'n']:
            # get the timestamp from redis for the first ant-pol
            if not got_time:
                t_plot_jd = float(r.hget('visdata://%d/%d/%s%s' % (i, i, pol, pol), 'time'))
                if t_plot_jd is not None:
                    t_plot_unix = Time(t_plot_jd, format='jd').unix
                    got_time = True
            linename = 'ant%d%s' % (i, pol)
            d = r.get('auto:%d%s' % (i, pol))
            if d is not None:
                n_signals += 1
                linenames += [linename]
                fh.write('%s = {\n' % (linename))
                fh.write('  x: [%s],\n' % frange_str)
                f = np.frombuffer(d, dtype=np.float32)[0:NCHANS].copy()
                f[f < 10 ** -2.5] = 10 ** -2.5
                f = 10 * np.log10(f)
                f_str = ', '.join('%f' % freq for freq in f)
                fh.write('  y: [%s],\n' % f_str)
                fh.write("  name: '%s',\n" % linename)
                fh.write("  type: 'scatter'\n")
                fh.write('};\n')
                fh.write('\n')
    fh.write('data = [%s];\n' % ', '.join(linenames))

    fh.write(plotly_postamble)
    fh.write('<p>Plots from %s UTC (JD: %f)</p>\n' % (time.ctime(t_plot_unix), t_plot_jd))
    fh.write('<p>Queried on %s UTC</p>\n' % time.ctime())
    # fh.write('<p>CMINFO source: %s</p>\n' % r['cminfo_source'])
    fh.write(html_postamble)

print('Got %d signals' % n_signals)
