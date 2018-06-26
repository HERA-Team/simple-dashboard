#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2018 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the on-site computers."""

from __future__ import absolute_import, division, print_function

from astropy.time import Time, TimeDelta
from cgi import escape
from hera_mc import mc
from hera_mc.librarian import LibServerStatus
from hera_mc.rtp import RTPServerStatus


def main():
    parser = mc.get_mc_argument_parser()
    args = parser.parse_args()

    try:
        db = mc.connect_to_mc_db(args)
    except RuntimeError as e:
        raise SystemExit(str(e))

    with db.sessionmaker() as session, \
         open('compute.html', 'wt') as html_file, \
         open('compute.js', 'wt') as js_file:
        def emit_html(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=html_file, end=end)
        def emit_js(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=js_file, end=end)

        Emitter(session, emit_html, emit_js).emit()


HTML_HEADER="""\
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

function extract(data, keyname) {{
  var items = [];
  for (var h in data) {{
    items.push({{x: data[h].t, y: data[h][keyname], name: h, type: "scatter"}});
  }}
  return items;
}}

layout = {{
    xaxis: {{{time_axis_range}}},
    yaxis: {{title: 'placeholder', rangemode: 'tozero'}},
    height: 200,
    margin: {{t: 2, r: 10, b: 2, l: 40}},
    legend: {{orientation: 'h', x: 0.15, y: -0.15}},
    showlegend: true,
    hovermode: 'closest'
}};\
"""

LIB_HOSTNAMES = [
    'qmaster',
    'pot1',
    'pot6.karoo.kat.ac.za',
    'pot7.rtp.pvt',
    'pot7.still.pvt',
    'pot8.rtp.pvt',
    'pot8.still.pvt',
]
RTP_HOSTNAMES = [
    'bigmem1.rtp.pvt',
    'bigmem2.rtp.pvt',
    'cask0.rtp.pvt',
    'cask1.rtp.pvt',
    'gpu1.rtp.pvt',
    'gpu2.rtp.pvt',
    'gpu3.rtp.pvt',
    'gpu4.rtp.pvt',
    'gpu5.rtp.pvt',
    'gpu6.rtp.pvt',
    'gpu7.rtp.pvt',
    'gpu8.rtp.pvt',
    'per510-1.rtp.pvt',
    'per510-2.rtp.pvt',
    'per715-1.rtp.pvt',
    'per715-2.rtp.pvt',
    'per715-3.rtp.pvt',
    'per715-4.rtp.pvt',
    'snb2.rtp.pvt',
    'snb4.rtp.pvt',
    'snb5.rtp.pvt',
    'snb6.rtp.pvt',
    'snb7.rtp.pvt',
    'snb8.rtp.pvt',
    'snb9.rtp.pvt',
    'snb10.rtp.pvt',
    'still1.rtp.pvt',
    'still2.rtp.pvt',
    'still3.rtp.pvt',
    'still4.rtp.pvt',
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


class Emitter(object):
    TIME_WINDOW = 14 # days

    def __init__(self, session, emit_html, emit_js):
        self.session = session
        self.emit_html = emit_html
        self.emit_js = emit_js

        self.now = Time.now()
        self.cutoff = self.now - TimeDelta(self.TIME_WINDOW, format='jd')
        self.cutoff_gps = self.cutoff.gps
        self.time_axis_range = 'range: ["{}", "{}"]'.format(self.cutoff.iso, self.now.iso)


    def emit(self):
        self.emit_html(HTML_HEADER)

        self.emit_html("""\
<body>
<div class="container">
  <div class="row">
    <div class="col-md-12">
        <p class="text-center">Report generated <span id="age">???</span> ago (at {gen_date} UTC)</p>
    </div>
  </div>
  <div class="row">
    <div id="lib-load" class="col-md-6"></div>
    <div id="rtp-load" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="lib-disk" class="col-md-6"></div>
    <div id="rtp-disk" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="lib-mem" class="col-md-6"></div>
    <div id="rtp-mem" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="lib-bandwidth" class="col-md-6"></div>
    <div id="rtp-bandwidth" class="col-md-6"></div>
  </div>
  <div class="row">
    <div id="lib-timediff" class="col-md-6"></div>
    <div id="rtp-timediff" class="col-md-6"></div>
  </div>
""", gen_date = self.now.iso)

        self.emit_js(JS_HEADER,
                     gen_time_unix_ms = self.now.unix * 1000,
                     time_axis_range = self.time_axis_range,
        )

        self.do_status(LibServerStatus, LIB_HOSTNAMES, 'lib')
        self.do_status(RTPServerStatus, RTP_HOSTNAMES, 'rtp')

        self.emit_html("""\
  <div class="row">
    <div class="col-md-12">
        <p class="text-center"><a href="https://github.com/HERA-Team/simple-dashboard">Source code</a>.</p>
    </div>
  </div>
</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="compute.js"></script>
</body>
</html>
""")


    def do_status(self, tablecls, hostnames, div_prefix):
        sep = ''
        self.emit_js('data = {{')

        for host in hostnames:
            data = (self.session.query(tablecls)
                    .filter(tablecls.hostname == host)
                    .filter(tablecls.mc_time > self.cutoff_gps)
                    .order_by(tablecls.mc_time)
                    .all())

            self.emit_js('{sep}"{host}": {{t:', host=UI_HOSTNAMES.get(host, host), sep=sep, end='')
            self.emit_gpstime_array(rec.mc_time for rec in data)
            self.emit_js(',load:', end='')
            self.emit_data_array((rec.cpu_load_pct for rec in data), '{x:.1f}')
            self.emit_js(',timediff:', end='')
            self.emit_data_array((rec.mc_system_timediff for rec in data), '{x:.3f}')
            self.emit_js(',mem:', end='')
            self.emit_data_array((rec.memory_used_pct for rec in data), '{x:.1f}')
            self.emit_js(',disk:', end='')
            self.emit_data_array((rec.disk_space_pct for rec in data), '{x:.1f}')
            self.emit_js(',net:', end='')
            self.emit_data_array((rec.network_bandwidth_mbs for rec in data), '{x:.2f}')
            self.emit_js('}}')
            sep = ','

        self.emit_js("""\
}};

layout.yaxis.title = 'Load % per CPU';
Plotly.plot('{div_prefix}-load', {{data: extract(data, 'load'), layout: layout}});
layout.yaxis.title = 'Local disk usage (%)';
Plotly.plot('{div_prefix}-disk', {{data: extract(data, 'disk'), layout: layout}});
layout.yaxis.title = 'Memory usage (%)';
Plotly.plot('{div_prefix}-mem', {{data: extract(data, 'mem'), layout: layout}});
layout.yaxis.title = 'Network I/O (MB/s)';
Plotly.plot('{div_prefix}-bandwidth', {{data: extract(data, 'net'), layout: layout}});
layout.yaxis.title = 'M&C time diff. (s)';
Plotly.plot('{div_prefix}-timediff', {{data: extract(data, 'timediff'), layout: layout}});\
""", div_prefix=div_prefix)


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


    def emit_gpstime_array(self, data):
        self.emit_js('[', end='')
        first = True

        for t in data:
            if first:
                first = False
            else:
                self.emit_js(',', end='')
            self.emit_js('"{x}"', x=Time(t, format='gps').iso, end='')

        self.emit_js(']', end='')


if __name__ == '__main__':
    main()
