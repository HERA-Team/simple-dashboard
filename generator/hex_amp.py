#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for the Antenna amplitudes."""

from __future__ import absolute_import, division, print_function

import os
import numpy as np
import re
import redis
from hera_mc import mc, cm_sysutils
from astropy.time import Time


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


def main():
    parser = mc.get_mc_argument_parser()
    args = parser.parse_args()

    try:
        db = mc.connect_to_mc_db(args)
        args.mc_db_name = 'hera_mc'
        db2 = mc.connect_to_mc_db(args)
    except RuntimeError as e:
        raise SystemExit(str(e))

    try:
        redis_db = redis.Redis('localhost', port=9932)
        redis_db.keys()
    except ConnectionError as err:
        raise SystemExit(str(err))

    with db.sessionmaker() as session, \
         db2.sessionmaker() as session2, \
         open('hex_amp.html', 'wt') as html_file, \
         open('hex_amp.js', 'wt') as js_file:

        def emit_html(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=html_file, end=end)

        def emit_js(f, end='\n', **kwargs):
            print(f.format(**kwargs), file=js_file, end=end)

        Emitter(session, session2, redis_db, emit_html, emit_js).emit()


class Emitter(object):

    def __init__(self, session, session2, redis_db, emit_html, emit_js):
        self.session = session
        self.session2 = session2
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
        autos = {}
        autos_raw = {}
        amps = {}
        keys = [k.decode() for k in self.redis_db.keys()
                if k.startswith(b'auto') and not k.endswith(b'timestamp')]
        # without item this will be an array which will break database queries
        timestamp = np.frombuffer(self.redis_db.get('auto:timestamp'),
                                  dtype=np.float64).item()
        latest = Time(timestamp, format='jd')
        for key in keys:
            match = re.search(r'auto:(?P<ant>\d+)(?P<pol>e|n)', key)
            if match is not None:
                ant, pol = int(match.group('ant')), match.group('pol')

                autos_raw[(ant, pol)] = np.frombuffer(self.redis_db.get(key),
                                                      dtype=np.float32)
                autos[(ant, pol)] = 10.0 * np.log10(autos_raw[(ant, pol)])

                tmp_amp = np.median(autos_raw[(ant, pol)])
                amps[(ant, pol)] = 10.0 * np.log10(tmp_amp)

        hsession = cm_sysutils.Handling(self.session)
        # stations_conn = hsession.get_all_fully_connected_at_date(at_date=latest)
        ants = np.unique([ant for (ant, pol) in autos.keys()])
        pols = np.unique([pol for (ant, pol) in autos.keys()])

        antpos = np.genfromtxt(os.path.join(mc.data_path, "HERA_350.txt"),
                               usecols=(0, 1, 2, 3),
                               dtype={'names': ('ANTNAME', 'EAST', 'NORTH', 'UP'),
                                      'formats': ('<U5', '<f8', '<f8', '<f8')},
                               encoding=None)
        antnames = antpos['ANTNAME']
        antpos = np.array([antpos['EAST'],
                           antpos['NORTH'],
                           antpos['UP']])
        array_center = np.mean(antpos, axis=1, keepdims=True)
        antpos -= array_center

        stations = hsession.get_all_fully_connected_at_date(at_date=latest)

        for station in stations:
            if station.antenna_number not in ants:
                np.append(ants, station.antenna_number)
        ants = np.unique(ants)

        # Get node and PAM info
        node_ind = np.zeros_like(ants, dtype=np.int)
        pam_ind = np.zeros_like(ants, dtype=np.int)
        pam_power = {}
        adc_power = {}

        for ant in ants:
            for pol in pols:
                amps.setdefault((ant, pol), np.Inf)
                pam_power.setdefault((ant, pol), np.Inf)
                adc_power.setdefault((ant, pol), np.Inf)

        for ant_cnt, ant in enumerate(ants):
            station_status = self.session2.get_antenna_status(starttime=latest,
                                                              stoptime=latest,
                                                              antenna_number=int(ant))
            for status in station_status:
                pam_power[(status.antenna_number, status.antenna_feed_pol)] = status.pam_power
                adc_power[(status.antenna_number, status.antenna_feed_pol)] = status.adc_power

            pam_info = hsession.get_part_at_station_from_type('HH{:d}'.format(ant), latest, 'post-amp')
            if pam_info[list(pam_info.keys())[0]]['e'] is not None:
                _pam_num = re.findall(r'PAM(\d+)', pam_info[list(pam_info.keys())[0]]['e'])[0]
                pam_ind[ant_cnt] = np.int(_pam_num)
            else:
                pam_ind[ant_cnt] = -1

            node_info = hsession.get_part_at_station_from_type('HH{:d}'.format(ant), latest, 'node')
            if node_info[list(node_info.keys())[0]]['e'] is not None:
                _node_num = re.findall(r'N(\d+)', node_info[list(node_info.keys())[0]]['e'])[0]
                node_ind[ant_cnt] = np.int(_node_num)
            else:
                node_ind[ant_cnt] = -1

        pams, _pam_ind = np.unique(pam_ind, return_inverse=True)
        nodes, _node_ind = np.unique(node_ind, return_inverse=True)

        xs_offline = np.ma.masked_array(antpos[0, :],
                                        mask=[True if int(name[2:]) in ants
                                              else False for name in antnames])
        ys_offline = np.ma.masked_array(antpos[1, :],
                                        mask=xs_offline.mask).compressed()
        name_offline = np.ma.masked_array(antnames,
                                          mask=xs_offline.mask).compressed()
        xs_offline = xs_offline.compressed()

        ant_index = np.array([np.argwhere('HH{:d}'.format(ant) == antnames)
                              for ant in ants]).squeeze()

        _amps = np.ma.masked_invalid([[amps[ant, pol] if ant is not None else np.Inf
                                       for ant_cnt, ant in enumerate(ants)] for pol in pols])
        _adc_power = np.ma.masked_invalid([[adc_power[ant, pol] if adc_power[ant, pol] is not None else np.Inf
                                            for ant_cnt, ant in enumerate(ants)] for pol in pols])
        _pam_power = np.ma.masked_invalid([[pam_power[ant, pol] if pam_power[ant, pol] is not None else np.Inf
                                            for ant_cnt, ant in enumerate(ants)] for pol in pols])
        xs = np.ma.masked_array(antpos[0, ant_index], mask=_amps[0].mask)
        ys = np.ma.masked_array([antpos[1, ant_index] + 3 * (pol_cnt - .5)
                                 for pol_cnt, pol in enumerate(pols)],
                                mask=_amps.mask)
        _text = np.ma.masked_array([[antnames[ant_index[ant_cnt]] + pol
                                     + '<br>' + 'PAM: ' + str(pam_ind[ant_cnt])
                                     + '<br>' + 'Node:' + str(node_ind[ant_cnt])
                                     for ant_cnt, ant in enumerate(ants)]
                                   for pol in pols], mask=_amps.mask)

        sep = ''
        self.emit_js('var data = [')

        amp_mask = ['true']
        pam_mask = ['true']
        adc_mask = ['true']
        # Offline antennas
        self.emit_js('{{x: ', end='')
        self.emit_data_array(xs_offline, '{x:.3f}')
        self.emit_js(',\ny :', end='')
        self.emit_data_array(ys_offline, '{x:.3f}')
        self.emit_js(',\ntext:', end='')
        self.emit_text_array(name_offline, '{x}')
        self.emit_js(",\nmode: 'markers'", end='')
        self.emit_js(",\nvisible: true", end='')
        self.emit_js(",\nmarker: {{color: 'black', size : 14,", end='')
        self.emit_js("opacity: .5, symbol: 'hexagon' }}", end='')
        self.emit_js(",\nhovertemplate: '%{{text}}<br>OFFLINE<extra></extra>' ", end='')
        self.emit_js('}},', end='\n')

        #  for each type of power, loop over pols and print out the data
        #  save up a mask array used for the buttons later
        #  also plot the bad ones!
        colorscale = "Viridis"
        for pow_ind, power in enumerate([_amps, _pam_power, _adc_power]):
            if pow_ind == 0:
                self.emit_js("// AMPLITUDE DATA ")
            elif pow_ind == 1:
                self.emit_js("// PAM DATA ")
            else:
                self.emit_js("// ADC DATA ")

            vmax = np.max(power.compressed())
            vmin = np.min(power.compressed())
            for pol_ind, pol in enumerate(pols):
                if pow_ind == 0:
                    amp_mask.extend(['true'] * 2)
                    pam_mask.extend(['false'] * 2)
                    adc_mask.extend(['false'] * 2)
                    visible = 'true'

                elif pow_ind == 1:
                    amp_mask.extend(['false'] * 2)
                    pam_mask.extend(['true'] * 2)
                    adc_mask.extend(['false'] * 2)
                    visible = 'false'
                else:
                    amp_mask.extend(['false'] * 2)
                    pam_mask.extend(['false'] * 2)
                    adc_mask.extend(['true'] * 2)
                    visible = 'false'

                self.emit_js('{{x: ', end='')
                self.emit_data_array(xs.data[~power[pol_ind].mask], '{x:.3f}')
                self.emit_js(',\ny: ', end='')
                self.emit_data_array(ys[pol_ind].data[~power[pol_ind].mask], '{x:.3f}')
                self.emit_js(",\nmode: 'markers'", end='')
                self.emit_js(",\nvisible: {visible}", visible=visible, end='')
                self.emit_js(",\ntext: ", end='')
                self.emit_text_array(_text[pol_ind].data[~power[pol_ind].mask], '{x}')
                self.emit_js(',\n marker: {{  color:', end='')
                self.emit_data_array(power[pol_ind].data[~power[pol_ind].mask], '{x:.3f}')
                self.emit_js(", cmin: {vmin}, cmax: {vmax}, ", vmin=vmin, vmax=vmax, end='')
                self.emit_js("colorscale: '{colorscale}', size: 14,", colorscale=colorscale, end='')
                self.emit_js("\ncolorbar: {{thickness: 20, title: 'dB'}}", end='')
                self.emit_js("}},\nhovertemplate: '%{{text}}<br>", end='')
                self.emit_js("Amp [dB]: %{{marker.color:.3f}}<extra></extra>'", end='')
                self.emit_js('}},', end='\n')

                self.emit_js('{{x: ', end='')
                self.emit_data_array(xs.data[power[pol_ind].mask], '{x:.3f}')
                self.emit_js(',\ny: ', end='')
                self.emit_data_array(ys[pol_ind].data[power[pol_ind].mask], '{x:.3f}')
                self.emit_js(",\nmode: 'markers'", end='')
                self.emit_js(",\nvisible: {visible}", visible=visible, end='')
                self.emit_js(",\ntext: ", end='')
                self.emit_text_array(_text[pol_ind].data[power[pol_ind].mask], '{x}')
                self.emit_js(",\n marker: {{  color: 'orange'", end='')
                self.emit_js(", size: 14", end='')
                self.emit_js("}},\nhovertemplate: '%{{text}}<br>", end='')
                self.emit_js("Amp [dB]: NO DATA AVAILABLE<extra></extra>'", end='')
                self.emit_js('}},\n', end='\n')

        self.emit_js(']', end='\n')

        self.emit_js(' var updatemenus=[')
        self.emit_js('{{buttons : [')

        # Amplitude Button
        self.emit_js('{{')
        self.emit_js('args: [')
        self.emit_js("{{'visible': ", end='')
        self.emit_data_array(amp_mask, '{x}')
        self.emit_js("}},\n{{'title': 'Median Auto Power',")
        self.emit_js("'annotations': {{}} }}")
        self.emit_js('],')
        self.emit_js("label: 'Auto Corr',")
        self.emit_js("method: 'update'")
        self.emit_js('}},')

        # PAMS buttons
        self.emit_js('{{')
        self.emit_js('args: [')
        self.emit_js("{{'visible': ", end='')
        self.emit_data_array(pam_mask, '{x}')
        self.emit_js("}},\n{{'title': 'PAM Power',")
        self.emit_js("'annotations': {{}} }}")
        self.emit_js('],')
        self.emit_js("label: 'Pam Power',")
        self.emit_js("method: 'update'")
        self.emit_js('}},')

        # ADC buttons
        self.emit_js('{{')
        self.emit_js('args: [')
        self.emit_js("{{'visible': ", end='')
        self.emit_data_array(adc_mask, '{x}')
        self.emit_js("}},\n{{'title': 'ADC Power',")
        self.emit_js("'annotations': {{}} }}")
        self.emit_js('],')
        self.emit_js("label: 'ADC Power',")
        self.emit_js("method: 'update'")
        self.emit_js('}},')

        self.emit_js('],', end='\n')
        self.emit_js('showactive: true,')
        self.emit_js("type: 'buttons',")
        self.emit_js('}},')
        self.emit_js(']', end='\n')

        self.emit_js("""

var layout = {{
    title: 'Median Auto Amplitude',
    xaxis: {{title: 'East-Westh Position [m]'}},
    yaxis: {{title: 'North-South Position [m]'}},
    autosize: true,
    showlegend: false,
    updatemenus: updatemenus,
    hovermode: 'closest'
}};

Plotly.plot("plotly-div", data, layout, {{responsive: true}});
window.onresize = function() {{
// Plotly.relayout("plotly-div", {{
//                    width: 0.7 * window.innerWidth,
//                    height: 0.8 * window.innerHeight
//                          }})
 }}
        """)

        self.emit_js("var data2 = [")
        amp_mask = []
        pam_mask = []
        adc_mask = []
        for node in nodes:
            node_index = np.where(node_ind == node)[0]

            ys = np.ma.masked_array([np.arange(node_index.size) + .3 * pol_cnt
                                     for pol_cnt, pol in enumerate(pols)], mask=_amps[:, node_index].mask)
            xs = np.zeros_like(ys)
            xs[:] = node
            __amps = _amps[:, node_index]
            __adc = _adc_power[:, node_index]
            __pam = _pam_power[:, node_index]
            for pow_ind, power in enumerate([__amps, __adc, __pam]):
                vmax = np.max(power.compressed())
                vmin = np.min(power.compressed())
                for pol_ind, pol in enumerate(pols):
                    if pow_ind == 0:
                        amp_mask.extend(['true'] * 2)
                        pam_mask.extend(['false'] * 2)
                        adc_mask.extend(['false'] * 2)
                        visible = 'true'
                        self.emit_js("// AMPLITUDE DATA ")

                    elif pow_ind == 1:
                        amp_mask.extend(['false'] * 2)
                        pam_mask.extend(['true'] * 2)
                        adc_mask.extend(['false'] * 2)
                        visible = 'false'
                        self.emit_js("// PAM DATA ")
                    else:
                        amp_mask.extend(['false'] * 2)
                        pam_mask.extend(['false'] * 2)
                        adc_mask.extend(['true'] * 2)
                        visible = 'false'
                        self.emit_js("// ADC DATA ")

                    self.emit_js('{{x: ', end='')
                    self.emit_data_array(xs[pol_ind].data[~power[pol_ind].mask], '{x:.3f}')
                    self.emit_js(',\ny: ', end='')
                    self.emit_data_array(ys[pol_ind].data[~power[pol_ind].mask], '{x:.3f}')
                    self.emit_js(",\nmode: 'markers'", end='')
                    self.emit_js(",\nvisible: {visible}", visible=visible, end='')
                    self.emit_js(",\ntext: ", end='')
                    self.emit_text_array(_text[pol_ind].data[~power[pol_ind].mask], '{x}')
                    self.emit_js(',\n marker: {{  color:', end='')
                    self.emit_data_array(power[pol_ind].data[~power[pol_ind].mask], '{x:.3f}')
                    self.emit_js(", cmin: {vmin}, cmax: {vmax}, ", vmin=vmin, vmax=vmax, end='')
                    self.emit_js("colorscale: '{colorscale}', size: 14,", colorscale=colorscale, end='')
                    self.emit_js("\ncolorbar: {{thickness: 20, title: 'dB'}}", end='')
                    self.emit_js("}},\nhovertemplate: '%{{text}}<br>", end='')
                    self.emit_js("Amp [dB]: %{{marker.color:.3f}}<extra></extra>'", end='')
                    self.emit_js('}},', end='\n')

                    self.emit_js('{{x: ', end='')
                    self.emit_data_array(xs[pol_ind].data[power[pol_ind].mask], '{x:.3f}')
                    self.emit_js(',\ny: ', end='')
                    self.emit_data_array(ys[pol_ind].data[power[pol_ind].mask], '{x:.3f}')
                    self.emit_js(",\nmode: 'markers'", end='')
                    self.emit_js(",\nvisible: {visible}", visible=visible, end='')
                    self.emit_js(",\ntext: ", end='')
                    self.emit_text_array(_text[pol_ind].data[power[pol_ind].mask], '{x}')
                    self.emit_js(",\n marker: {{  color: 'orange'", end='')
                    self.emit_js(", size: 14", end='')
                    self.emit_js("}},\nhovertemplate: '%{{text}}<br>", end='')
                    self.emit_js("Amp [dB]: NO DATA AVAILABLE<extra></extra>'", end='')
                    self.emit_js('}},\n', end='\n')

        self.emit_js(']', end='\n')

        self.emit_js(' var updatemenus=[')
        self.emit_js('{{buttons : [')

        # Amplitude Button
        self.emit_js('{{')
        self.emit_js('args: [')
        self.emit_js("{{'visible': ", end='')
        self.emit_data_array(amp_mask, '{x}')
        self.emit_js("}},\n{{'title': 'Median Auto Power vs Node',")
        self.emit_js("'annotations': {{}} }}")
        self.emit_js('],')
        self.emit_js("label: 'Auto Corr',")
        self.emit_js("method: 'update'")
        self.emit_js('}},')

        # PAMS buttons
        self.emit_js('{{')
        self.emit_js('args: [')
        self.emit_js("{{'visible': ", end='')
        self.emit_data_array(pam_mask, '{x}')
        self.emit_js("}},\n{{'title': 'PAM Power vs Node',")
        self.emit_js("'annotations': {{}} }}")
        self.emit_js('],')
        self.emit_js("label: 'Pam Power',")
        self.emit_js("method: 'update'")
        self.emit_js('}},')

        # ADC buttons
        self.emit_js('{{')
        self.emit_js('args: [')
        self.emit_js("{{'visible': ", end='')
        self.emit_data_array(adc_mask, '{x}')
        self.emit_js("}},\n{{'title': 'ADC Power vs Node',")
        self.emit_js("'annotations': {{}} }}")
        self.emit_js('],')
        self.emit_js("label: 'ADC Power',")
        self.emit_js("method: 'update'")
        self.emit_js('}},')

        self.emit_js('],', end='\n')
        self.emit_js('showactive: true,')
        self.emit_js("type: 'buttons',")
        self.emit_js('}},')
        self.emit_js(']', end='\n')

        self.emit_js("""

var layout2 = {{
    title: 'Power vs Node',
    xaxis: {{title: 'Node Number',
             dtick:1,
             tick0: 0,
             shogrid: false,
             showzeroline: false}},
    yaxis: {{showticklabels: false,
             showgrid: false,
             showzeroline: false}},
    autosize: true,
    showlegend: false,
    updatemenus: updatemenus,
    hovermode: 'closest'
}};

Plotly.plot("plotly-div2", data2, layout2, {{responsive: true}});
window.onresize = function() {{
// Plotly.relayout("plotly-div", {{
//                    width: 0.7 * window.innerWidth,
//                    height: 0.8 * window.innerHeight
//                          }})
 }}""")

    def emit(self):
        self.emit_html(HTML_HEADER)

        self.emit_html("""\
<body>
<div class="container">
  <div class="row">
    <div class="col-md-12">
        <p class="text-center"><big>Report generated <span id="age">???</span> ago (at {gen_date} UTC)<big></p>
    </div>
    <div class="col-md-12">
        <p class="text-cneter"><big><big>Data observerd at {iso_date} (JD: {jd_date})</big></big></p>
    </div>
  </div>
  <div class="row">
    <div id="plotly-div" class="col-md-12", style="height: 1000px"></div>
  </div>
   <div class="row">
     <div id="plotly-div2" class="col-md-12", style="height: 500px"></div>
   </div>
""", gen_date=self.now.iso,
     iso_date=self.latest.iso,
     jd_date=self.latest.jd)

        self.emit_js(JS_HEADER,
                     gen_time_unix_ms=self.now.unix * 1000,
                     )
        self.prep_data()

        self.emit_html("""\
  <div class="row">
    <div class="col-md-12">
        <p class="text-center"><a href="https://github.com/HERA-Team/simple-dashboard">Source code</a>.</p>
    </div>
  </div>
</div>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<script src="hex_amp.js"></script>
</body>
</html>
""")


if __name__ == '__main__':
    main()
