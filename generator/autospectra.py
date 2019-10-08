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
import json
import numpy as np
import argparse
from astropy.time import Time
from jinja2 import Environment, FileSystemLoader


def is_list(value):
    return isinstance(value, list)


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

    env = Environment(loader=FileSystemLoader(template_dir),
                      trim_blocks=True)
    env.filters['islist'] = is_list

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
    corr_map = r.hgetall(b'corr:map')
    ant_to_snap = json.loads(corr_map[b'ant_to_snap'])
    node_map = {}
    nodes = []
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

    table_ants = {}
    table_ants["title"] = "Antennas with no mapping"
    rows = []
    bad_ants = []
    for i in ants:
        for pol in ['e', 'n']:
            # get the timestamp from redis for the first ant-pol
            if not got_time:
                t_plot_jd = float(r.hget('visdata://%d/%d/%s%s' % (i, i, pol, pol), 'time'))
                if t_plot_jd is not None:
                    got_time = True
            linename = 'ant%d%s' % (i, pol)

            match = re.search(r'heraNode(?P<node>\d+)Snap',
                              ant_to_snap[str(i)][pol]['host'])
            if match is not None:
                _node = int(match.group('node'))
                nodes.append(_node)
                node_map[linename] = _node
            else:
                print("No Node mapping for antennna: " + linename)
                bad_ants.append(linename)
                node_map[linename] = -1
                nodes.append(-1)

            d = r.get('auto:%d%s' % (i, pol))
            if d is not None:

                n_signals += 1
                auto = np.frombuffer(d, dtype=np.float32)[0:NCHANS].copy()

                eq_coeffs = r.hget(b'eq:ant:{ant}:{pol}'.format(ant=i, pol=pol),
                                   'values')
                if eq_coeffs is not None:
                    eq_coeffs = np.fromstring(eq_coeffs.decode('utf-8').strip('[]'),
                                              sep=',')
                    if eq_coeffs.size == 0:
                        eq_coeffs = np.ones_like(auto)
                else:
                    eq_coeffs = np.ones_like(auto)

                # divide out the equalization coefficients
                # eq_coeffs are stored as a length 1024 array but only a
                # single number is used. Taking the median to not deal with
                # a size mismatch
                eq_coeffs = np.median(eq_coeffs)
                auto /= eq_coeffs

                auto[auto < 10 ** -2.5] = 10 ** -2.5
                auto = 10 * np.log10(auto)
                _auto = {"x": frange_mhz.tolist(),
                         "y": auto.tolist(),
                         "name": linename,
                         "node": node_map[linename],
                         "type": "scatter",
                         "hovertemplate": "%{x:.1f}\tMHz<br>%{y:.3f}\t[dB]"
                         }
                autospectra.append(_auto)

    row = {}
    row["text"] = '\t'.join(bad_ants)
    rows.append(row)
    table_ants["rows"] = rows

    nodes = np.unique(nodes)
    # if an antenna was not mapped, roll the -1 to the end
    # this makes making buttons easier so the unmapped show last
    if -1 in nodes:
        nodes = np.roll(nodes, -1)
    # create a mask to find all the matching nodes
    node_mask = [[True if s['node'] == node else False for s in autospectra]
                 for node in nodes]
    buttons = []
    _button = {"args": [{"visible": [True for s in autospectra]},
                        {"title": '',
                         "annotations": {}
                         }
                        ],
               "label": "All\tAnts",
               "method": "restyle"
               }
    buttons.append(_button)
    for node_cnt, node in enumerate(nodes):
        if node != -1:
            label = "Node\t{}".format(node)
        else:
            label = "Unmapped\tAnts"

        _button = {"args": [{"visible": node_mask[node_cnt]},
                            {"title": '',
                             "annotations": {}
                             }
                            ],
                   "label": label,
                   "method": "restyle"
                   }
        buttons.append(_button)

    updatemenus = [{"buttons": buttons,
                    "showactive": True,
                    "active": 0,
                    "type": "dropdown",
                    "x": .55,
                    "y": 1.1,
                    }
                   ]

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

    html_template = env.get_template("refresh_with_table.html")
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
                                         hostname=computer_hostname,
                                         table=table_ants)

    rendered_js = js_template.render(data=autospectra,
                                     layout=layout,
                                     updatemenus=updatemenus,
                                     plotname=plotname)

    print('Got %d signals' % n_signals)
    with open('spectra.html', 'w') as h_file:
        h_file.write(rendered_html)
    with open('spectra.js', 'w') as js_file:
        js_file.write(rendered_js)


if __name__ == '__main__':
    main()
