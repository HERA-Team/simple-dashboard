#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the hookup notes."""

from __future__ import absolute_import, division, print_function

import os
import sys
import numpy as np
import re
import redis
from hera_mc import mc, cm_sysutils, cm_utils, cm_sysdef, cm_hookup
from astropy.time import Time
from jinja2 import Environment, FileSystemLoader


def main():
    # templates are stored relative to the script dir
    # stored one level up, find the parent directory
    # and split the parent directory away
    script_dir = os.path.dirname(os.path.realpath(__file__))
    split_dir = os.path.split(script_dir)
    template_dir = os.path.join(split_dir[0], "templates")

    env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)
    if sys.version_info[0] < 3:
        # py2
        computer_hostname = os.uname()[1]
    else:
        # py3
        computer_hostname = os.uname().nodename

    # The standard M&C argument parser
    parser = mc.get_mc_argument_parser()
    # we'll have to add some extra options too
    parser.add_argument(
        "--redishost",
        dest="redishost",
        type=str,
        default="redishost",
        help=('The host name for redis to connect to, defualts to "redishost"'),
    )
    parser.add_argument(
        "--port", dest="port", type=int, default=6379, help="Redis port to connect."
    )
    parser.add_argument(
        "-p",
        "--hpn",
        help="Part number, csv-list or default. (default)",
        default="default",
    )
    parser.add_argument(
        "--all",
        help="Toggle to show 'all' hookups as opposed to 'full'",
        action="store_true",
    )
    parser.add_argument(
        "--hookup-cols",
        dest="hookup_cols",
        default="all",
        help=(
            "Specify a subset of parts to show in hookup, "
            "comma-delimited no-space list. (all])"
        ),
    )

    args = parser.parse_args()

    args.hookup_cols = cm_utils.listify(args.hookup_cols)
    if args.hpn == "default":
        args.hpn = cm_sysdef.hera_zone_prefixes
    else:
        args.hpn = cm_utils.listify(args.hpn)

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
        # without item this will be an array which will break database queries
        latest = Time(
            np.frombuffer(redis_db.get("auto:timestamp"), dtype=np.float64).item(),
            format="jd",
        )

        now = Time.now()
        online_ants = []
        keys = [
            k.decode()
            for k in redis_db.keys()
            if k.startswith(b"auto") and not k.endswith(b"timestamp")
        ]

        for key in keys:
            match = re.search(r"auto:(?P<ant>\d+)(?P<pol>e|n)", key)
            if match is not None:
                ant = int(match.group("ant"))
                online_ants.append(ant)

        hsession = cm_sysutils.Handling(session)
        hookup = cm_hookup.Hookup(session)

        hookup_dict = hookup.get_hookup(
            hpn=args.hpn,
            pol="all",
            at_date=now,
            exact_match=False,
            use_cache=False,
            hookup_type=args.hookup_type
        )
        hu_notes = hookup.get_notes(hookup_dict=hookup_dict, state="all")

        online_ants = np.unique(online_ants)

        antpos = np.genfromtxt(
            os.path.join(mc.data_path, "HERA_350.txt"),
            usecols=(0, 1, 2, 3),
            dtype={
                "names": ("ANTNAME", "EAST", "NORTH", "UP"),
                "formats": ("<U5", "<f8", "<f8", "<f8"),
            },
            encoding=None,
        )
        antnames = antpos["ANTNAME"]
        inds = [int(j[2:]) for j in antnames]
        inds = np.argsort(inds)

        antnames = np.take(antnames, inds)

        antpos = np.array([antpos["EAST"], antpos["NORTH"], antpos["UP"]])
        array_center = np.mean(antpos, axis=1, keepdims=True)
        antpos -= array_center
        antpos = np.take(antpos, inds, axis=1)

        stations = hsession.get_all_fully_connected_at_date(at_date="now")

        for station in stations:
            if station.antenna_number not in online_ants:
                online_ants = np.append(online_ants, station.antenna_number)
        online_ants = np.unique(online_ants)

        stations = []
        for station_type in hsession.geo.parse_station_types_to_check("default"):
            for stn in hsession.geo.station_types[station_type]["Stations"]:
                stations.append(stn)

        # stations is a list of HH??? numbers we just want the ints
        stations = list(map(int, [j[2:] for j in stations]))
        built_but_not_on = np.setdiff1d(stations, online_ants)
        # Get node and PAM info

        #  get all the data

        xs = np.ma.masked_array(antpos[0, :])
        ys = np.ma.masked_array(antpos[1, :], mask=xs.mask)

        _text = np.empty_like(xs, dtype=object)

        #  want to format No Data where data was not retrieved for each type of power
        for ant_cnt, antname in enumerate(antnames):
            full_info_string = ''
            hdr = "---{}---<br>".format(antname)

            antnum = int(antname[2:])
            if antnum in online_ants:
                full_info_string += "Online<br>"
            elif antnum in built_but_not_on:
                full_info_string += "Contructed but not Online<br>"

            notes_key = [key for key in hu_notes if antname in key]
            if len(notes_key) > 0:
                notes_key = notes_key[0]
                entry_info = ''
                part_hu_hpn = cm_utils.put_keys_in_order(
                    list(hu_notes[notes_key].keys()),
                    sort_order="PNR"
                )
                if notes_key in part_hu_hpn:  # Do the hkey first
                    part_hu_hpn.remove(notes_key)
                    part_hu_hpn = [notes_key] + part_hu_hpn
                for ikey in part_hu_hpn:
                    gps_times = sorted(list(hu_notes[notes_key][ikey].keys()))
                    for gtime in gps_times:
                        atime = cm_utils.get_time_for_display(gtime)
                        entry_info += "    {} ({})  {}<br>".format(ikey, atime, hu_notes[notes_key][ikey][gtime])
                if len(entry_info):
                    full_info_string += "{}<br>{}<br>".format(hdr, entry_info)
            else:
                full_info_string = "No Notes Information"

            _text[ant_cnt] = full_info_string.replace(" ", "\t")

        data_hex = []
        ants = {
            "x": xs.compressed().tolist(),
            "y": ys.compressed().tolist(),
            "text": _text,
            "mode": "markers",
            "visible": True,
            "marker": {
                "color": ["black"] * xs.compressed().size,
                "size": 14,
                "opacity": 0.5,
                "symbol": "hexagon",
            },
            "hovertemplate": "%{text}<extra></extra>",
        }
        # now we want to Fill in the conneted ones
        ants["marker"]["color"][built_but_not_on] = "red"
        ants["marker"]["color"][online_ants] = 'green'

        ants["marker"]["color"] = (
            ants["marker"]["color"].compressed().tolist()
        )
        ants["text"] = ants["text"].compressed().tolist()
        data_hex.append(ants)

        layout_hex = {
            "xaxis": {"title": "East-West Position [m]"},
            "yaxis": {"title": "North-South Position [m]"},
            "title": {
                "text": "Per Ant Notes vs Hex position",
                "font": {"size": 24},
            },
            "hoverlabel": {"align": "left"},
            "margin": {"t": 40},
            "autosize": True,
            "showlegend": False,
            "hovermode": "closest",
        }
        caption = {}
        caption["title"] = "Hookup Notes"
        caption["text"] = (
            "A hookup table in interactive form"
        )

        # Render all the power vs position files
        plotname = "plotly-hex-notes"
        html_template = env.get_template("plotly_base.html")
        js_template = env.get_template("plotly_base.js")

        rendered_hex_html = html_template.render(
            plotname=plotname,
            plotstyle="height: 85vh",
            data_type="Online Antennas",
            gen_date=now.iso,
            data_date_iso=latest.iso,
            data_date_jd=latest.jd,
            data_date_unix_ms=latest.unix * 1000,
            js_name="hex_notes",
            gen_time_unix_ms=now.unix * 1000,
            scriptname=os.path.basename(__file__),
            hostname=computer_hostname,
            caption=caption,
        )

        rendered_hex_js = js_template.render(
            data=data_hex,
            layout=layout_hex,
            plotname=plotname,
        )

        with open("hex_notes.html", "w") as h_file:
            h_file.write(rendered_hex_html)

        with open("hex_notes.js", "w") as js_file:
            js_file.write(rendered_hex_js)


if __name__ == "__main__":
    main()
