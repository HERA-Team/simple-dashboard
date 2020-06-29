#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Antenna amplitudes."""

from __future__ import absolute_import, division, print_function

import os
import re
import sys
import json
import redis
import numpy as np
from hera_mc import mc, cm_sysutils
from astropy.time import Time
import hera_corr_cm
from jinja2 import Environment, FileSystemLoader


def is_list(value):
    return isinstance(value, list)

def listify(input):
    if isinstance(input, (list, tuple, np.ndarray)):
        return input
    else:
        return [input]

def index_in(indexable, i):
    return indexable[i]

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
    env.filters["islist"] = is_list
    env.filters["index"] = index_in
    env.filters["listify"] = listify

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
        stations = hsession.get_connected_stations(at_date='now')

        antpos = np.genfromtxt(os.path.join(mc.data_path, "HERA_350.txt"),
                               usecols=(0, 1, 2, 3),
                               dtype={'names': ('ANTNAME', 'EAST', 'NORTH', 'UP'),
                                      'formats': ('<U5', '<f8', '<f8', '<f8')},
                               encoding=None)
        antnames = antpos['ANTNAME']
        inds = [int(j[2:]) for j in antnames]
        inds = np.argsort(inds)

        antnames = np.take(antnames, inds)

        ants = []
        for station in stations:
            if station.antenna_number not in ants:
                ants = np.append(ants, station.antenna_number)
        ants = np.unique(ants).astype(int)

        hostname_lookup = {}

        # all_snap_statuses = session.get_snap_status(most_recent=True)
        all_snap_statuses = corr_cm.get_f_status()
        snapautos = {}

        ant_status_from_snaps = corr_cm.get_ant_status()
        all_snaprf_stats = corr_cm.get_snaprf_status()

        table_snap = {}
        table_snap["title"] = "Snap hookups with No Data"
        rows = []
        bad_snaps = []

        for snap_chan in all_snaprf_stats:
            host, loc_num = snap_chan.split(":")
            loc_num = int(loc_num)

            # initialize this key if not already in the dict
            auto_group = snapautos.setdefault(host, {})

            try:
                tmp_auto = np.array(all_snaprf_stats[snap_chan]["autocorrelation"])
                if np.all(tmp_auto == "None") and tmp_auto is not None:
                    print("No Data for {} port {}".format(host, loc_num))
                    bad_snaps.append(snap_chan)
                    tmp_auto = np.full(1024, np.nan)

                eq_coeffs = np.array(all_snaprf_stats[snap_chan]["eq_coeffs"])
                if np.all(eq_coeffs == "None") and eq_coeffs is not None:
                    eq_coeffs = np.full_like(tmp_auto, 1.0)

                tmp_auto /= eq_coeffs**2
                tmp_auto = np.ma.masked_invalid(10 * np.log10(np.real(tmp_auto)))
                auto_group[loc_num] = tmp_auto.filled(-50)

            except KeyError:
                print("Snap connection with no autocorrelation", snap_chan)
                raise
            except TypeError:
                print("Received TypeError when taking log.")
                print("Type of item in dictionary: ", type(all_snaprf_stats[snap_chan]["autocorrelation"]))
                print("Value of item: ", tmp_auto)
                raise

            hostname_lookup.setdefault(host, {})
            hostname_lookup[host].setdefault(loc_num, {})
            hostname_lookup[host][loc_num]['MC'] = 'NC'
        row = {}
        row["text"] = '\t'.join(bad_snaps)
        rows.append(row)
        table_snap["rows"] = rows

        table_ants = {}
        table_ants["title"] = "Antennas with no mapping"
        rows = []

        bad_ants = []
        bad_hosts = []

        for ant_cnt, ant in enumerate(ants):

            # get the status for both polarizations for this antenna
            ant_status = {key: ant_status_from_snaps[key]
                          for key in ant_status_from_snaps
                          if ant == int(key.split(':')[0])}

            # check if the antenna status from M&C has the host and
            # channel number, if it does not we have to do some gymnastics
            for antkey in ant_status:
                pol_key = antkey.split(":")[1]
                stat = ant_status[antkey]
                name = "{ant:d}:{pol}".format(ant=ant,
                                              pol=pol_key)
                # check that key is in the dictionary, is not None or the string "None"
                if ('f_host' in stat and 'host_ant_id' in stat
                        and stat['f_host'] is not None
                        and stat['host_ant_id'] is not None
                        and stat['f_host'] != "None"
                        and stat['host_ant_id'] != "None"):
                    hostname = stat['f_host']
                    loc_num = stat['host_ant_id']
                    hostname_lookup[hostname][loc_num]['MC'] = name
                else:
                    # Try to get the snap info from M&C. Output is a dictionary with 'e' and 'n' keys
                    # connect to M&C to find all the hooked up Snap hostnames and corresponding ant-pols
                    mc_name = antnames[ant]
                    # these two may not be used, but it is easier to grab them now
                    snap_info = hsession.get_part_at_station_from_type(mc_name,
                                                                       'now', 'snap',
                                                                       include_ports=True)
                    for _key in snap_info.keys():
                        # initialize a dict if they key does not exist already
                        pol_key = pol_key.upper() + "<ground"
                        if snap_info[_key][pol_key] is not None:
                            serial_with_ports = snap_info[_key][pol_key]
                            snap_serial = serial_with_ports.split('>')[1].split('<')[0]
                            ant_channel = int(serial_with_ports.split('>')[0][1:]) // 2

                            hostname = session.get_snap_hostname_from_serial(snap_serial)

                            if hostname is None:
                                node_info = hsession.get_part_at_station_from_type(mc_name,
                                                                                   'now', 'node')
                                _node_num = re.findall(r'N(\d+)', node_info[_key][pol_key])[0]

                                snap_stats = session.get_snap_status(nodeID=int(_node_num),
                                                                     most_recent=True)

                                for _stat in snap_stats:
                                    if _stat.serial_number == snap_serial:
                                        hostname = _stat.hostname

                            # if hostname is still None then we don't have a known hookup
                            if hostname is None:
                                print("No MC snap information for antennna: " + name)
                                bad_ants.append(name)
                            else:
                                if hostname not in hostname_lookup.keys():
                                    err = "host from M&C not found in corr_cm 'status:snaprf' : {}".format(hostname)
                                    err += '\nThis host may not have data populated yet or is offline.'
                                    err += '\nAll anteanns on this host will be full of 0.'
                                    print(err)
                                    bad_hosts.append(hostname)
                                grp1 = hostname_lookup.setdefault(hostname, {})
                                # if this loc num is not in lookup table initialize
                                # empty list
                                if ant_channel not in grp1.keys():
                                    if hostname not in bad_hosts:
                                        print("loc_num from M&C not found in hera_corr_cm `status:snaprf` (host, location number): {}".format([hostname, ant_channel]))
                                        print("filling with bad array full of 0.")
                                    else:
                                        _name = "{host}:{loc}".format(host=hostname, loc=ant_channel)
                                        if _name not in table_snap["rows"][0]["text"]:
                                            table_snap["rows"][0]["text"] += _name + '\t'
                                    snap_grp1 = snapautos.setdefault(hostname, {})
                                    snap_grp1[ant_channel] = np.full(1024, 0)
                                grp2 = grp1.setdefault(ant_channel, {})
                                grp2['MC'] = name

                        else:
                            print("No MC snap information for antennna: " + name)
                            bad_ants.append(name)
        row = {}
        row["text"] = '\t'.join(bad_ants)
        rows.append(row)
        table_ants["rows"] = rows

        host_masks = []
        for h1 in sorted(hostname_lookup.keys()):
            _mask = []
            for h2 in sorted(hostname_lookup.keys()):
                _mask.extend([True if h2 == h1 else False
                              for loc_num in hostname_lookup[h2]])
            host_masks.append(_mask)

        # Generate frequency axis
        freqs = np.linspace(0, 250e6, 1024)
        freqs /= 1e6

        data = []
        for host_cnt, host in enumerate(sorted(hostname_lookup.keys())):
            if host_cnt == 0:
                visible = True
            else:
                visible = False

            for loc_num in sorted(hostname_lookup[host].keys()):
                mc_name = hostname_lookup[host][loc_num]['MC']

                name = '{loc}:{mcname}'.format(loc=loc_num,
                                               mcname=mc_name.replace(":", ""))
                try:
                    _data = {"x": freqs.tolist(),
                             "y": snapautos[host][loc_num].tolist(),
                             "name": name,
                             "visible": visible,
                             "hovertemplate": "%{x:.1f}\tMHz<br>%{y:.3f}\t[dB]"
                             }
                except KeyError:
                    print("Given host, location pair: ({0}, {1})".format(host, loc_num))
                    print("All possible keys for host {0}: {1}".format(host, list(snapautos[host].keys())))
                    raise
                data.append(_data)
        buttons = []
        for host_cnt, host in enumerate(sorted(hostname_lookup.keys())):
            prog_time = all_snap_statuses[host]['last_programmed']
            timestamp = all_snap_statuses[host]['timestamp']
            temp = all_snap_statuses[host]['temp']
            uptime = all_snap_statuses[host]['uptime']
            pps = all_snap_statuses[host]['pps_count']
            if host in bad_hosts:
                label = ('{host}<br>programmed:\t{start}'
                         '<br>spectra\trecorded:\tNO DATA OBSERVED<br>'
                         'temp:\t{temp:.0f}\tC\t'
                         'pps\tcount:\t{pps}\tCycles\t\t\t'
                         'uptime:\t{uptime}'
                         ''.format(host=host,
                                   start=prog_time.isoformat(' '),
                                   temp=temp,
                                   pps=pps,
                                   uptime=uptime
                                   )
                         )
            else:
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
            _button = {"args": [{"visible": host_masks[host_cnt]},
                                {"title": '',
                                 # "annotations": {}
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
                            },
                  "yaxis": {"title": 'Power [dB]',
                            "showticklabels": True,
                            },
                  "hoverlabel": {"align": "left"},
                  "margin": {"l": 40, "b": 30,
                             "r": 40, "t": 30},
                  "autosize": True,
                  "showlegend": True,
                  "hovermode": 'closest',
                  "annotations": [{"x": 1.03,
                                   "y": 1.03,
                                   "align": "right",
                                   "valign": "top",
                                   "text": 'ADC Port # : Antpol',
                                   "showarrow": False,
                                   "xref": "paper",
                                   "yref": "paper",
                                   "xanchor": "center",
                                   "yanchor": "top"
                                   }
                                  ]
                  }

        caption = {}
        caption["title"] = "Snap Spectra Help"
        caption["text"] = ("Autocorrelations (in dB) calculated by each Snap "
                           "with equalization coefficients divided out. "
                           "Calculation is independent of the corrlator. "
                           "<br><br>"
                           "Data is organized by the ADC Port number from "
                           "each Snap. "
                           "A mapping dictionary is used to look up the "
                           "associated ant-pol for each ADC Port. "
                           "Some ADC Ports may not have a known ant-pol "
                           "and are labeled as N/C."
                           "<br>Some antennas known to M&C may not have a known ADC port"
                           " mapping and are labeled below the plot."
                           "<br><br>Some Snap ports my not have data and are "
                           "labeled in a table below the plot."
                           "<br><br>The node selection button contains a lot "
                           "of information described here."
                           "<br><h4>Button Label Information</h4>"
                           "<ul>"
                           "<li>Snap hostname</li>"
                           "<li>Last time the Snap was programmed</li>"
                           "<li>Last time data was recorded from this Snap</li>"
                           "<li>Last known temperature in C | PPS count | Uptime</li>"
                           "</ul>"
                           )

        plotname = "plotly-snap"
        html_template = env.get_template("refresh_with_table.html")
        js_template = env.get_template("plotly_base.js")
        basename = "snapspectra"
        rendered_html = html_template.render(plotname=plotname,
                                             plotstyle="height: 100%",
                                             gen_date=Time.now().iso,
                                             js_name=basename,
                                             gen_time_unix_ms=Time.now().unix * 1000,
                                             scriptname=os.path.basename(__file__),
                                             hostname=computer_hostname,
                                             table=[table_snap, table_ants],
                                             caption=caption
                                             )

        rendered_js = js_template.render(json_name=basename,
                                         layout=layout,
                                         updatemenus=updatemenus,
                                         plotname=plotname)

        with open("{}.json".format(basename), "w") as json_file:
            json.dump(data, json_file)

        with open('snapspectra.html', 'w') as h_file:
            h_file.write(rendered_html)

        with open('snapspectra.js', 'w') as js_file:
            js_file.write(rendered_js)


if __name__ == '__main__':
    main()
