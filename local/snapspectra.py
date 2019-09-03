#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Antenna amplitudes."""

from __future__ import absolute_import, division, print_function

import numpy as np
import redis
from hera_mc import mc, cm_sysutils
from astropy.time import Time
import hera_corr_cm


HTML_HEADER = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HERA Compute Dashboard</title>
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap-theme.min.css">
  <!--[if lt IE 9]>
    <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
    <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
  <![endif]-->
</head>
"""

JS_HEADER = """\
var report_age = 0.001 * (Date.now() - {gen_time_unix_ms});
var age_text = "?";
if (report_age < 300) {{
  age_text = report_age.toFixed(0) + " seconds";
}} else if (report_age < 10800) {{ // 3 hours
  age_text = (report_age / 60).toFixed(0) + " minutes";
}} else if (report_age < 172800) {{ // 48 hours
  age_text = (report_age / 3600).toFixed(0) + " hours";
}} else {{
  age_text = (report_age / 86400).toFixed(1) + " days";
}}
document.getElementById("age").textContent = age_text;
if (report_age > 1800) {{
    document.getElementById("age").style.color = 'red';
}}
"""

HTML_FOOTER = """\
<div class="row">
<div class="col-md-12">
<p class="text-center"><a href="https://github.com/HERA-Team/simple-dashboard">Source code</a></p>
</div>
</div>
</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="snapspectra.js"></script>
</body>
</html>
"""


def main():
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

    with db.sessionmaker() as session, \
            open('snapspectra.html', 'wt') as html_file, \
            open('snapspectra.js', 'wt') as js_file:

        def emit_html(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=html_file, end=end)

        def emit_js(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=js_file, end=end)

        Emitter(session, redis_db, args.redishost,
                emit_html, emit_js).emit()


class Emitter(object):

    def __init__(self, session, redis_db, redishost,
                 emit_html, emit_js):
        self.session = session
        self.corr_cm = hera_corr_cm.HeraCorrCM(redishost=redishost)
        self.redis_db = redis_db

        self.emit_html = emit_html
        self.emit_js = emit_js
        self.latest = Time(np.frombuffer(self.redis_db.get('auto:timestamp'),
                           dtype=np.float64).item(), format='jd')

        self.now = Time.now()

    def emit_data_array(self, data, fmt):
        self.emit_js('[', end='')
        first = True

        for x in data:
            if first:
                first = False
            else:
                self.emit_js(',', end='')
            self.emit_js(fmt, x=x, end='')

        self.emit_js(']', end='')

    def emit_text_array(self, data, fmt):
        self.emit_js('[', end='')
        first = True

        for x in data:
            if first:
                first = False
            else:
                self.emit_js(',', end='')
            self.emit_js("'" + fmt + "'", x=x, end='')

        self.emit_js(']', end='')

    def prep_data(self):
        hsession = cm_sysutils.Handling(self.session)
        stations = hsession.get_all_fully_connected_at_date(at_date='now')

        ants = []
        for station in stations:
            if station.antenna_number not in ants:
                ants = np.append(ants, station.antenna_number)
        ants = np.unique(ants).astype(int)

        hostname_lookup = {}
        snap_serial = {}
        ant_loc_num = {}

        all_snap_statuses = self.session.get_snap_status(most_recent=True)

        hostnames = []
        hostnames = [stat.hostname for stat in all_snap_statuses
                     if stat.hostname not in hostnames]

        autos = {}

        ant_status_from_snaps = self.corr_cm.get_ant_status()

        for ant_cnt, ant in enumerate(ants):
            mc_ant_status = self.session.get_antenna_status(antenna_number=int(ant),
                                                            most_recent=True)
            for stat in mc_ant_status:
                name = "{ant:d}:{pol}".format(ant=stat.antenna_number,
                                              pol=stat.antenna_feed_pol)
                try:
                    tmp_auto = ant_status_from_snaps[name]["autocorrelation"]

                    autos[name] = 10 * np.log10(np.real(tmp_auto))
                except KeyError:
                    print("Ant-pol with no autocorrelation", name)
                    raise
            # Try to get the snap info. Output is a dictionary with 'e' and 'n' keys
            # connect to M&C to find all the hooked up Snap hostnames and corresponding ant-pols
            mc_name = 'HH{:d}'.format(ant)
            snap_info = hsession.get_part_at_station_from_type(mc_name,
                                                               'now', 'snap')

            for _key in snap_info.keys():
                # initialize a dict if they key does not exist already
                snap_serial.setdefault(int(ant), {})
                ant_loc_num.setdefault(int(ant), {})

                for pol_key in snap_info[_key].keys():
                    if snap_info[_key][pol_key] is not None:
                        snap_serial[ant][pol_key] = snap_info[_key][pol_key]

                        name = "{ant:d}:{pol}".format(ant=ant,
                                                      pol=pol_key)

                        for _stat in all_snap_statuses:
                            if _stat.serial_number == snap_serial[ant][pol_key]:
                                ant_loc_num[ant][pol_key] = _stat.snap_loc_num

                                # if this hostname is not in the lookup table yet
                                # initialize an empty dict
                                grp1 = hostname_lookup.setdefault(_stat.hostname, {})
                                # if this loc num is not in lookup table initialize
                                # empty list
                                grp2 = grp1.setdefault(_stat.snap_loc_num, [])
                                grp2.append(name)

        self.emit_js("var data = [")
        # create a mask to make things visibile for only that hostname
        # the mask is different for each host, but each mask is the total
        # length of all data, 8 because loc_nums go 0-3 each with 'e' and 'n' pols
        host_masks = np.full((len(hostnames), len(hostnames) * 8), 'false',
                             dtype=np.str_)
        host_title = np.zeros((len(hostnames)), dtype='object')

        # Generate frequency axis
        # this is taken directly from autospectra.py
        NCHANS = int(2048 // 4 * 2)
        NCHANS_F = 8192
        NCHAN_SUM = 6
        frange = np.linspace(0, 250e6, NCHANS_F + 1)[1536:1536 + (8192 // 4 * 3)]
        # average over channels
        freqs = frange.reshape(NCHANS, NCHAN_SUM).sum(axis=1) / NCHAN_SUM

        for host_cnt, host in enumerate(hostname_lookup.keys()):
            mask_cnt = host_cnt * 8
            if host_cnt == 0:
                visible = 'true'
            else:
                visible = 'false'

            # host_title[host_cnt] = '{} Integration over {} seconds'.format(host, length)

            for loc_num in hostname_lookup[host].keys():
                for ant_cnt, ant_name in enumerate(hostname_lookup[host][loc_num]):
                    # this 8 and 2 business is because the mask is raveled
                    # and needs to account for the 8 different feed pols connected to each snap
                    # the loc_num helps to track the antenna
                    host_masks[host_cnt, mask_cnt] = 'true'
                    mask_cnt += 1

                    name = 'ant{}'.format(ant_name.replace(":", ""))

                    self.emit_js('{{x: ', end='')
                    self.emit_data_array(freqs, '{x:.3f}')
                    self.emit_js(',\ny: ', end='')
                    self.emit_data_array(autos[ant_name], '{x:.3f}')
                    self.emit_js(",\nvisibile: {visible}", visible=visible, end='')
                    self.emit_js(",\nhovertemplate: '%{{x:.3f}}<extra>{name}</extra>'", name=name, end='')
                    self.emit_js("}}, ", end='\n')
        # end data var
        self.emit_js(']', end='\n')

        self.emit_js(' var updatemenus=[')
        self.emit_js('{{buttons: [')
        for host_cnt, host in enumerate(hostnames):
            self.emit_js('{{')
            self.emit_js('args: [')
            self.emit_js("{{'visibile': ", end='')
            self.emit_data_array(host_masks[host_cnt], 'x')
            self.emit_js("}},\n{{'title': {title},", title=host_title[host_cnt])
            self.emit_js("'annotations': {{}} }}")
            self.emit_js('],')
            self.emit_js("label: {host},", host=host)
            self.emit_js("method: 'restyle'")
            self.emit_js('}},')
        self.emit_js(']', end='\n')
        self.emit_js('showactive: true,')
        self.emit_js('}},')
        self.emit_js(']', end='\n')

        self.emit_js("""
var layout = {{
    xaxis: {{title: 'Frequency [MHz]'}},
    yaxis: {{title: 'Power [dBm]'}},
    "hoverlabel": {{"align": "left"}},
    margin: {{ l: 40, b: 0, r: 40, t: 30}},
    autosize: true,
    hovermode: 'closest'
}};

Plotly.plot("plotly-snap", data, layout, {{responsive: true}});
                """)

    def emit(self):
        self.emit_html(HTML_HEADER)

        self.emit_html("""\
<body>
<div class="container">
  <div class="row">
    <div id="plotly-snap" class="col-md-12", style="height: 85vh"></div>
  </div>
  <div class="row">
    <div class="col-md-12">
        <p class="text-center">Report generated <span id="age">???</span> ago (at {gen_date} UTC)</p>
    </div>
    <div class="col-md-12">
        <p class="text-center">Auto correlations observed on {iso_date} (JD: {jd_date:.6f})</p>
    </div>
  </div>
""", gen_date=self.now.iso,
     iso_date=self.latest.iso,
     jd_date=self.latest.jd)

        self.emit_js(JS_HEADER,
                     gen_time_unix_ms=self.now.unix * 1000,
                     )

        self.prep_data()

        self.emit_html(HTML_FOOTER)


if __name__ == '__main__':
    main()
