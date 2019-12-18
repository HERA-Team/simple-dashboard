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


def process_string(input_str, time_string_offset=37):
    # the header is already 37 characters long
    # take this offset into account but only on the first iteration
    if len(input_str) > 80 - time_string_offset:
        space_ind = 79 - time_string_offset

        if ' ' in input_str[space_ind:]:
            space_ind += input_str[space_ind:].index(' ')

            input_str = (
                input_str[:space_ind]
                + "<br>\t\t\t\t\t\t\t\t"
                + process_string(input_str[space_ind:], time_string_offset=8)
            )
    return input_str


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
        "--hookup-type",
        dest="hookup_type",
        help="Force use of specified hookup type.",
        default=None,
    )

    args = parser.parse_args()

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
        latest.out_subfmt = u"date_hm"

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

        stations = hsession.get_connected_stations(at_date="now")

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

        xs = np.array(antpos[0, :])
        ys = np.array(antpos[1, :])

        _text = np.empty_like(xs, dtype=object)
        all_tables = []

        table = {}
        table["title"] = "Hookup Notes"
        table["div_style"] = 'style="max-height: 75vh; text-align: center; overflow-x: auto; overflow-y: scroll;"'

        table["headers"] = ["Antenna", "Status", "Notes"]
        table["rows"] = []

        #  want to format No Data where data was not retrieved for each type of power
        for ant_cnt, antname in enumerate(antnames):
            row = {}

            _stat = []
            full_info_string = "{}<br>".format(antname)
            _stat.append(antname)

            antnum = int(antname[2:])
            if antnum in online_ants:
                full_info_string += "Online<br>"
                _stat.append("Online")
            elif antnum in built_but_not_on:
                full_info_string += "Constructed but not Online<br>"
                _stat.append("Constructed but not Online")
            else:
                _stat.append('Offline')

            notes_key = antname + ":A"
            if notes_key in hu_notes:
                entry_info = ''
                # used for the html table version
                no_space_info = ''
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
                        notes = process_string(hu_notes[notes_key][ikey][gtime])
                        entry_info += "    {} ({})  {}<br>".format(ikey, atime, notes)
                        # we don't need the fancy line breaks because HTML will do it for us
                        no_space_info += "{} ({})  {}<br>".format(ikey, atime, hu_notes[notes_key][ikey][gtime])
                if len(entry_info):
                    full_info_string += "{}<br>".format(entry_info)
                    # Replace all the spaces with \t and hyphens with non-breaking hyphens
                    _stat.append(
                        no_space_info
                        .replace(" ", "\t")
                        .replace('-', u"\u2011")
                    )
                else:
                    _stat.append("N/A")
            else:
                full_info_string += "No Notes Information"
                _stat.append("N/A")

            # replace spaces with \t and - with non-breaking hyphen
            full_info_string = full_info_string.replace(" ", "\t").replace('-', u"\u2011")

            _text[ant_cnt] = full_info_string

            row["text"] = _stat
            row["style"] = "text-align: left;"
            table["rows"].append(row)

        all_tables.append(table)
        html_template = env.get_template("tables_with_footer.html")

        rendered_html = html_template.render(
            tables=all_tables,
            gen_date=Time.now().iso,
            gen_time_unix_ms=Time.now().unix * 1000,
            scriptname=os.path.basename(__file__),
            hostname=computer_hostname,
            colsize="12",
        )

        with open("hookup_notes_table.html", "w") as h_file:
            h_file.write(rendered_html)

        data_hex = []
        ants = {
            "x": xs.tolist(),
            "y": ys.tolist(),
            "text": _text.tolist(),
            "mode": "markers",
            "visible": True,
            "marker": {
                "color": np.array(["black"] * xs.size, dtype=object),
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
            ants["marker"]["color"].tolist()
        )
        data_hex.append(ants)

        layout_hex = {
            "xaxis": {"title": "East-West Position [m]"},
            "yaxis": {
                "title": "North-South Position [m]",
                "scaleanchor": "x"
            },
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
            "Prints any notes generated through hera_mc/hookup.py for any "
            "parts connected to each antenna.<br>"
            "Green antenna are 'online' meaning there are current autocorrelation "
            "entries in redis.<br>"
            "Red antennas are constructed and registered as fully connected but "
            "do not have any data in redis.<br>"
            "Black antennas are not yet constructed or have no information available."
        )

        # Render all the power vs position files
        plotname = "plotly-hex-notes"
        html_template = env.get_template("plotly_base.html")
        js_template = env.get_template("plotly_base.js")

        rendered_hex_html = html_template.render(
            plotname=plotname,
            plotstyle="height: 100%",
            data_type="Online Antennas",
            gen_date=now.iso,
            data_date_iso=latest.iso,
            data_date_jd="{:.3f}".format(latest.to_value('jd', subfmt='float')),
            data_date_unix_ms=latest.to_value('unix') * 1000,
            js_name="hookup_notes",
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

        with open("hookup_notes.html", "w") as h_file:
            h_file.write(rendered_hex_html)

        with open("hookup_notes.js", "w") as js_file:
            js_file.write(rendered_hex_js)


if __name__ == "__main__":
    main()
