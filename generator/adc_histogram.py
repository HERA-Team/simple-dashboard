#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the adc histograms."""

from __future__ import absolute_import, division, print_function

import os
import sys
import re
import redis
import numpy as np
from hera_mc import mc, cm_sysutils
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

    env = Environment(loader=FileSystemLoader(template_dir),
                      trim_blocks=True)

    if sys.version_info[0] < 3:
        # py2
        computer_hostname = os.uname()[1]
    else:
        # py3
        computer_hostname = os.uname().nodename

    parser = mc.get_mc_argument_parser()
    parser.add_argument('--redishost', dest='redishost', type=str,
                        default='redishost',
                        help=('The host name for redis to connect to, defaults to "redishost"'))
    parser.add_argument('--port', dest='port', type=int, default=6379,
                        help='Redis port to connect.')
    args = parser.parse_args()

    try:
        db = mc.connect_to_mc_db(args)
    except RuntimeError as e:
        raise SystemExit(str(e))

    try:
        redis_db = redis.Redis(args.redishost, port=args.port)
        redis_db.keys()
    except Exception as err:
        raise SystemExit(str(err))

    with db.sessionmaker() as session:
        now = Time.now()

        hsession = cm_sysutils.Handling(session)
        stations = hsession.get_all_fully_connected_at_date(at_date='now')

        ants = []
        for station in stations:
            if station.antenna_number not in ants:
                ants = np.append(ants, station.antenna_number)
        ants = np.unique(ants).astype(int)

        hists = []
        bad_ants = []
        for ant_cnt, ant in enumerate(ants):
            ant_status = session.get_antenna_status(most_recent=True,
                                                    antenna_number=int(ant))
            for stat in ant_status:
                name = "ant{ant}{pol}".format(ant=stat.antenna_number,
                                              pol=stat.antenna_feed_pol)
                timestamp = Time(stat.time, format='gps')
                if (stat.histogram_bin_centers is not None
                        and stat.histogram is not None):
                    bins = np.fromstring(stat.histogram_bin_centers.strip('[]'),
                                         sep=',')
                    hist = np.fromstring(stat.histogram.strip('[]'),
                                         sep=',')
                    eq_coeffs = np.fromstring(stat.eq_coeffs.strip('[]'),
                                              sep=',')
                    hist /= np.medina(eq_coeffs)

                    text = "observed at {iso}<br>(JD {jd})".format(iso=timestamp.iso,
                                                                   jd=timestamp.jd)
                    # spaces cause weird wrapping issues, replace them all with \t
                    text = text.replace(' ', '\t')
                    _data = {"x": bins.tolist(),
                             "y": hist.tolist(),
                             "name": name,
                             "text": [text] * bins.size,
                             "hovertemplate": "(%{x:.1},\t%{y})<br>%{text}"
                             }
                    hists.append(_data)
                else:
                    bad_ants.append('{ant}:{pol}'.format(ant=stat.antenna_number,
                                                         pol=stat.antenna_feed_pol)
                                    )
        table = {}
        table["title"] = "Ants with no Histogram"
        table["rows"] = []
        row = {}
        row['text'] = ',\t'.join(bad_ants)
        table['rows'].append(row)

        layout = {"xaxis": {"title": 'ADC value'},
                  "yaxis": {"title": 'Occurance',
                            "type": "linear"
                            },
                  "margin": {"l": 40, "b": 30, "r": 40, "t": 30},
                  "hovermode": "closest",
                  "autosize": True,
                  "showlegend": True
                  }
        buttons = []

        log_buttons = {"args": [{},
                                {"yaxis": {"type": "log"}}],
                       "label": "Log",
                       "method": "update",
                       }
        lin_buttons = {"args": [{},
                                {"yaxis": {"type": "linear"}}],
                       "label": "Linear",
                       "method": "update"
                       }

        buttons.append(lin_buttons)
        buttons.append(log_buttons)

        updatemenus = [{"buttons": buttons,
                        "showactive": True,
                        "type": "buttons",
                        "active": 0,
                        }
                       ]

        plotname = "plotly-adc-hist"

        html_template = env.get_template("ploty_with_table.html")
        js_template = env.get_template("plotly_base.js")

        rendered_html = html_template.render(plotname=plotname,
                                             plotstyle="height: 85vh",
                                             gen_date=now.iso,
                                             js_name="adchist",
                                             gen_time_unix_ms=now.unix * 1000,
                                             scriptname=os.path.basename(__file__),
                                             hostname=computer_hostname,
                                             table=table)

        rendered_js = js_template.render(data=hists,
                                         layout=layout,
                                         plotname=plotname,
                                         updatemenus=updatemenus)

        with open('adchist.html', 'w') as h_file:
            h_file.write(rendered_html)
        with open('adchist.js', 'w') as js_file:
            js_file.write(rendered_js)


if __name__ == '__main__':
    main()
