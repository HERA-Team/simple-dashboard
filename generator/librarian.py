#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Librarian."""

from __future__ import absolute_import, division, print_function

import os
import sys
from astropy.time import Time, TimeDelta
from cgi import escape
from hera_mc import mc
from hera_mc.librarian import LibRAIDErrors, LibRAIDStatus, LibRemoteStatus, LibServerStatus, LibStatus
from jinja2 import Environment, FileSystemLoader


HOSTNAMES = [
    'qmaster',
    'pot1',
    'pot6.karoo.kat.ac.za',
    'pot7.rtp.pvt',
    'pot8.rtp.pvt',
]

UI_HOSTNAMES = {
    'pot6.karoo.kat.ac.za': 'pot6',
    'pot7.rtp.pvt': 'pot7',
    'pot7.still.pvt': 'pot7',
    'pot8.rtp.pvt': 'pot8',
    'pot8.still.pvt': 'pot8',
    'cask0.rtp.pvt': 'cask0',
    'cask1.rtp.pvt': 'cask1',
    'per510-1.rtp.pvt': 'cask0',
    'per510-2.rtp.pvt': 'cask1',
    'still1.rtp.pvt': 'still1',
    'still2.rtp.pvt': 'still2',
    'still3.rtp.pvt': 'still3',
    'still4.rtp.pvt': 'still4',
    'per715-1.rtp.pvt': 'still1',
    'per715-2.rtp.pvt': 'still2',
    'per715-3.rtp.pvt': 'still3',
    'per715-4.rtp.pvt': 'still4',
    'gpu1.rtp.pvt': 'gpu1',
    'gpu2.rtp.pvt': 'gpu2',
    'gpu3.rtp.pvt': 'gpu3',
    'gpu4.rtp.pvt': 'gpu4',
    'gpu5.rtp.pvt': 'gpu5',
    'gpu6.rtp.pvt': 'gpu6',
    'gpu7.rtp.pvt': 'gpu7',
    'gpu8.rtp.pvt': 'gpu8',
    'snb2.rtp.pvt': 'gpu3',
    'snb4.rtp.pvt': 'gpu6',
    'snb5.rtp.pvt': 'gpu8',
    'snb6.rtp.pvt': 'gpu7',
    'snb7.rtp.pvt': 'gpu4',
    'snb8.rtp.pvt': 'gpu2',
    'snb9.rtp.pvt': 'gpu5',
    'snb10.rtp.pvt': 'gpu1',
    'bigmem1.rtp.pvt': 'bigmem1',
    'bigmem2.rtp.pvt': 'bigmem2',
}

REMOTES = ['aoc-uploads', 'shredder']


def do_server_loads(session, cutoff):
    _data = []
    for host in HOSTNAMES:
        data = (session.query(LibServerStatus.mc_time,
                              LibServerStatus.cpu_load_pct)
                .filter(LibServerStatus.hostname == host)
                .filter(LibServerStatus.mc_time > cutoff.gps)
                .order_by(LibServerStatus.mc_time)
                .all())
        time_array = Time([t[0] for t in data], format='gps')
        if time_array:
            time_array = time_array.isot.tolist()
        else:
            time_array = []
        __data = [{"x": time_array,
                   "y": [t[1] for t in data],
                   "name": UI_HOSTNAMES.get(host, host),
                   "type": "scatter"
                   }
                  ]
        _data.append(__data)
    return _data


def do_disk_space(session, cutoff):
    _data = []
    data = (session.query(LibStatus.time, LibStatus.data_volume_gb)
            .filter(LibStatus.time > cutoff.gps)
            .order_by(LibStatus.time)
            .all())

    time_array = Time([t[0] for t in data], format='gps')
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []

    __data = {"x": time_array,
              "y": [t[1] for t in data],
              "name": "Data Volume".replace(' ', '\t'),
              "type": "scatter"
              }
    _data.append(__data)

    data = (session.query(LibStatus.time, LibStatus.free_space_gb)
            .filter(LibStatus.time > cutoff.gps)
            .order_by(LibStatus.time)
            .all())

    time_array = Time([t[0] for t in data], format='gps')
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []
    __data = {"x": time_array,
              "y": [t[1] for t in data],
              "name": "Free space".replace(' ', '\t'),
              "type": "scatter"
              }
    _data.append(__data)

    return _data


def do_upload_ages(session, cutoff):
    _data = []

    data = (session.query(LibStatus.time, LibStatus.upload_min_elapsed)
            .filter(LibStatus.time > cutoff.gps)
            .order_by(LibStatus.time)
            .all())

    time_array = Time([t[0] for t in data], format='gps')
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []
    __data = {"x": time_array,
              "y": [t[1] for t in data],
              "name": "Time since last upload".replace(' ', '\t'),
              "type": "scatter"
              }
    _data.append(__data)



def do_bandwidths(session, cutoff):
    _data = []

    for remote in REMOTES:
        data = (session.query(LibRemoteStatus.time, LibRemoteStatus.bandwidth_mbs)
                .filter(LibRemoteStatus.remote_name == remote)
                .filter(LibRemoteStatus.time > cutoff.gps)
                .order_by(LibRemoteStatus.time)
                .all())

        time_array = Time([t[0] for t in data], format='gps')
        if time_array:
            time_array = time_array.isot.tolist()
        else:
            time_array = []
        __data = {"x": time_array,
                  "y": [t[1] for t in data],
                  "name": "Time since last upload".replace(' ', '\t'),
                  "type": "scatter"
                  }
        _data.append(__data)

    return _data


def do_ping_times(session, cutoff):
    _data = []
    for remote in REMOTES:
        data = (session.query(LibRemoteStatus.time, LibRemoteStatus.ping_time)
                .filter(LibRemoteStatus.remote_name == remote)
                .filter(LibRemoteStatus.time > cutoff.gps)
                .order_by(LibRemoteStatus.time)
                .all())

        time_array = Time([t[0] for t in data], format='gps')
        if time_array:
            time_array = time_array.isot.tolist()
        else:
            time_array = []
        __data = {"x": time_array,
                  "y": [1000 * t[1] for t in data],
                  "name": "{name} ping time".format(name=remote).replace(' ', '\t'),
                  "type": "scatter"
                  }
        _data.append(__data)

    return _data


def do_num_files(session, cutoff):
    _data = []
    data = (session.query(LibStatus.time, LibStatus.num_files)
            .filter(LibStatus.time > cutoff.gps)
            .order_by(LibStatus.time)
            .all())
    time_array = Time([t[0] for t in data], format='gps')
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []
    __data = {"x": time_array,
              "y": [t[1] for t in data],
              "name": "Number of files".replace(' ', '\t'),
              "type": "scatter"
              }

    _data.append(__data)

    return _data


def do_raid_errors(session, cutoff):
    q = (session.query(LibRAIDErrors)
         .filter(LibRAIDErrors.time > cutoff.gps)
         .order_by(LibRAIDErrors.time.desc())
         .limit(10))
    table = {}
    table["title"] = "Recent RAID Errors".replace(' ', '\t')
    table["headers"] = ["Date", "Host", "Disk", "Message"]

    rows = []

    for rec in q:
        _row = {}
        _row.time = Time(rec.time, format='gps').isot
        _row.hostname = rec.hostname
        _row.disk = rec.disk
        _row.message = escape(rec.log)
        rows.append(_row)
    table["rows"] = rows
    return table


def do_raid_status(session, cutoff):
    q = (session.query(LibRAIDStatus)
         .filter(LibRAIDStatus.time > cutoff.gps)
         .filter(~LibRAIDStatus.hostname.startswith('per'))  # hack
         .order_by(LibRAIDStatus.time.desc())
         .limit(10))
    table = {}
    table["title"] = "Recent RAID Status Reports".replace(' ', '\t')
    table["headers"] = ["Date", "Host", "Num. Disks", "Message"]

    rows = []

    for rec in q:
        _row = {}
        _row.time = Time(rec.time, format='gps').isot
        _row.hostname = rec.hostname
        _row.disk = rec.num_disks
        _row.message = escape(rec.info)
        rows.append(_row)
    table["rows"] = rows

    return table


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
    args = parser.parse_args()

    try:
        db = mc.connect_to_mc_db(args)
    except RuntimeError as e:
        raise SystemExit(str(e))

    colsize = 6
    TIME_WINDOW = 14  # days
    now = Time.now()
    cutoff = now - TimeDelta(TIME_WINDOW, format='jd')
    time_axis_range = [cutoff.isot, now.isot]
    plotnames = [["server-loads", "upload-ages"],
                 ["disk-space", "bandwidths"],
                 ["num-files", "ping-times"]]

    layout = {"xaxis": {"range": time_axis_range},
              "yaxis": {"title": 'Load % per CPU'},
              "height": 200,
              "margin": {"t": 2, "r": 10, "b": 2, "l": 40},
              "legend": {"orientation": 'h', "x": 0.15, "y": -0.15},
              "showlegend": True,
              "hovermode": 'closest'
              }

    html_template = env.get_template("librarian_table.html")
    js_template = env.get_template("plotly_base.js")

    with db.sessionmaker() as session:

        data = do_server_loads(session, cutoff)

        rendered_js = js_template.render(plotname="server-loads",
                                         data=data,
                                         layout=layout)
        with open('librarian.js', 'w') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        data = do_upload_ages(session, cutoff)
        layout["yaxis"]["title"] = "Minutes"
        layout["yaxis"]["zeroline"] = False
        rendered_js = js_template.render(plotname="upload-ages",
                                         data=data,
                                         layout=layout)
        with open('librarian.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        data = do_disk_space(session, cutoff)
        layout["yaxis"]["title"] = "Gigabytes"
        layout["yaxis"]["zeroline"] = True

        rendered_js = js_template.render(plotname="disk-space",
                                         data=data,
                                         layout=layout)
        with open('librarian.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        data = do_bandwidths(session, cutoff)
        layout["yaxis"]["title"] = 'MB/s'
        rendered_js = js_template.render(plotname="bandwidths",
                                         data=data,
                                         layout=layout)
        with open('librarian.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        data = do_num_files(session, cutoff)
        layout["yaxis"]["title"] = 'Number'
        layout["yaxis"]["zeroline"] = False
        rendered_js = js_template.render(plotname="num-files",
                                         data=data,
                                         layout=layout)
        with open('librarian.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        data = do_ping_times(session, cutoff)
        layout["yaxis"]["title"] = 'ms'
        layout["yaxis"]["rangemode"] = 'tozero'
        layout["yaxis"]["zeroline"] = True
        rendered_js = js_template.render(plotname="ping-times",
                                         data=data,
                                         layout=layout)
        with open('librarian.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        tables = []
        tables.append(do_raid_errors(session, cutoff))
        tables.append(do_raid_status(session, cutoff))

        rendered_html = html_template.render(plotname=plotnames,
                                             plotstyle="height: 220",
                                             colsize=colsize,
                                             gen_date=now.iso,
                                             gen_time_unix_ms=now.unix * 1000,
                                             js_name='librarian',
                                             hostname=computer_hostname,
                                             scriptname=os.path.basename(__file__),
                                             tables=tables
                                             )

        with open('librarian.html', 'w') as h_file:
            h_file.write(rendered_html)


if __name__ == '__main__':
    main()
