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
    # this filter is used to see if there is more than one table
    env.filters['islist'] = is_list

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

        nodes = []
        hists = []
        bad_ants = []
        bad_node = []
        for ant_cnt, ant in enumerate(ants):
            ant_status = session.get_antenna_status(most_recent=True,
                                                    antenna_number=int(ant))
            mc_name = "HH{:d}".format(int(ant))
            node_info = hsession.get_part_at_station_from_type(mc_name,
                                                               'now', 'node')
            if len(ant_status) == 0:
                for pol in ['e', 'n']:
                    name = '{ant}:{pol}'.format(ant=ant, pol=pol)
                    print("No histogram data for ", name)
                    bad_ants.append(name)
            for stat in ant_status:
                name = "ant{ant}{pol}".format(ant=stat.antenna_number,
                                              pol=stat.antenna_feed_pol)

                # try to find the associated node
                # get the first key in the dict to index easier
                _key = list(node_info.keys())[0]
                if node_info[_key][stat.antenna_feed_pol] is not None:
                    _node_num = re.findall(r'N(\d+)', node_info[_key]['e'])[0]
                else:
                    print("No Node mapping for antennna: " + name)
                    _node_num = -1
                    bad_node.append('{ant}:{pol}'.format(ant=stat.antenna_number,
                                                         pol=stat.antenna_feed_pol
                                                         )
                                    )
                nodes.append(_node_num)

                timestamp = Time(stat.time, format='gps')
                if (stat.histogram_bin_centers is not None
                        and stat.histogram is not None):
                    bins = np.fromstring(stat.histogram_bin_centers.strip('[]'),
                                         sep=',')
                    hist = np.fromstring(stat.histogram.strip('[]'),
                                         sep=',')
                    if stat.eq_coeffs is not None:
                        eq_coeffs = np.fromstring(stat.eq_coeffs.strip('[]'),
                                                  sep=',')
                    else:
                        eq_coeffs = np.ones_like(hist)
                    hist /= np.median(eq_coeffs)

                    text = "observed at {iso}<br>(JD {jd})".format(iso=timestamp.iso,
                                                                   jd=timestamp.jd)
                    # spaces cause weird wrapping issues, replace them all with \t
                    text = text.replace(' ', '\t')
                    _data = {"x": bins.tolist(),
                             "y": hist.tolist(),
                             "name": name,
                             "node": _node_num,
                             "text": [text] * bins.size,
                             "hovertemplate": "(%{x:.1},\t%{y})<br>%{text}"
                             }
                    hists.append(_data)
                else:
                    name = '{ant}:{pol}'.format(ant=stat.antenna_number,
                                                pol=stat.antenna_feed_pol)
                    print("No histogram data for ", name)
                    bad_ants.append(name)
        table = {}
        table["title"] = "Ants with no Histogram"
        table["rows"] = []
        row = {}
        row['text'] = ',\t'.join(bad_ants)
        table['rows'].append(row)

        table_node = {}
        table_node["title"] = "Antennas with no Node mapping"
        row_node = {}
        row_node["text"] = '\t'.join(bad_node)
        rows_node = [row_node]
        table_node["rows"] = rows_node

        layout = {"xaxis": {"title": 'ADC value'},
                  "yaxis": {"title": 'Occurance',
                            "type": "linear"
                            },
                  "margin": {"l": 40, "b": 30, "r": 40, "t": 30},
                  "hovermode": "closest",
                  "autosize": True,
                  "showlegend": True
                  }

        # Make all the buttons for this plot
        nodes = np.unique(nodes)
        # if an antenna was not mapped, roll the -1 to the end
        # this makes making buttons easier so the unmapped show last
        if -1 in nodes:
            nodes = np.roll(nodes, -1)
        # create a mask to find all the matching nodes
        node_mask = [[True if s['node'] == node else False for s in hists]
                     for node in nodes]

        buttons_node = []
        _button_node = {"args": [{"visible": [True for s in hists]},
                                 {"title": '',
                                 "annotations": {}
                                  }
                                 ],
                        "label": "All\tAnts",
                        "method": "restyle"
                        }
        buttons_node.append(_button_node)

        for node_cnt, node in enumerate(nodes):
            if node != -1:
                label = "Node\t{}".format(node)
            else:
                label = "Unmapped\tAnts"

            _button_node = {"args": [{"visible": node_mask[node_cnt]},
                                     {"title": '',
                                      "annotations": {}
                                      }
                                     ],
                            "label": label,
                            "method": "restyle"
                            }
            buttons_node.append(_button_node)

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

        updatemenus = [{"buttons": buttons_node,
                        "showactive": True,
                        "active": 0,
                        "type": "dropdown",
                        "x": .55,
                        "y": 1.1,
                        },
                       {"buttons": buttons,
                        "showactive": True,
                        "type": "buttons",
                        "active": 0,
                        }
                       ]

        plotname = "plotly-adc-hist"

        html_template = env.get_template("ploty_with_multi_table.html")
        js_template = env.get_template("plotly_base.js")

        rendered_html = html_template.render(plotname=plotname,
                                             plotstyle="height: 85vh",
                                             gen_date=now.iso,
                                             js_name="adchist",
                                             gen_time_unix_ms=now.unix * 1000,
                                             scriptname=os.path.basename(__file__),
                                             hostname=computer_hostname,
                                             table=[table, table_node])

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
