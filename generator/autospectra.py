#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""
Generate a simple dashboard page for the autocorelation spectra.

Adapted from https://github.com/HERA-Team/hera_corr_cm/blob/master/hera_today/redis_autocorr_to_html.py
"""

from __future__ import absolute_import, division, print_function

import os
import sys
import re
import redis
import numpy as np
import argparse
from astropy.time import Time
from jinja2 import Environment, FileSystemLoader


# Two redis instances run on this server.
# port 6379 is the hera-digi mirror
# port 6380 is the paper1 mirror
def main():
    # templates are stored relative to the script dir
    # stored one level up, find the parent directory
    # and split the parent directory away
    script_dir = os.path.dirname(os.path.realpath(__file__))
    split_dir = os.path.split(script_dir)
    template_dir = os.path.join(split_dir[0], 'templates')

    env = Environment(loader=FileSystemLoader(template_dir))

    if sys.version_info[0] < 3:
        # py2
        computer_hostname = os.uname()[1]
    else:
        # py3
        computer_hostname = os.uname().nodename

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

    # Generate frequency axis
    NCHANS = int(2048 // 4 * 3)
    NCHANS_F = 8192
    NCHAN_SUM = 4
    frange = np.linspace(0, 250e6, NCHANS_F + 1)[1536:1536 + (8192 // 4 * 3)]
    # average over channels
    frange = frange.reshape(NCHANS, NCHAN_SUM).sum(axis=1) / NCHAN_SUM
    frange_mhz = frange / 1e6

    got_time = False
    n_signals = 0

    t_plot_jd = np.frombuffer(r['auto:timestamp'], dtype=np.float64)[0]
    t_plot_iso = Time(t_plot_jd, format='jd').iso
    got_time = True
    # grab data from redis and format it according to plotly's javascript api
    autospectra = []
    for i in ants:
        for pol in ['e', 'n']:
            # get the timestamp from redis for the first ant-pol
            if not got_time:
                t_plot_jd = float(r.hget('visdata://%d/%d/%s%s' % (i, i, pol, pol), 'time'))
                if t_plot_jd is not None:
                    got_time = True
            linename = 'ant%d%s' % (i, pol)
            d = r.get('auto:%d%s' % (i, pol))
            if d is not None:
                n_signals += 1
                auto = np.frombuffer(d, dtype=np.float32)[0:NCHANS].copy()
                auto[auto < 10 ** -2.5] = 10 ** -2.5
                auto = 10 * np.log10(auto)
                _auto = {"x": frange_mhz.tolist(),
                         "y": auto.tolist(),
                         "name": linename,
                         "type": "scatter",
                         "hovertemplate": "%{x:.1f}\tMHz<br>%{y:.3f}\t[dB]"
                         }
                autospectra.append(_auto)
    layout = {"xaxis": {"title": "Frequency [MHz]"},
              "yaxis": {"title": "Power [dB]"},
              "autosize": True,
              "showlegend": True,
              "legend": {"x": 1,
                         "y": 1},
              "margin": {"l": 40,
                         "b": 30,
                         "r": 40,
                         "t": 30},
              "hovermode": "closest",
              }
    plotname = "plotly-autos"

    html_template = env.get_template("refresh_button.html")
    js_template = env.get_template("plotly_base.js")

    rendered_html = html_template.render(plotname=plotname,
                                         data_type="Auto correlations",
                                         plotstyle="height: 85vh",
                                         gen_date=Time.now().iso,
                                         data_date=t_plot_iso,
                                         data_jd_date=t_plot_jd,
                                         js_name="spectra",
                                         gen_time_unix_ms=Time.now().unix * 1000,
                                         scriptname=os.path.basename(__file__),
                                         hostname=computer_hostname)

    rendered_js = js_template.render(data=autospectra,
                                     layout=layout,
                                     plotname=plotname)

    print('Got %d signals' % n_signals)
    with open('spectra.html', 'w') as h_file:
        h_file.write(rendered_html)
    with open('spectra.js', 'w') as js_file:
        js_file.write(rendered_js)


if __name__ == '__main__':
    main()
