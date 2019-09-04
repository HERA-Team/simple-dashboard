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
import time
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
    script_dir = os.path.dirname(os.path.realpath(__file__))
    template_dir = os.path.join(script_dir, 'templates')

    env = Environment(loader=FileSystemLoader(template_dir))

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
    frange_mhz = frange / 1e6
    # frange_str = ', '.join('%f' % freq for freq in frange)
    # linenames = []

    got_time = False
    n_signals = 0
    # with open('spectra.html', 'w') as fh:
        # fh.write(html_preamble)
        # fh.write(plotly_preamble)
        # Get time of plot
    t_plot_jd = np.frombuffer(r['auto:timestamp'], dtype=np.float64)[0]
    t_plot_unix = Time(t_plot_jd, format='jd').unix
    t_plot_iso = Time(t_plot_jd, format='jd').iso
    # print(t_plot_jd, t_plot_unix)
    got_time = True
    # grab data from redis and format it according to plotly's javascript api
    autospectra = []
    for i in ants:
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
                # linenames += [linename]
                auto = np.frombuffer(d, dtype=np.float32)[0:NCHANS].copy()
                auto[auto < 10 ** -2.5] = 10 ** -2.5
                auto = 10 * np.log10(auto)
                _auto = {"x": frange.tolist(),
                         "y": auto.tolist(),
                         "text": frange_mhz.tolist(),
                         "name": linename,
                         "type": "scatter",
                         "hovertemplate": "%{x:.1f}\tMhz<br>%{y:.3f}\t[dB]"
                         }
                autospectra.append(_auto)
    layout = {"xaxis": {"title": "Frequency [MHz]"},
              "yaxis": {"title": "Power [dB]"},
              "autosize": True,
              "showlegend": True,
              "legend": {"x": 1,
                         "y": 1},
              "margin": {"l": 40,
                         "b": 0,
                         "r": 40,
                         "t": 30},
              "hovermode": "closest",
              }
    plotname = "plotly-autos"

    js_template = env.get_template("plotly_base.js")
    html_template = env.get_template("refresh_button.html")

    rendered_html = html_template.render(plotname=plotname,
                                         data_type="Auto correlations",
                                         plotstyle="height: 85vh",
                                         gen_date=Time.now().iso,
                                         iso_date=t_plot_iso,
                                         jd_date=t_plot_jd,
                                         js_name="spectra")

    rendered_js = js_template.render(gen_time_unix_ms=Time.now().unix * 1000,
                                     data=autospectra,
                                     layout=layout,
                                     plotname=plotname)

    print('Got %d signals' % n_signals)
    with open('spectra.html', 'w') as h_file:
        h_file.write(rendered_html)
    with open('spectra.js', 'w') as js_file:
        js_file.write(rendered_js)


if __name__ == '__main__':
    main()
