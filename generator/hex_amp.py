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
from multiprocessing import Process
from hera_mc import mc, cm_sysutils
from astropy.time import Time
from jinja2 import Environment, FileSystemLoader

node_path = {
    0: "M -80,-125, L -100,-90 L -60,-90 L -60,-78 L -50,-78, L -35,-105 L -45,-125 Z"
}

def runInParallel(*fns):
    proc = []
    for fn in fns:
        p = Process(target=fn[0], args=fn[1])
        p.start()
        proc.append(p)
    for p in proc:
        p.join()


def is_list(value):
    return isinstance(value, list)

def listify(input):
    if isinstance(input, (list, tuple, np.ndarray)):
        return input
    else:
        return [input]

def index_in(indexable, i):
    return indexable[i]

def write_csv(filename, antnames, ants, pols, stat_names, stats, built_but_not_on):
    """Write out antenna stats to csv file.

    Parameters
    ----------
    filenae : str
        name of file to write
    antnames : array_like str
        Names of antennas
    ants : array_like int
        Antenna numbers
    pols : array_list str
        array of antenna feed polarizations
    stat_names : array_like str
        array of names of antenna statistics to write to file
    stats : array_like
        list of arrays of statistics to write to file
    built_but_not_on : array_like int
        list of antenna numbers which are constructed but not on.

    Returns
    -------
    None

    """
    print(Time.now().iso + "    Writing to antenna stats to {}".format(filename))
    format_string = "{}"
    float_format_string = "{:.5f}"
    stats = np.ma.masked_invalid(stats)

    with open(filename, "w") as csv_file:
        csv_file.write(
            format_string.format("ANTNAME")
            + ","
            + ",".join([format_string] * len(stat_names)).format(*stat_names)
        )
        csv_file.write("\n")

        for ant_cnt, antname in enumerate(antnames):
            antnum = int(antname[2:])
            for pol_cnt, pol in enumerate(pols):
                _name = antname + pol
                if antnum in ants:
                    ant_ind = np.nonzero(antnum == ants)[0].item()
                    csv_file.write(
                        format_string.format(_name)
                        + ","
                        + ",".join([float_format_string] * len(stats)).format(
                            *[p.filled(np.nan)[pol_cnt, ant_ind] for p in stats]
                        )
                    )
                elif antnum in built_but_not_on:
                    csv_file.write(
                        format_string.format(_name)
                        + ",CONST"
                        + ","
                        + ",".join(["nan"] * (len(stats) - 1))
                    )
                else:
                    csv_file.write(
                        format_string.format(_name)
                        + ",OFF"
                        + ","
                        + ",".join(["nan"] * (len(stats) - 1))
                    )

                csv_file.write("\n")
    return

def make_hex(
    powers,
    xs_offline,
    ys_offline,
    name_offline,
    built_but_not_on,
    xs,
    ys,
    nodes,
    node_ind,
    _text,
    env,
    latest,
    pols,
    computer_hostname,
    names
):
    masks = [[True] for p in powers]

    # Offline antennas
    data_hex = []
    offline_ants = {
        "x": xs_offline.compressed().tolist(),
        "y": ys_offline.compressed().tolist(),
        "text": name_offline,
        "mode": "markers",
        "visible": True,
        "marker": {
            "color": np.ma.masked_array(
                ["black"] * len(name_offline), mask=xs_offline.mask
            ),
            "size": 14,
            "opacity": 0.5,
            "symbol": "hexagon",
        },
        "hovertemplate": "%{text}<extra></extra>",
    }
    # now we want to Fill in the conneted ones
    offline_ants["marker"]["color"][built_but_not_on] = "red"
    offline_ants["text"].data[built_but_not_on] = [
        offline_ants["text"].data[ant].split("<br>")[0]
        + "<br>Constructed<br>Not\tOnline"
        for ant in built_but_not_on
    ]

    offline_ants["marker"]["color"] = (
        offline_ants["marker"]["color"].compressed().tolist()
    )
    offline_ants["text"] = offline_ants["text"].compressed().tolist()
    data_hex.append(offline_ants)

    #  for each type of power, loop over pols and print out the data
    #  save up a mask array used for the buttons later
    #  also plot the bad ones!3
    colorscale = "Viridis"

    # define some custom scale values for the ADC RMS page
    rms_scale_vals = [2, 20]
    relavitve_values = [0.4, 0.7]
    rms_color_scale = [
        ["0.0", "rgb(68,1,84)"],
        ["0.2", "rgb(62,74,137)"],
        ["0.3", "rgb(38,130,142)"],
        ["0.4", "rgb(53,183,121)"],
        ["0.5", "rgb(53,183,121)"],
        ["0.6", "rgb(53,183,121)"],
        ["0.7", "rgb(109,205,89)"],
        ["0.8", "rgb(180,222,44)"],
        ["1.0", "rgb(253,231,37)"],
    ]

    for pow_ind, power in enumerate(powers):
        if power.compressed().size > 0:
            vmax = np.max(power.compressed())
            vmin = np.min(power.compressed())
        else:
            vmax = 1
            vmin = 0

        colorscale = "Viridis"

        if pow_ind == 3:
            cbar_title = "RMS\tlinear"
            vmin = rms_scale_vals[0] * relavitve_values[0]
            vmax = rms_scale_vals[1] / relavitve_values[1]
            colorscale = rms_color_scale
        elif pow_ind == 4 or pow_ind == 5:
            cbar_title = "Degrees"
        elif pow_ind == len(powers) - 1:
            cbar_title = "Median\tCoeff"
        else:
            cbar_title = "dB"

        if pow_ind == 0:
            visible = True
        else:
            visible = False

        for pol_ind, pol in enumerate(pols):
            for mask_cnt, mask in enumerate(masks):
                if mask_cnt == pow_ind:
                    mask.extend([True] * 2)
                else:
                    mask.extend([False] * 2)

            _power = {
                "x": xs.data[~power[pol_ind].mask].tolist(),
                "y": ys[pol_ind].data[~power[pol_ind].mask].tolist(),
                "text": _text[pol_ind][~power[pol_ind].mask].tolist(),
                "mode": "markers",
                "visible": visible,
                "marker": {
                    "color": power[pol_ind].data[~power[pol_ind].mask].tolist(),
                    "size": 14,
                    "cmin": vmin,
                    "cmax": vmax,
                    "colorscale": colorscale,
                    "colorbar": {"thickness": 20, "title": cbar_title},
                },
                "hovertemplate": "%{text}<extra></extra>",
            }
            data_hex.append(_power)

            _power_offline = {
                "x": xs.data[power[pol_ind].mask].tolist(),
                "y": ys[pol_ind].data[power[pol_ind].mask].tolist(),
                "text": _text[pol_ind][power[pol_ind].mask].tolist(),
                "mode": "markers",
                "visible": visible,
                "marker": {
                    "color": "orange",
                    "size": 14,
                    "cmin": vmin,
                    "cmax": vmax,
                    "colorscale": colorscale,
                    "colorbar": {"thickness": 20, "title": cbar_title},
                },
                "hovertemplate": "%{text}<extra></extra>",
            }
            data_hex.append(_power_offline)

    buttons = []
    for _name, mask in zip(names, masks):
        _button = {
            "args": [{"visible": mask}, {"title": "", "annotations": {}}],
            "label": _name,
            "method": "restyle",
        }
        buttons.append(_button)

    updatemenus_hex = [{"buttons": buttons, "showactive": True, "type": "buttons"}]

    layout_hex = {
        "xaxis": {"title": "East-West Position [m]"},
        "yaxis": {
            "title": "North-South Position [m]",
            "scaleanchor": "x"
        },
        "title": {
            "text": "Per Antpol Stats vs Hex position",
            "font": {"size": 24},
        },
        "hoverlabel": {"align": "left"},
        "margin": {"t": 40},
        "autosize": True,
        "showlegend": False,
        "hovermode": "closest",
    }
    layout_hex["shapes"] = []

    for node in nodes:
        if node in node_path:
            shape = {
                "type": "path",
                "path": node_path[node],
                "opacity": 0.2,
                "layer": "below",
                # "fillcolor": 'blue',
                # "line": {
                # "color": 'blue'
                # }
            }
            layout_hex["shapes"].append(shape)

    caption = {}
    caption["title"] = "Stats vs Hex pos Help"
    caption["text"] = (
        "This plot shows various statistics and measurements "
        "per ant-pol versus its position in the array."
        "<br>Antennas which are build but not fully hooked up "
        "are shown in light red."
        "<br>Grey antennas are not yet constructed."
        "<br><br><h4>Available plotting options</h4>"
        "<ul>"
        "<li>Auto Corr - Median Auto Correlation (in db) "
        "from the correlator with equalization coefficients "
        "divided out</li>"
        "<li>Pam Power - Latest Pam Power (in db) recorded in M&C</li>"
        "<li>ADC Power - Latest ADC Power (in db) recorded in M&C</li>"
        "<li>ADC RMS - Latest linear ADC RMS recorded in M&C</li>"
        "<li>FEM IMU THETA - IMU-reported theta, in degrees</li>"
        "<li>FEM IMU PHI - IMU-reported phi, in degrees</li>"
        "<li>EQ Coeffs - Latest Median Equalization Coefficient recorded in M&C</li>"
        "</ul>"
        "Any antpol showing with an orange color means "
        "no data is avaible for the currenty plot selection."
        "<h4>Hover label Formatting</h4>"
        "<ul>"
        "<li>Antenna Name from M&C<br>(e.g. HH0n = Hera Hex Antenna 0 Polarization N)</li>"
        "<li>Snap hostname from M&C<br>(e.g. heraNode0Snap0)</li>"
        "<li>PAM Number</li>"
        "<li>Median Auto Correlation power in dB</li>"
        "<li>PAM power in dB</li>"
        "<li>ADC power in dB</li>"
        "<li>Linear ADC RMS</li>"
        "<li>FEM IMU reported theta in degrees</li>"
        "<li>FEM IMU reported phi in degrees</li>"
        "<li>Median Equalization Coefficient</li>"
        "<li>Time ago in hours the M&C Antenna Status was updated. "
        "This time stamp applies to all data for this antenna "
        "except the Auto Correlation.</li>"
        "</ul>"
        "In any hover label entry 'No Data' means "
        "information not currrently available in M&C."
    )

    # Render all the power vs position files
    plotname = "plotly-hex"
    html_template = env.get_template("plotly_base.html")
    js_template = env.get_template("plotly_base.js")

    if sys.version_info.minor >= 8 and sys.version_info.major > 2:
        time_jd = latest.to_value('jd', subfmt='float')
        time_unix = latest.to_value('unix')
    else:
        time_jd = latest.jd
        time_unix = latest.unix

    basename = "hex_amp"
    rendered_hex_html = html_template.render(
        plotname=plotname,
        data_type="Auto correlations",
        plotstyle="height: 100%",
        gen_date=Time.now().iso,
        data_date_iso=latest.iso,
        data_date_jd="{:.3f}".format(time_jd),
        data_date_unix_ms=time_unix * 1000,
        js_name=basename,
        gen_time_unix_ms=Time.now().unix * 1000,
        scriptname=os.path.basename(__file__),
        hostname=computer_hostname,
        caption=caption,
    )

    rendered_hex_js = js_template.render(
        json_name=basename,
        layout=layout_hex,
        updatemenus=updatemenus_hex,
        plotname=plotname,
    )

    with open("{}.json".format(basename), "w") as json_file:
        json.dump(data_hex, json_file)

    with open("{}.html".format(basename), "w") as h_file:
        h_file.write(rendered_hex_html)

    with open("{}.js".format(basename), "w") as js_file:
        js_file.write(rendered_hex_js)


def make_node(
    powers,
    _text,
    names,
    hostname,
    nodes,
    node_ind,
    pols,
    env,
    latest,
    computer_hostname,
):
    rms_scale_vals = [2, 20]
    relavitve_values = [0.4, 0.7]
    rms_color_scale = [
        ["0.0", "rgb(68,1,84)"],
        ["0.2", "rgb(62,74,137)"],
        ["0.3", "rgb(38,130,142)"],
        ["0.4", "rgb(53,183,121)"],
        ["0.5", "rgb(53,183,121)"],
        ["0.6", "rgb(53,183,121)"],
        ["0.7", "rgb(109,205,89)"],
        ["0.8", "rgb(180,222,44)"],
        ["1.0", "rgb(253,231,37)"],
    ]
    # now prepare the data to be plotted vs node number
    data_node = []

    masks = [[] for p in powers]

    vmax = [
        np.max(power.compressed()) if power.compressed().size > 1 else 1
        for power in powers
    ]
    vmin = [
        np.min(power.compressed()) if power.compressed().size > 1 else 0
        for power in powers
    ]
    vmin[3] = rms_scale_vals[0] * relavitve_values[0]
    vmax[3] = rms_scale_vals[1] / relavitve_values[1]

    for node in nodes:
        node_index = np.where(node_ind == node)[0]
        hosts = hostname[node_index]

        host_index = np.argsort(hosts)

        ys = np.ma.masked_array(
            [
                np.arange(node_index.size) + 0.3 * pol_cnt
                for pol_cnt, pol in enumerate(pols)
            ],
            mask=powers[0][:, node_index].mask,
        )
        xs = np.zeros_like(ys)
        xs[:] = node
        powers_node = [pow[:, node_index] for pow in powers]
        __text = _text[:, node_index]

        for pow_ind, power in enumerate(powers_node):
            cbar_title = "dB"
            if pow_ind == 4 or pow_ind == 5:
                cbar_title = "Degrees"

            if pow_ind == 3:
                colorscale = rms_color_scale
            else:
                colorscale = "Viridis"
            colorscale = "Viridis"

            if pow_ind == 3:
                cbar_title = "RMS\tlinear"
                colorscale = rms_color_scale
            elif pow_ind == 4 or pow_ind == 5:
                cbar_title = "Degrees"
            elif pow_ind == len(powers) - 1:
                cbar_title = "Median\tCoeff"
            else:
                cbar_title = "dB"

            if pow_ind == 0:
                visible = True
            else:
                visible = False

            for pol_ind, pol in enumerate(pols):
                for mask_cnt, mask in enumerate(masks):
                    if mask_cnt == pow_ind:
                        mask.extend([True] * 2)
                    else:
                        mask.extend([False] * 2)

                __power = power[pol_ind][host_index]
                ___text = __text[pol_ind][host_index]

                _power = {
                    "x": xs[pol_ind].data[~__power.mask].tolist(),
                    "y": ys[pol_ind].data[~__power.mask].tolist(),
                    "text": ___text[~__power.mask].tolist(),
                    "mode": "markers",
                    "visible": visible,
                    "marker": {
                        "color": __power.data[~__power.mask].tolist(),
                        "size": 14,
                        "cmin": vmin[pow_ind],
                        "cmax": vmax[pow_ind],
                        "colorscale": colorscale,
                        "colorbar": {"thickness": 20, "title": cbar_title},
                    },
                    "hovertemplate": "%{text}<extra></extra>",
                }

                data_node.append(_power)

                _power_offline = {
                    "x": xs[pol_ind].data[__power.mask].tolist(),
                    "y": ys[pol_ind].data[__power.mask].tolist(),
                    "text": ___text[__power.mask].tolist(),
                    "mode": "markers",
                    "visible": visible,
                    "marker": {
                        "color": "orange",
                        "size": 14,
                        "cmin": vmin[pow_ind],
                        "cmax": vmax[pow_ind],
                        "colorscale": colorscale,
                        "colorbar": {"thickness": 20, "title": cbar_title},
                    },
                    "hovertemplate": "%{text}<extra></extra>",
                }

                data_node.append(_power_offline)
    buttons = []
    for _name, mask in zip(names, masks):
        _button = {
            "args": [{"visible": mask}, {"title": "", "annotations": {}}],
            "label": _name,
            "method": "restyle",
        }
        buttons.append(_button)

    updatemenus_node = [{"buttons": buttons, "showactive": True, "type": "buttons"}]

    layout_node = {
        "xaxis": {
            "title": "Node Number",
            "dtick": 1,
            "tick0": 0,
            "showgrid": False,
            "zeroline": False,
        },
        "yaxis": {"showticklabels": False, "showgrid": False, "zeroline": False},
        "title": {"text": "Per Antpol Stats vs Node #", "font": {"size": 24}},
        "hoverlabel": {"align": "left"},
        "margin": {"t": 40},
        "autosize": True,
        "showlegend": False,
        "hovermode": "closest",
    }

    caption_node = {}
    caption_node["title"] = "Stats vs Node Help"
    caption_node["text"] = (
        "This plot shows various statistics and measurements "
        "per ant-pol versus the node number to which it is connected."
        "<br><br><h4>Available plotting options</h4>"
        "<ul>"
        "<li>Auto Corr - Median Auto Correlation (in db) "
        "from the correlator with equalization coefficients "
        "divided out</li>"
        "<li>Pam Power - Latest Pam Power (in db) recorded in M&C</li>"
        "<li>ADC Power - Latest ADC Power (in db) recorded in M&C</li>"
        "<li>ADC RMS - Latest linear ADC RMS recorded in M&C</li>"
        "<li>EQ Coeffs - Latest Median Equalization Coefficient recorded in M&C</li>"
        "</ul>"
        "Any antpol showing with an orange color means "
        "no data is avaible for the currenty plot selection."
        "<h4>Hover label Formatting</h4>"
        "<ul>"
        "<li>Antenna Name from M&C<br>(e.g. HH0n = Hera Hex Antenna 0 Polarization N)</li>"
        "<li>Snap hostname from M&C<br>(e.g. heraNode0Snap0)</li>"
        "<li>PAM Number</li>"
        "<li>Median Auto Correlation power in dB</li>"
        "<li>PAM power in dB</li>"
        "<li>ADC power in dB</li>"
        "<li>Linear ADC RMS</li>"
        "<li>Median Equalization Coefficient</li>"
        "<li>Time ago in hours the M&C Antenna Status was updated. "
        "This time stamp applies to all data for this antenna "
        "except the Auto Correlation.</li>"
        "</ul>"
        "In any hover label entry 'No Data' means "
        "information not currrently available in M&C."
    )

    # Render all the power vs ndde files
    plotname = "plotly-node"
    html_template = env.get_template("plotly_base.html")
    js_template = env.get_template("plotly_base.js")

    if sys.version_info.minor >= 8 and sys.version_info.major > 2:
        time_jd = latest.to_value('jd', subfmt='float')
        time_unix = latest.to_value('unix')
    else:
        time_jd = latest.jd
        time_unix = latest.unix

    basename = "node_amp"
    rendered_node_html = html_template.render(
        plotname=plotname,
        data_type="Auto correlations",
        plotstyle="height: 100%",
        gen_date=Time.now().iso,
        gen_time_unix_ms=Time.now().unix * 1000,
        data_date_iso=latest.iso,
        data_date_jd="{:.3f}".format(time_jd),
        data_date_unix_ms=time_unix * 1000,
        js_name=basename,
        scriptname=os.path.basename(__file__),
        hostname=computer_hostname,
        caption=caption_node,
    )

    rendered_node_js = js_template.render(
        json_name=basename,
        layout=layout_node,
        updatemenus=updatemenus_node,
        plotname=plotname,
    )

    with open("{}.json".format(basename), "w") as json_file:
        json.dump(data_node, json_file)

    with open("{}.html".format(basename), "w") as h_file:
        h_file.write(rendered_node_html)

    with open("{}.js".format(basename), "w") as js_file:
        js_file.write(rendered_node_js)


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
        # without item this will be an array which will break database queries
        latest = Time(
            np.frombuffer(redis_db.get("auto:timestamp"), dtype=np.float64).item(),
            format="jd",
        )
        latest.out_subfmt = u"date_hm"

        amps = {}
        keys = [
            k.decode()
            for k in redis_db.keys()
            if k.startswith(b"auto") and not k.endswith(b"timestamp")
        ]

        for key in keys:
            match = re.search(r"auto:(?P<ant>\d+)(?P<pol>e|n)", key)
            if match is not None:
                ant, pol = int(match.group("ant")), match.group("pol")
                d = redis_db.get(key)
                if d is not None:
                    # need to copy because frombuffer creates a read-only array
                    auto = np.frombuffer(d, dtype=np.float32).copy()

                    eq_coeff = redis_db.hget(
                        bytes("eq:ant:{ant}:{pol}".format(ant=ant, pol=pol).encode()),
                        "values",
                    )
                    if eq_coeff is not None:
                        eq_coeffs = np.fromstring(
                            eq_coeff.decode("utf-8").strip("[]"), sep=","
                        )
                        if eq_coeffs.size == 0:
                            eq_coeffs = np.ones_like(auto)
                    else:
                        eq_coeffs = np.ones_like(auto)

                    # divide out the equalization coefficients
                    # eq_coeffs are stored as a length 1024 array but only a
                    # single number is used. Taking the median to not deal with
                    # a size mismatch
                    eq_coeffs = np.median(eq_coeffs)
                    auto /= eq_coeffs ** 2
                    auto[auto < 10 ** -10.0] = 10 ** -10.0
                    auto = np.median(auto)
                    amps[(ant, pol)] = 10.0 * np.log10(auto)

        hsession = cm_sysutils.Handling(session)
        ants = np.unique([ant for (ant, pol) in amps.keys()])
        pols = np.unique([pol for (ant, pol) in amps.keys()])

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
            if station.antenna_number not in ants:
                ants = np.append(ants, station.antenna_number)
        ants = np.unique(ants)

        stations = []
        for station_type in hsession.geo.parse_station_types_to_check("default"):
            for stn in hsession.geo.station_types[station_type]["Stations"]:
                stations.append(stn)

        # stations is a list of HH??? numbers we just want the ints
        stations = list(map(int, [j[2:] for j in stations]))
        built_but_not_on = np.setdiff1d(stations, ants)
        # Get node and PAM info
        node_ind = np.zeros_like(ants, dtype=np.int)
        pam_ind = np.zeros_like(ants, dtype=np.int)
        # defaul the snap name to "No Data"
        hostname = np.full_like(ants, "No\tData", dtype=object)
        snap_serial = np.full_like(ants, "No\tData", dtype=object)

        pam_power = {}
        adc_power = {}
        adc_rms = {}
        time_array = {}
        fem_imu_theta = {}
        fem_imu_phi = {}
        eq_coeffs = {}
        for ant in ants:
            for pol in pols:
                amps.setdefault((ant, pol), np.Inf)
                pam_power.setdefault((ant, pol), np.Inf)
                adc_power.setdefault((ant, pol), np.Inf)
                adc_rms.setdefault((ant, pol), np.Inf)
                eq_coeffs.setdefault((ant, pol), np.Inf)
                fem_imu_theta.setdefault((ant, pol), np.Inf)
                fem_imu_phi.setdefault((ant, pol), np.Inf)
                time_array.setdefault((ant, pol), Time.now() - Time(0, format="gps"))

        for ant_cnt, ant in enumerate(ants):
            station_status = session.get_antenna_status(
                most_recent=True, antenna_number=int(ant)
            )

            for status in station_status:
                antpol = (status.antenna_number, status.antenna_feed_pol)
                if status.pam_power is not None:
                    pam_power[antpol] = status.pam_power
                if status.adc_power is not None:
                    adc_power[antpol] = 10 * np.log10(status.adc_power)
                if status.adc_rms is not None:
                    adc_rms[antpol] = status.adc_rms
                if status.time is not None:
                    time_array[antpol] = Time.now() - Time(status.time, format="gps")
                if status.fem_imu_phi is not None:
                    fem_imu_phi[antpol] = status.fem_imu_phi
                if status.fem_imu_theta is not None:
                    fem_imu_theta[antpol] = status.fem_imu_theta
                if status.eq_coeffs is not None:
                    _coeffs = np.fromstring(status.eq_coeffs.strip("[]"), sep=",")
                    # just track the median coefficient for now
                    eq_coeffs[antpol] = np.median(_coeffs)

            # Try to get the snap info. Output is a dictionary with 'e' and 'n' keys
            mc_name = antnames[ant]
            snap_info = hsession.get_part_at_station_from_type(mc_name, "now", "snap")
            # get the first key in the dict to index easier
            _key = list(snap_info.keys())[0]
            pol_key = [key for key in snap_info[_key].keys() if "E" in key]
            if pol_key:
                # 'E' should be in one of the keys, extract the 0th entry
                pol_key = pol_key[0]
            else:
                # a hacky solution for a key that should work
                pol_key = "E<ground"
            if snap_info[_key][pol_key] is not None:
                snap_serial[ant_cnt] = snap_info[_key][pol_key]

            # Try to get the pam info. Output is a dictionary with 'e' and 'n' keys
            pam_info = hsession.get_part_at_station_from_type(
                mc_name, "now", "post-amp"
            )
            # get the first key in the dict to index easier
            _key = list(pam_info.keys())[0]
            if pam_info[_key][pol_key] is not None:
                _pam_num = re.findall(r"PAM(\d+)", pam_info[_key][pol_key])[0]
                pam_ind[ant_cnt] = np.int(_pam_num)
            else:
                pam_ind[ant_cnt] = -1

            # Try to get the ADC info. Output is a dictionary with 'e' and 'n' keys
            node_info = hsession.get_part_at_station_from_type(mc_name, "now", "node")
            # get the first key in the dict to index easier
            _key = list(node_info.keys())[0]
            if node_info[_key][pol_key] is not None:
                _node_num = re.findall(r"N(\d+)", node_info[_key][pol_key])[0]
                node_ind[ant_cnt] = np.int(_node_num)

                _hostname = session.get_snap_hostname_from_serial(snap_serial[ant_cnt])

                if _hostname is not None:
                    hostname[ant_cnt] = _hostname
                else:
                    snap_status = session.get_snap_status(
                        most_recent=True, nodeID=np.int(_node_num)
                    )
                    for _status in snap_status:
                        if _status.serial_number == snap_serial[ant_cnt]:
                            hostname[ant_cnt] = _status.hostname
            else:
                node_ind[ant_cnt] = -1

        pams, _pam_ind = np.unique(pam_ind, return_inverse=True)
        nodes, _node_ind = np.unique(node_ind, return_inverse=True)

        xs_offline = np.ma.masked_array(
            antpos[0, :],
            mask=[True if int(name[2:]) in ants else False for name in antnames],
        )
        ys_offline = np.ma.masked_array(antpos[1, :], mask=xs_offline.mask)
        name_offline = np.ma.masked_array(
            [aname + "<br>OFFLINE" for aname in antnames],
            mask=xs_offline.mask,
            dtype=object,
        )
        xs_offline = xs_offline

        names = [
            "Auto  [dB]",
            "PAM [dB]",
            "ADC [dB]",
            "ADC RMS",
            "FEM IMU THETA",
            "FEM IMU PHI",
            "EQ COEF",
        ]
        powers = [
            amps,
            pam_power,
            adc_power,
            adc_rms,
            fem_imu_theta,
            fem_imu_phi,
            eq_coeffs,
        ]
        powers = [
            np.ma.masked_invalid([[p[ant, pol] for ant in ants] for pol in pols])
            for p in powers
        ]

        time_array = np.array(
            [[time_array[ant, pol].to("hour").value for ant in ants] for pol in pols]
        )
        xs = np.ma.masked_array(antpos[0, ants], mask=powers[0][0].mask)
        ys = np.ma.masked_array(
            [antpos[1, ants] + 3 * (pol_cnt - 0.5) for pol_cnt, pol in enumerate(pols)],
            mask=powers[0].mask,
        )

        _text = np.array(
            [
                [
                    antnames[ant]
                    + pol
                    + "<br>"
                    + str(hostname[ant_cnt])
                    + "<br>"
                    + "PAM\t#:\t"
                    + str(pam_ind[ant_cnt])
                    for ant_cnt, ant in enumerate(ants)
                ]
                for pol_cnt, pol in enumerate(pols)
            ],
            dtype="object",
        )

        #  want to format No Data where data was not retrieved for each type of power
        for pol_cnt, pol in enumerate(pols):
            for ant_cnt, ant in enumerate(ants):
                for _name, _power in zip(names, powers):
                    if not _power.mask[pol_cnt, ant_cnt]:
                        _text[pol_cnt, ant_cnt] += (
                            "<br>"
                            + _name
                            + ": {0:.2f}".format(_power[pol_cnt, ant_cnt])
                        )
                    else:
                        _text[pol_cnt, ant_cnt] += "<br>" + _name + ": No Data"
                if time_array[pol_cnt, ant_cnt] > 2 * 24 * 365:
                    # if the value is older than 2 years it is bad
                    # value are stored in hours.
                    # 2 was chosen arbitraritly.
                    _text[pol_cnt, ant_cnt] += "<br>" + "Ant Status:  No Date"
                else:
                    _text[pol_cnt, ant_cnt] += (
                        "<br>"
                        + "Ant Status: {0:.2f} hrs old".format(
                            time_array[pol_cnt, ant_cnt]
                        )
                    )
                # having spaces will cause odd wrapping issues, replace all
                # spaces by \t
                _text[pol_cnt, ant_cnt] = _text[pol_cnt, ant_cnt].replace(" ", "\t")

    runInParallel(
        [
            make_hex,
            [
                powers,
                xs_offline,
                ys_offline,
                name_offline,
                built_but_not_on,
                xs,
                ys,
                nodes,
                node_ind,
                _text,
                env,
                latest,
                pols,
                computer_hostname,
                names
            ]
        ],
        [
            make_node,
            [
                powers,
                _text,
                names,
                hostname,
                nodes,
                node_ind,
                pols,
                env,
                latest,
                computer_hostname,
            ]
        ],
        [
            write_csv,
            [
                "ant_stats.csv",
                antnames,
                ants,
                pols,
                names,
                powers,
                built_but_not_on
            ],
        ],
    )




if __name__ == "__main__":
    main()
