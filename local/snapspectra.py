#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Antenna amplitudes."""

from __future__ import absolute_import, division, print_function

import os
import sys
import re
import numpy as np
import redis
from hera_mc import mc, cm_sysutils
from astropy.time import Time
import hera_corr_cm
from jinja2 import Environment, FileSystemLoader


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

    # The standard M&C argument parser
    parser = mc.get_mc_argument_parser()
    # we'll have to add some extra options too
    parser.add_argument('--redishost', dest='redishost', type=str,
                        default='redishost',
                        help=('The host name for redis to connect to, defualts to "redishost"'))
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
        corr_cm = hera_corr_cm.HeraCorrCM(redishost=args.redishost)
        hsession = cm_sysutils.Handling(session)
        stations = hsession.get_all_fully_connected_at_date(at_date='now')

        ants = []
        for station in stations:
            if station.antenna_number not in ants:
                ants = np.append(ants, station.antenna_number)
        ants = np.unique(ants).astype(int)

        hostname_lookup = {}
        snap_serial = {}
        ant_loc_num = {}

        # all_snap_statuses = session.get_snap_status(most_recent=True)
        all_snap_statuses = corr_cm.get_f_status()
        hostnames = list(set(all_snap_statuses.keys()))
        snapautos = {}

        ant_status_from_snaps = corr_cm.get_ant_status()
        table = {}
        table["title"] = "Antennas with No Data"
        rows = []
        text = ''
        bad_ants = []
        for ant_cnt, ant in enumerate(ants):
            mc_ant_status = session.get_antenna_status(antenna_number=int(ant),
                                                       most_recent=True)
            for stat in mc_ant_status:
                name = "{ant:d}:{pol}".format(ant=stat.antenna_number,
                                              pol=stat.antenna_feed_pol)
                try:
                    tmp_auto = ant_status_from_snaps[name]["autocorrelation"]
                    if tmp_auto == "None":
                        print("No Data for ", name)
                        text += name + "\t"
                        bad_ants.append(name)
                        continue
                    tmp_auto = np.ma.masked_invalid(10 * np.log10(np.real(tmp_auto)))
                    snapautos[name] = tmp_auto.filled(-100)

                except KeyError:
                    print("Ant-pol with no autocorrelation", name)
                    raise
                except TypeError:
                    print("Received TypeError when taking log.")
                    print("Type of item in dictionary: ", type(ant_status_from_snaps[name]["autocorrelation"]))
                    print("Value of item: ", tmp_auto)
                    raise
            # Try to get the snap info. Output is a dictionary with 'e' and 'n' keys
            # connect to M&C to find all the hooked up Snap hostnames and corresponding ant-pols
            mc_name = 'HH{:d}'.format(ant)
            snap_info = hsession.get_part_at_station_from_type(mc_name,
                                                               'now', 'snap')
            node_info = hsession.get_part_at_station_from_type(mc_name,
                                                               'now', 'node')

            for _key in snap_info.keys():
                # initialize a dict if they key does not exist already
                snap_serial.setdefault(int(ant), {})
                ant_loc_num.setdefault(int(ant), {})

                for pol_key in snap_info[_key].keys():
                    name = "{ant:d}:{pol}".format(ant=ant, pol=pol_key)
                    if snap_info[_key][pol_key] is not None:
                        snap_serial[ant][pol_key] = snap_info[_key][pol_key]
                        _node_num = re.findall(r'N(\d+)', node_info[_key][pol_key])[0]

                        snap_stats = session.get_snap_status(nodeID=int(_node_num),
                                                             most_recent=True)

                        for _stat in snap_stats:
                            if _stat.serial_number == snap_serial[ant][pol_key]:
                                ant_loc_num[ant][pol_key] = _stat.snap_loc_num

                                # if this hostname is not in the lookup table yet
                                # initialize an empty dict
                                grp1 = hostname_lookup.setdefault(_stat.hostname, {})
                                # if this loc num is not in lookup table initialize
                                # empty list
                                grp2 = grp1.setdefault(_stat.snap_loc_num, [])
                                grp2.append(name)
                    else:
                        print("No snap information for antennna: " + name)
        row = {}
        row["text"] = text
        rows.append(row)
        table["rows"] = rows
        data = []
        # create a mask to make things visible for only that hostname
        # the mask is different for each host, but each mask is the total
        # length of all data, 6 inputs per snap * number of snaps
        host_masks = np.full((len(hostnames), len(hostnames) * 6), False,
                             dtype='object')

        # Generate frequency axis
        freqs = np.linspace(0, 250e6, 1024)
        freqs /= 1e6
        mask_cnt = 0  #letting mask_cnt inca lets it match with indexing to append(_data)
        for host_cnt, host in enumerate(hostname_lookup.keys()):
            #mask_cnt = host_cnt * 6
            if host_cnt == 0:
                visible = True
            else:
                visible = False

            # host_title[host_cnt] = '{} Integration over {} seconds'.format(host, length)
            #loc_num is the snap#, there is always 1 (one) per host bc a host is a snap
            for loc_num in hostname_lookup[host].keys():
                for ant_cnt, ant_name in enumerate(hostname_lookup[host][loc_num]):
                    if ant_name in bad_ants:
                        continue
                    host_masks[host_cnt, mask_cnt] = True
                    mask_cnt += 1

                    name = 'ant{}'.format(ant_name.replace(":", ""))
                    _data = {"x": freqs.tolist(),
                             "y": snapautos[ant_name].tolist(),
                             "name": name,
                             "visible": visible,
                             "hovertemplate": "%{x:.1f}\tMHz<br>%{y:.3f}\t[dBm]"
                             }
                    data.append(_data)
        buttons = []
        for host_cnt, host in enumerate(hostnames):
            prog_time = all_snap_statuses[host]['last_programmed']
            timestamp = all_snap_statuses[host]['timestamp']
            temp = all_snap_statuses[host]['temp']
            uptime = all_snap_statuses[host]['uptime']
            pps = all_snap_statuses[host]['pps_count']

            label = ('{host}<br>programmed:\t{start}'
                     '<br>spectra\trecorded:\t{obs}<br>'
                     'temp:\t{temp:.0f}\tC\t'
                     'pps\tcount:\t{pps}\tCycles\t\t\t'
                     'uptime:\t{uptime}'
                     ''.format(host=host,
                               start=prog_time.isoformat(' '),
                               obs=timestamp.isoformat(' '),
                               temp=temp,
                               pps=pps,
                               uptime=uptime
                               )
                     )
            _button = {"args": [{"visible": host_masks[host_cnt].tolist()},
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
                        "type": "dropdown",
                        "x": .7,
                        "y": 1.1,
                        }
                       ]
        layout = {"xaxis": {"title": "Frequency [MHz]",
                            "showticklabels": True,
                            "tick0": 0,
                            "dtick": 10,
                            "range": [40, 250]
                            },
                  "yaxis": {"title": 'Power [dBm]',
                            "showticklabels": True,
                            "range": [-20, 20]
                            },
                  "hoverlabel": {"align": "left"},
                  "margin": {"l": 40, "b": 30,
                             "r": 40, "t": 30},
                  "autosize": True,
                  "showlegend": True,
                  "hovermode": 'closest',
                  }

        plotname = "plotly-snap"
        html_template = env.get_template("snapspectra.html")
        js_template = env.get_template("plotly_base.js")

        rendered_html = html_template.render(plotname=plotname,
                                             plotstyle="height: 85vh",
                                             gen_date=Time.now().iso,
                                             js_name='snapspectra',
                                             gen_time_unix_ms=Time.now().unix * 1000,
                                             scriptname=os.path.basename(__file__),
                                             hostname=computer_hostname,
                                             table=table
                                             )
        rendered_js = js_template.render(data=data,
                                         layout=layout,
                                         updatemenus=updatemenus,
                                         plotname=plotname)

        with open('snapspectra.html', 'w') as h_file:
            h_file.write(rendered_html)

        with open('snapspectra.js', 'w') as js_file:
            js_file.write(rendered_js)


if __name__ == '__main__':
    main()
