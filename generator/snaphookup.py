#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""
Generate a simple dashboard page for the HERA snaphookups.

Adapted from http://hera.today/snaphookup.html
"""

from __future__ import absolute_import, division, print_function

import os
import sys
import redis
import json
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

    env = Environment(loader=FileSystemLoader(template_dir),
                      trim_blocks=True)

    if sys.version_info[0] < 3:
        # py2
        computer_hostname = os.uname()[1]
    else:
        # py3
        computer_hostname = os.uname().nodename

    parser = argparse.ArgumentParser(
        description=('Create snap hookup tables for heranow dashboard')
    )
    parser.add_argument('--redishost', dest='redishost', type=str,
                        default='redishost',
                        help=('The host name for redis to connect to, defaults to "redishost"'))
    parser.add_argument('--port', dest='port', type=int, default=6379,
                        help='Redis port to connect.')
    args = parser.parse_args()

    redis_db = redis.Redis(args.redishost, port=args.port)
    corr_map = redis_db.hgetall('corr:map')

    update_time = Time(float(corr_map[b'update_time']), format='unix')
    all_tables = []

    # make a table of the antenna to snap mapping
    table_a_to_s = {}
    table_a_to_s["title"] = "Antenna -> SNAP mappings"
    rows_a = []
    ant_to_snap = json.loads(corr_map[b'ant_to_snap'])
    for ant in sorted(map(int, ant_to_snap)):
        ant = str(ant)
        pol = ant_to_snap[ant]
        for p in pol:
            vals = pol[p]
            row = {}
            host = vals['host']
            chan = vals['channel']
            if isinstance(host, bytes):
                host = host.decode('utf-8')
            if isinstance(chan, bytes):
                chan = chan.decode('utf-8')
            row["text"] = ("{ant}:{pol} -> {host}:{chan}"
                           .format(ant=ant, pol=p,
                                   host=host,
                                   chan=chan)
                           )
            rows_a.append(row)
    table_a_to_s["rows"] = rows_a
    all_tables.append(table_a_to_s)

    # make a table of the snap to antenna mapping
    table_s_to_a = {}
    table_s_to_a["title"] = "SNAP -> Antenna mappings"
    rows_s = []

    snap_to_ant = json.loads(corr_map[b'snap_to_ant'])
    for snap in sorted(snap_to_ant):
        ant = snap_to_ant[snap]
        for i in range(6):
            if ant[i] is None:
                ant[i] = "n/c"
            if isinstance(ant[i], bytes):
                ant[i] = ant[i].decode('utf-8')

        if isinstance(snap, bytes):
            snap = snap.decode('utf-8')
        row = {}
        row["text"] = ("{snap} -> {ants}"
                       .format(snap=snap,
                               ants=', '.join(ant))
                       )
        rows_s.append(row)

    table_s_to_a["rows"] = rows_s
    all_tables.append(table_s_to_a)

    # Make a table of the snap to antenna indices mapping
    table_ant_ind = {}
    table_ant_ind["title"] = "SNAP -> Antenna indices"

    snap_to_ant_i = redis_db.hgetall("corr:snap_ants")
    rows_ant_ind = []
    for snap in sorted(snap_to_ant_i):
        ant = snap_to_ant_i[snap]
        row = {}
        if isinstance(snap, bytes):
            snap = snap.decode('utf-8')
        if isinstance(ant, bytes):
            ant = ant.decode('utf-8')
        row["text"] = "{snap} -> {ant}".format(snap=snap, ant=str(ant))
        rows_ant_ind.append(row)

    table_ant_ind["rows"] = rows_ant_ind
    all_tables.append(table_ant_ind)

    # Make a table of the XENG channel indices
    table_xeng = {}
    table_xeng["title"] = "XENG -> Channel indices"
    rows_xeng = []

    xeng_to_chan_i = redis_db.hgetall("corr:xeng_chans")
    for xeng in sorted(map(int, xeng_to_chan_i)):
        xeng = bytes(str(xeng).encode())
        chans = xeng_to_chan_i[xeng]
        row = {}
        if isinstance(xeng, bytes):
            xeng = xeng.decode('utf-8')
        if isinstance(chans, bytes):
            chans = chans.decode('utf-8')
        row["text"] = ("{xeng} -> {chans}...".format(xeng=xeng,
                                                     chans=chans[0:5])
                       )
        rows_xeng.append(row)
    table_xeng["rows"] = rows_xeng
    all_tables.append(table_xeng)

    html_template = env.get_template("tables_with_footer.html")

    rendered_html = html_template.render(tables=all_tables,
                                         data_type="Hookup information",
                                         data_date=update_time.iso,
                                         data_date_jd=update_time.jd,
                                         data_date_unix_ms=update_time.unix * 1000,
                                         gen_date=Time.now().iso,
                                         gen_time_unix_ms=Time.now().unix * 1000,
                                         scriptname=os.path.basename(__file__),
                                         hostname=computer_hostname,
                                         colsize=6)

    with open('snaphookup.html', 'w') as h_file:
        h_file.write(rendered_html)


if __name__ == "__main__":
    main()
