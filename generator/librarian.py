#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Librarian."""

from __future__ import absolute_import, division, print_function

import os
import re
import sys
import json
import copy
import numpy as np
from astropy.time import Time, TimeDelta
from html import escape
from hera_mc import mc
from hera_mc.librarian import (
    LibRAIDErrors,
    LibRAIDStatus,
    LibRemoteStatus,
    LibServerStatus,
    LibStatus,
)
from jinja2 import Environment, FileSystemLoader


HOSTNAMES = [
    "qmaster",
    "pot1",
    "pot6.karoo.kat.ac.za",
    "pot7.rtp.pvt",
    "pot8.rtp.pvt",
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

REMOTES = ["aoc-uploads", "shredder"]


def is_list(value):
    return isinstance(value, list)

def listify(input):
    if isinstance(input, (list, tuple, np.ndarray)):
        return input
    else:
        return [input]

def index_in(indexable, i):
    return indexable[i]


def do_server_loads(session, cutoff):
    _data = []
    for host in HOSTNAMES:
        data = (
            session.query(LibServerStatus.mc_time, LibServerStatus.cpu_load_pct)
            .filter(LibServerStatus.hostname == host)
            .filter(LibServerStatus.mc_time > cutoff.gps)
            .order_by(LibServerStatus.mc_time)
            .all()
        )
        time_array = Time([t[0] for t in data], format="gps")
        if time_array:
            time_array = time_array.isot.tolist()
        else:
            time_array = []
        __data = {
            "x": time_array,
            "y": [t[1] for t in data],
            "name": UI_HOSTNAMES.get(host, host),
            "type": "scattergl",
        }

        _data.append(__data)
    return _data


def do_disk_space(session, cutoff):
    _data = []
    data = (
        session.query(LibStatus.time, LibStatus.data_volume_gb)
        .filter(LibStatus.time > cutoff.gps)
        .order_by(LibStatus.time)
        .all()
    )

    time_array = Time([t[0] for t in data], format="gps")
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []

    __data = {
        "x": time_array,
        "y": [t[1] for t in data],
        "name": "Data Volume".replace(" ", "\t"),
        "type": "scattergl",
    }
    _data.append(__data)

    data = (
        session.query(LibStatus.time, LibStatus.free_space_gb)
        .filter(LibStatus.time > cutoff.gps)
        .order_by(LibStatus.time)
        .all()
    )

    time_array = Time([t[0] for t in data], format="gps")
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []
    __data = {
        "x": time_array,
        "y": [t[1] for t in data],
        "name": "Free space".replace(" ", "\t"),
        "type": "scattergl",
        "yaxis": "y2",
    }
    _data.append(__data)

    return _data


def do_upload_ages(session, cutoff):
    _data = []

    data = (
        session.query(LibStatus.time, LibStatus.upload_min_elapsed)
        .filter(LibStatus.time > cutoff.gps)
        .order_by(LibStatus.time)
        .all()
    )

    time_array = Time([t[0] for t in data], format="gps")
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []
    __data = {
        "x": time_array,
        "y": [t[1] for t in data],
        "name": "Time since last upload".replace(" ", "\t"),
        "type": "scattergl",
    }
    _data.append(__data)

    return _data


def do_bandwidths(session, cutoff):
    _data = []

    for remote in REMOTES:
        data = (
            session.query(LibRemoteStatus.time, LibRemoteStatus.bandwidth_mbs)
            .filter(LibRemoteStatus.remote_name == remote)
            .filter(LibRemoteStatus.time > cutoff.gps)
            .order_by(LibRemoteStatus.time)
            .all()
        )

        time_array = Time([t[0] for t in data], format="gps")
        if time_array:
            time_array = time_array.isot.tolist()
        else:
            time_array = []
        __data = {
            "x": time_array,
            "y": [t[1] for t in data],
            "name": ("{name} transfer rate".format(name=remote).replace(" ", "\t")),
            "type": "scattergl",
        }
        _data.append(__data)

    return _data


def do_ping_times(session, cutoff):
    _data = []
    for remote in REMOTES:
        data = (
            session.query(LibRemoteStatus.time, LibRemoteStatus.ping_time)
            .filter(LibRemoteStatus.remote_name == remote)
            .filter(LibRemoteStatus.time > cutoff.gps)
            .order_by(LibRemoteStatus.time)
            .all()
        )

        time_array = Time([t[0] for t in data], format="gps")
        if time_array:
            time_array = time_array.isot.tolist()
        else:
            time_array = []
        __data = {
            "x": time_array,
            "y": [1000 * t[1] for t in data],
            "name": "{name} ping time".format(name=remote).replace(" ", "\t"),
            "type": "scattergl",
        }
        _data.append(__data)

    return _data


def creation_date(path_to_file):
    """
    Try to get the date that a file was created.

    Falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    Modified to remove the non-linux sections of the code found on link.
    """
    stat = os.stat(path_to_file)
    return stat.st_mtime


def do_num_files(session, cutoff):
    _data = []
    data = (
        session.query(LibStatus.time, LibStatus.num_files)
        .filter(LibStatus.time > cutoff.gps)
        .order_by(LibStatus.time)
        .all()
    )
    time_array = Time([t[0] for t in data], format="gps")
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []
    __data = {
        "x": time_array,
        "y": [t[1] for t in data],
        "name": "Total Number of files".replace(" ", "\t"),
        "type": "scattergl",
    }

    _data.append(__data)

    return _data


def do_compare_file_types(TIME_WINDOW):
    # This will only execute on qmaster
    # Count the number of raw files staged at /mnt/sn1 that are like zen.(\d+).(\d+).uvh5
    # Compare with the number of processed files that match zen.(\d+).(\d+).HH.uvh5
    # only compare files that have a JD newer than the oldest raw file
    if sys.version_info[0] < 3:
        # py2
        computer_hostname = os.uname()[1]
    else:
        # py3
        computer_hostname = os.uname().nodename
    if computer_hostname != "qmaster":
        return
    timesteps = np.linspace(-1 * TIME_WINDOW, 0, 24 * 14 * 6, endpoint=True)
    time_array = Time.now() + TimeDelta(timesteps, format="jd")
    _data = []
    sum_regex = r"zen.(\d+.\d+).sum.uvh5"
    diff_regex = r"zen.(\d+.\d+).diff.uvh5"
    data_dir = "/mnt/sn1/"
    try:
        sum_names = [f for f in os.listdir(data_dir) if re.search(sum_regex, f)]
    except OSError as err:
        print(
            "Experienced OSError while " "attempting to find files: {err}".format(err)
        )
        return

    try:
        diff_names = [
            f for f in os.listdir(data_dir) if re.search(diff_regex, f)
        ]
    except OSError as err:
        print(
            "Experienced OSError while " "attempting to find files: {err}".format(err)
        )
        return

    sum_jd = Time([float(re.findall(sum_regex, f)[0]) for f in sum_names], format="jd")
    diff_jd = Time(
        [float(re.findall(diff_regex, f)[0]) for f in diff_names], format="jd"
    )

    # try to find the times they were created
    sum_times = Time(
        [creation_date(os.path.join(data_dir, n)) for n in sum_names], format="unix"
    )

    diff_times = Time(
        [creation_date(os.path.join(data_dir, n)) for n in diff_names],
        format="unix",
    )
    # Only consider processed files if their JD is equal to or newer than
    # the oldest raw file
    hh_times = diff_times[diff_jd >= sum_jd.min()]

    n_files_raw = []
    n_files_processed = []
    for _t in time_array:
        n_files_raw.append(int(sum(list(_t >= sum_times))))
        n_files_processed.append(int(sum(list(_t >= hh_times))))

    __data = {
        "x": time_array.isot.tolist(),
        "y": n_files_raw,
        "name": "Sum files".replace(" ", "\t"),
        "type": "scattergl",
    }

    _data.append(__data)

    __data = {
        "x": time_array.isot.tolist(),
        "y": n_files_processed,
        "name": "Diff files".replace(" ", "\t"),
        "type": "scattergl",
    }

    _data.append(__data)

    return _data


def do_raid_errors(session, cutoff):
    q = (
        session.query(LibRAIDErrors)
        .filter(LibRAIDErrors.time > cutoff.gps)
        .order_by(LibRAIDErrors.time.desc())
        .limit(10)
    )
    table = {}
    table["title"] = "Recent RAID Errors".replace(" ", "\t")
    table["headers"] = ["Date", "Host", "Disk", "Message"]

    rows = []

    for rec in q:
        _row = {}
        _row["time"] = Time(rec.time, format="gps").iso.replace(" ", "\t")
        _row["hostname"] = rec.hostname
        _row["disk"] = rec.disk
        _row["message"] = escape(rec.log)
        rows.append(_row)
    table["rows"] = rows
    return table


def do_raid_status(session, cutoff):
    q = (
        session.query(LibRAIDStatus)
        .filter(LibRAIDStatus.time > cutoff.gps)
        .filter(~LibRAIDStatus.hostname.startswith("per"))  # hack
        .order_by(LibRAIDStatus.time.desc())
        .limit(10)
    )
    table = {}
    table["title"] = "Recent RAID Status Reports".replace(" ", "\t")
    table["headers"] = ["Date", "Host", "Num. Disks", "Message"]

    rows = []

    for rec in q:
        _row = {}
        _row["time"] = Time(rec.time, format="gps").iso.replace(" ", "\t")
        _row["hostname"] = rec.hostname
        _row["disk"] = rec.num_disks
        _row["message"] = escape(rec.info)
        rows.append(_row)
    table["rows"] = rows

    return table


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

    colsize = 6
    TIME_WINDOW = 14  # days
    now = Time.now()
    cutoff = now - TimeDelta(TIME_WINDOW, format="jd")
    time_axis_range = [cutoff.isot, now.isot]
    plotnames = [
        ["server-loads", "upload-ages"],
        ["disk-space", "bandwidths"],
        ["num-files", "ping-times"],
        ["file-compare"],
    ]

    layout = {
        "xaxis": {"range": time_axis_range},
        "yaxis": {"title": "Load % per CPU"},
        "title": {"text": "NONE"},
        "height": 200,
        "margin": {"t": 30, "r": 50, "b": 2, "l": 50},
        "legend": {"orientation": "h", "x": 0.15, "y": -0.15},
        "showlegend": True,
        "hovermode": "closest",
    }

    html_template = env.get_template("librarian_table.html")
    js_template = env.get_template("plotly_base.js")

    json_name_list = []
    layout_list = []
    plotname_list = []

    basename = "librarian"
    with db.sessionmaker() as session:

        data = do_server_loads(session, cutoff)
        _layout = copy.deepcopy(layout)
        _layout["title"]["text"] = "CPU Loads"

        layout_list.append(_layout)
        plotname_list.append("server-loads")
        json_name = basename + "_server_loads"

        with open("{}.json".format(json_name), "w") as json_file:
            json.dump(data, json_file)

        json_name_list.append(json_name)

        data = do_upload_ages(session, cutoff)

        _layout = copy.deepcopy(layout)
        _layout["yaxis"]["title"] = "Minutes"
        _layout["yaxis"]["zeroline"] = False
        _layout["title"]["text"] = "Time Since last upload"
        layout_list.append(_layout)

        plotname_list.append("upload-ages")
        json_name = basename + "_upload_ages"

        with open("{}.json".format(json_name), "w") as json_file:
            json.dump(data, json_file)

        json_name_list.append(json_name)

        data = do_disk_space(session, cutoff)

        _layout = copy.deepcopy(layout)

        _layout["yaxis"]["title"] = "Data Volume [GiB]"
        _layout["yaxis"]["zeroline"] = True
        _layout["yaxis2"] = {
            "title": "Free Space [GiB]",
            "overlaying": "y",
            "side": "right",
        }
        _layout["title"]["text"] = "Disk Usage"
        layout_list.append(_layout)

        plotname_list.append("disk-space")
        json_name = basename + "_disk_space"

        with open("{}.json".format(json_name), "w") as json_file:
            json.dump(data, json_file)

        json_name_list.append(json_name)

        data = do_bandwidths(session, cutoff)
        _layout = copy.deepcopy(layout)
        _layout.pop("yaxis2", None)
        _layout["yaxis"]["title"] = "MB/s"
        _layout["title"]["text"] = "Librarian Transfer Rates"
        layout_list.append(_layout)

        plotname_list.append("bandwidths")
        json_name = basename + "_bandwidths"

        with open("{}.json".format(json_name), "w") as json_file:
            json.dump(data, json_file)

        json_name_list.append(json_name)

        data = do_num_files(session, cutoff)
        _layout = copy.deepcopy(layout)
        _layout["yaxis"]["title"] = "Number"
        _layout["yaxis"]["zeroline"] = False
        _layout["title"]["text"] = "Total Number of Files in Librarian"
        layout_list.append(_layout)

        plotname_list.append("num-files")
        json_name = basename + "_num_files"

        with open("{}.json".format(json_name), "w") as json_file:
            json.dump(data, json_file)

        json_name_list.append(json_name)

        data = do_ping_times(session, cutoff)
        _layout = copy.deepcopy(layout)
        _layout["yaxis"]["title"] = "ms"
        _layout["yaxis"]["rangemode"] = "tozero"
        _layout["yaxis"]["zeroline"] = True
        _layout["title"]["text"] = "Server Ping Times"
        layout_list.append(_layout)

        plotname_list.append("ping-times")
        json_name = basename + "_ping_times"

        with open("{}.json".format(json_name), "w") as json_file:
            json.dump(data, json_file)

        json_name_list.append(json_name)

        data = do_compare_file_types(TIME_WINDOW)
        if data is not None:
            _layout = copy.deepcopy(layout)
            _layout["yaxis"]["title"] = "Files in <br><b>temporary staging</b>"
            _layout["yaxis"]["zeroline"] = True
            _layout["margin"]["l"] = 60
            _layout["title"]["text"] = "Files in <b>Temporary Staging</b>"
            layout_list.append(_layout)

            plotname_list.append("file-compare")
            json_name = basename + "_file_compare"

            with open("{}.json".format(json_name), "w") as json_file:
                json.dump(data, json_file)

            json_name_list.append(json_name)

        tables = []
        tables.append(do_raid_errors(session, cutoff))
        tables.append(do_raid_status(session, cutoff))

        caption = {}
        caption["title"] = "Librarian Help"

        caption["text"] = (
            "An overview of many Librarian related statisics. "
            "<br>The Plots are organized as follows: "
            """<div class="table-responsive">
                <table class="table table-striped" style="border:1px solid black; border-top; 1px solid black;">
                <tbody>
                  <tr>
                    <td style="border-left:1px solid black;">CPU Load
                    <td style="border-left:1px solid black;">Time Since last Upload</td>
                  </tr>
                  <tr>
                    <td style="border-left:1px solid black;">Disk Space Usage
                    <td style="border-left:1px solid black;">AOC Transfer Speeds</td></tr>
                  <tr>
                    <td style="border-left:1px solid black;">Total Number of files in Librarian
                    <td style="border-left:1px solid black;">AOC ping time</td></tr>
                  <tr>
                    <td style="border-left:1px solid black;">Files in <b>Temporary Storage</b>
                    <td style="border-left:1px solid black;"></td></tr>
                </tbody>
                </table>
             </div>
            """
            "The files in temporary storage counts the number of raw files at /mnt/sn1 "
            "on qmaster and compares that to the number of processed files whose "
            "JDs are >= oldest raw file.<br>It is a hacky proxy for 'DID RTP RUN?' "
            "<br>Assuming RTP runs successfully on all files from an observation, "
            "both lines should report the same number of files."
            "<br><br>"
            "The final two tables give some recent RAID errors and status reports."
        )

        rendered_html = html_template.render(
            plotname=plotnames,
            title="Librarian",
            plotstyle="height: 24.5%",
            colsize=colsize,
            gen_date=now.iso,
            gen_time_unix_ms=now.unix * 1000,
            js_name=basename,
            hostname=computer_hostname,
            scriptname=os.path.basename(__file__),
            tables=tables,
            caption=caption,
        )

        rendered_js = js_template.render(
            json_name=json_name_list, plotname=plotname_list, layout=layout_list
        )

        with open("{}.js".format(basename), "w") as js_file:
            js_file.write(rendered_js)

        with open("{}.html".format(basename), "w") as h_file:
            h_file.write(rendered_html)


if __name__ == "__main__":
    main()
