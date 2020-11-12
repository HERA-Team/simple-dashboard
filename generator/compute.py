#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2018 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the on-site computers."""

from __future__ import absolute_import, division, print_function

import os
import sys
import json
import copy
import numpy as np
from astropy.time import Time, TimeDelta
from hera_mc import mc
from hera_mc.librarian import LibServerStatus
from hera_mc.rtp import RTPServerStatus
from jinja2 import Environment, FileSystemLoader

LIB_HOSTNAMES = [
    "qmaster",
    "pot1",
    "pot6.karoo.kat.ac.za",
    "pot7.rtp.pvt",
    "pot8.rtp.pvt",
]
RTP_HOSTNAMES = [
    "bigmem1.rtp.pvt",
    "bigmem2.rtp.pvt",
    "cask0.rtp.pvt",
    "cask1.rtp.pvt",
    "gpu1.rtp.pvt",
    "gpu2.rtp.pvt",
    "gpu3.rtp.pvt",
    "gpu4.rtp.pvt",
    "gpu5.rtp.pvt",
    "gpu6.rtp.pvt",
    "gpu7.rtp.pvt",
    "gpu8.rtp.pvt",
    "still1.rtp.pvt",
    "still2.rtp.pvt",
    "still3.rtp.pvt",
    "still4.rtp.pvt",
]
UI_HOSTNAMES = {
    "pot6.karoo.kat.ac.za": "pot6",
    "pot7.rtp.pvt": "pot7",
    "pot7.still.pvt": "pot7",
    "pot8.rtp.pvt": "pot8",
    "pot8.still.pvt": "pot8",
    "cask0.rtp.pvt": "cask0",
    "cask1.rtp.pvt": "cask1",
    "per510-1.rtp.pvt": "cask0",
    "per510-2.rtp.pvt": "cask1",
    "still1.rtp.pvt": "still1",
    "still2.rtp.pvt": "still2",
    "still3.rtp.pvt": "still3",
    "still4.rtp.pvt": "still4",
    "per715-1.rtp.pvt": "still1",
    "per715-2.rtp.pvt": "still2",
    "per715-3.rtp.pvt": "still3",
    "per715-4.rtp.pvt": "still4",
    "gpu1.rtp.pvt": "gpu1",
    "gpu2.rtp.pvt": "gpu2",
    "gpu3.rtp.pvt": "gpu3",
    "gpu4.rtp.pvt": "gpu4",
    "gpu5.rtp.pvt": "gpu5",
    "gpu6.rtp.pvt": "gpu6",
    "gpu7.rtp.pvt": "gpu7",
    "gpu8.rtp.pvt": "gpu8",
    "snb2.rtp.pvt": "gpu3",
    "snb4.rtp.pvt": "gpu6",
    "snb5.rtp.pvt": "gpu8",
    "snb6.rtp.pvt": "gpu7",
    "snb7.rtp.pvt": "gpu4",
    "snb8.rtp.pvt": "gpu2",
    "snb9.rtp.pvt": "gpu5",
    "snb10.rtp.pvt": "gpu1",
    "bigmem1.rtp.pvt": "bigmem1",
    "bigmem2.rtp.pvt": "bigmem2",
}

def is_list(value):
    return isinstance(value, list)

def listify(input):
    if isinstance(input, (list, tuple, np.ndarray)):
        return input
    else:
        return [input]

def index_in(indexable, i):
    return indexable[i]

def get_status(session, tablecls, hostnames, cutoff):
    data_dict = {
        "load": [],
        "timediff": [],
        "mem": [],
        "disk": [],
        "bandwidth": [],
    }
    for host in hostnames:
        data = (
            session.query(tablecls)
            .filter(tablecls.hostname == host)
            .filter(tablecls.mc_time > cutoff.gps)
            .order_by(tablecls.mc_time)
            .all()
        )
        _name = UI_HOSTNAMES.get(host, host)
        time_array = [Time(rec.mc_time, format="gps").isot for rec in data]
        load_array = [rec.cpu_load_pct for rec in data]
        tdiff_array = [rec.mc_system_timediff for rec in data]
        mem_array = [rec.memory_used_pct for rec in data]
        disk_array = [rec.disk_space_pct for rec in data]
        net_array = [rec.network_bandwidth_mbs for rec in data]
        data_arrays = [load_array, tdiff_array, mem_array, disk_array, net_array]
        for pname, array in zip(data_dict.keys(), data_arrays):
            _data = {"x": time_array, "y": array, "name": _name, "type": "scattergl"}
            data_dict[pname].append(_data)
    return data_dict


def main():
    # templates are stored relative to the script dir
    # stored one level up, find the parent directory
    # and split the parent directory away
    script_dir = os.path.dirname(os.path.realpath(__file__))
    split_dir = os.path.split(script_dir)
    template_dir = os.path.join(split_dir[0], "templates")

    env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)
    env.filters["islist"] = is_list
    env.filters["index"] = index_in
    env.filters["listify"] = listify
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

    plotnames = [
        [n1 + "-" + n2 for n1 in ["lib", "rtp"]]
        for n2 in ["load", "disk", "mem", "bandwidth", "timediff"]
    ]
    colsize = 6
    TIME_WINDOW = 14  # days
    now = Time.now()
    cutoff = now - TimeDelta(TIME_WINDOW, format="jd")
    time_axis_range = [cutoff.isot, now.isot]

    caption = {}

    caption["text"] = (
        "An overview of many computer statisics."
        "<br><br>Plotted statistics"
        """<div class="table-responsive">
            <table class="table table-striped" style="border:1px solid black; border-top; 1px solid black;">
            <thead>
            <tr>
              <td style="border-left:1px solid black;">Librarian Related Computers
              <td style="border-left:1px solid black;">RTP Related Computers</td>
            </tr>
            </thead>
            <tbody>
              <tr>
                <td style="border-left:1px solid black;">Load % per Computer
                <td style="border-left:1px solid black;">Load % per Computer</td>
              </tr>
              <tr>
                <td style="border-left:1px solid black;">Local Disk Usage %
                <td style="border-left:1px solid black;">Local Disk Usage %</td></tr>
              <tr>
                <td style="border-left:1px solid black;">Local Memory Usage %
                <td style="border-left:1px solid black;">Local Memory Usage %</td></tr>
              <tr>
                <td style="border-left:1px solid black;">Network I/O rate (MB/s)
                <td style="border-left:1px solid black;">Network I/O rate (MB/s)</td>
              </tr>
              <tr>
                <td style="border-left:1px solid black;">M&C time diff (s)
                <td style="border-left:1px solid black;">M&C time diff (s)</td>
              </tr>
            </tbody>
            </table>
         </div>
        """
    )

    caption["title"] = "Compute Help"

    html_template = env.get_template("plotly_base.html")
    basename="compute"
    rendered_html = html_template.render(
        plotname=plotnames,
        plotstyle="height: 19.5%",
        colsize=colsize,
        gen_date=now.iso,
        gen_time_unix_ms=now.unix * 1000,
        js_name=basename,
        hostname=computer_hostname,
        scriptname=os.path.basename(__file__),
        caption=caption,
    )
    with open("compute.html", "w") as h_file:
        h_file.write(rendered_html)

    with db.sessionmaker() as session:
        lib_data = get_status(session, LibServerStatus, LIB_HOSTNAMES, cutoff)
        rtp_data = get_status(session, RTPServerStatus, RTP_HOSTNAMES, cutoff)

        layout = {
            "xaxis": {"range": time_axis_range},
            "yaxis": {"title": "placeholder", "rangemode": "tozero"},
            "title": {"text": "placeholder", "font": {"size": 18}},
            "height": 200,
            "margin": {"t": 25, "r": 10, "b": 10, "l": 40},
            "legend": {"orientation": "h", "x": 0.15, "y": -0.15},
            "showlegend": True,
            "hovermode": "closest",
        }
        yaxis_titles = {
            "load": "Load % per CPU",
            "disk": "Local disk usage (%)",
            "mem": "Memory usage (%)",
            "bandwidth": "Network I/O (MB/s)",
            "timediff": "M&C time diff. (s)",
        }

        titles = {
            "load": "CPU Load",
            "disk": "Disk Usage",
            "mem": "Memory Usage",
            "bandwidth": "Network I/O",
            "timediff": "M&C time diff. ",
        }
        name_list = []
        layout_list = []
        json_name_list = []
        for server_type, data_dict in zip(["lib", "rtp"], [lib_data, rtp_data]):

            for pname in ["load", "disk", "mem", "bandwidth", "timediff"]:
                _layout = copy.deepcopy(layout)
                _layout["yaxis"]["title"] = yaxis_titles[pname]
                _layout["title"]["text"] = server_type + " " + titles[pname]
                layout_list.append(_layout)
                name_list.append(server_type + "-" + pname)
                json_name = "_".join([basename, server_type, pname])
                json_name_list.append(json_name)
                with open("{}.json".format(json_name), "w") as json_file:
                    json.dump(data_dict[pname], json_file)

        js_template = env.get_template("plotly_base.js")
        rendered_js = js_template.render(
            json_name=json_name_list, plotname=name_list, layout=layout_list
        )

        with open("{}.js".format(basename), "w") as js_file:
            js_file.write(rendered_js)


if __name__ == "__main__":
    main()
