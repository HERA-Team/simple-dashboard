#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2018 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""Generate a simple dashboard page for monitoring data quality."""

from __future__ import absolute_import, division, print_function

import os
import sys
import numpy as np
from astropy.time import Time, TimeDelta
from hera_mc import mc
from hera_mc.qm import AntMetrics, ArrayMetrics
import sqlalchemy
from jinja2 import Environment, FileSystemLoader


def do_ant_metric(session, metric, yexpression,
                  ymode='lines', yname='NONAME', cutoff=None):
    data = (session.query(AntMetrics.obsid, yexpression)
            .filter(AntMetrics.metric == metric)
            .filter(AntMetrics.obsid > cutoff.gps)
            .group_by(AntMetrics.obsid)
            .order_by(AntMetrics.obsid)
            .all())
    # 300s are added here ONLY because it was this way in the
    # legacy pdoubled_slotter.
    time_array = Time([t[0] + 300 for t in data], format='gps')
    if time_array:
        time_array = time_array.isot.tolist()
    else:
        time_array = []
    _data = [{"x": time_array,
              "y": (np.ma.masked_invalid([t[1] for t in data])
                    .filled(None).tolist()),
              "name": yname,
              "mode": ymode,
              }
             ]
    return _data


def do_xy_array_metric(session, metric_base, yexpression=ArrayMetrics.val,
                       doubled_suffix=False, ymode='lines', cutoff=None):
    if doubled_suffix:
        suffixes = ['_XX', '_YY']
    else:
        suffixes = ['_x', '_y']
    _data = []
    for desc, suffix in zip('XY', suffixes):
        data = (session.query(ArrayMetrics.obsid, yexpression)
                .filter(ArrayMetrics.metric == metric_base + suffix)
                .filter(ArrayMetrics.obsid > cutoff.gps)
                .order_by(ArrayMetrics.obsid)
                .all())
        # 300s are added here ONLY because it was this way in the
        # legacy pdoubled_slotter.
        time_array = Time([t[0] + 300 for t in data], format='gps')
        if time_array:
            time_array = time_array.isot.tolist()
        else:
            time_array = []
        __data = {"x": time_array,
                  "y": (np.ma.masked_invalid([t[1] for t in data])
                        .filled(None).tolist()),
                  "name": desc,
                  "mode": ymode,
                  }
        _data.append(__data)

    return _data


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

    plotnames = [["am-xants", "am-meanVij"],
                 ["am-redCorr", "am-meanVijXpol"],
                 ["fc-agg_std", "fc-max_std"],
                 ["oc-ant_phs_std_max", "oc-chisq_tot_avg"]]
    colsize = 6
    TIME_WINDOW = 7  # days
    now = Time.now()
    cutoff = now - TimeDelta(TIME_WINDOW, format='jd')
    time_axis_range = [cutoff.isot, now.isot]

    caption = {}
    caption["title"] = "Daily Quality Metrics"

    caption["text"] = (
        "An overview of the Daily Quality metrics run on data from RTP. "
        "A plot with no data indicates that particular metric was not run, "
        "or the data could not be found."
        "<br><br>"
        "Currenly only the Ant Metrics are run on data during RTP."
        """<div class="table-responsive">
            <table class="table table-striped" style="border:1px solid black; border-top; 1px solid black;">
            <tbody>
              <tr>
                <td style="border-left:1px solid black;">Ant Metrics Number of Excluded Ants
                <td style="border-left:1px solid black;">Ant Metrics Mean Vij Ampltiude</td>
              </tr>
              <tr>
                <td style="border-left:1px solid black;">Ant Metrics red Corr Mean Ampltidue
                <td style="border-left:1px solid black;">Ant Metrics Mean Vij Cross Pol Ampltidue</td></tr>
              <tr>
                <td style="border-left:1px solid black;">Frist Cal Agg Std
                <td style="border-left:1px solid black;">First Cal Max Stde</td></tr>
              <tr>
                <td style="border-left:1px solid black;">Ominical Phase Std Max
                <td style="border-left:1px solid black;">Omnical Chi-square Total Average</td></tr>
            </tbody>
            </table>
         </div>
        """
    )

    html_template = env.get_template("plotly_base.html")
    rendered_html = html_template.render(plotname=plotnames,
                                         plotstyle="height: 220",
                                         colsize=colsize,
                                         gen_date=now.iso,
                                         gen_time_unix_ms=now.unix * 1000,
                                         js_name='qm',
                                         hostname=computer_hostname,
                                         scriptname=os.path.basename(__file__),
                                         caption=caption
                                         )
    with open('qm.html', 'w') as h_file:
        h_file.write(rendered_html)

    js_template = env.get_template('plotly_base.js')

    with db.sessionmaker() as session:

        layout = {"xaxis": {"range": time_axis_range},
                  "yaxis": {"title": 'placeholder'},
                  "title": {"text": 'placeholder'},
                  "height": 200,
                  "margin": {"t": 30, "r": 10,
                             "b": 2, "l": 40},
                  "legend": {"orientation": "h",
                             "x": 0.15,
                             "y": -0.15},
                  "showlegend": False,
                  "hovermode": "closest"
                  }

        # If an antpol is detected as bad (`val` not used).
        data = do_ant_metric(session,
                             'ant_metrics_xants',
                             sqlalchemy.func.count(),
                             ymode='markers',
                             yname='Data',
                             cutoff=cutoff
                             )

        layout["yaxis"]["title"] = 'Count'
        layout["title"]["text"] = "Ant Metrics # of Xants"
        rendered_js = js_template.render(plotname='am-xants',
                                         data=data,
                                         layout=layout)
        with open('qm.js', 'w') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        # "Mean of the absolute value of all visibilities associated with an
        # antenna".
        data = do_ant_metric(session,
                             'ant_metrics_meanVij',
                             sqlalchemy.func.avg(AntMetrics.val),
                             yname='Data',
                             cutoff=cutoff
                             )
        layout["yaxis"]["title"] = 'Average Amplitude'
        layout["title"]["text"] = "Ant Metrics MeanVij"
        rendered_js = js_template.render(plotname='am-meanVij',
                                         data=data,
                                         layout=layout)
        with open('qm.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        # "Extent to which baselines involving an antenna do not correlate
        # with others they are nominmally redundant with".
        data = do_ant_metric(session,
                             'ant_metrics_redCorr',
                             sqlalchemy.func.avg(AntMetrics.val),
                             yname='Data',
                             cutoff=cutoff
                             )
        layout["yaxis"]["title"] = 'Average Amplitude'
        layout["title"]["text"] = "Ant Metrics redCorr"
        rendered_js = js_template.render(plotname='am-redCorr',
                                         data=data,
                                         layout=layout)
        with open('qm.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        # "Ratio of mean cross-pol visibilities to mean same-pol visibilities:
        # (Vxy+Vyx)/(Vxx+Vyy)".
        data = do_ant_metric(session,
                             'ant_metrics_meanVijXPol',
                             sqlalchemy.func.avg(AntMetrics.val),
                             yname='Data',
                             cutoff=cutoff
                             )
        layout["yaxis"]["title"] = 'Average Amplitude'
        layout["title"]["text"] = "Ant Metrics MeanVij CrossPol"
        rendered_js = js_template.render(plotname='am-meanVijXpol',
                                         data=data,
                                         layout=layout)
        with open('qm.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        # "Aggregate standard deviation of delay solutions".
        data = do_xy_array_metric(session,
                                  'firstcal_metrics_agg_std',
                                  cutoff=cutoff
                                  )
        layout["yaxis"]["title"] = 'std'
        layout["title"]["text"] = "FirstCal Metrics Agg Std"
        rendered_js = js_template.render(plotname='fc-agg_std',
                                         data=data,
                                         layout=layout)
        with open('qm.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        # "Maximum antenna standard deviation of delay solutions".
        data = do_xy_array_metric(session,
                                  'firstcal_metrics_max_std',
                                  cutoff=cutoff
                                  )
        layout["yaxis"]["title"] = 'FC max_std'
        layout["title"]["text"] = "FirstCal Metrics Max Std"
        rendered_js = js_template.render(plotname='fc-max_std',
                                         data=data,
                                         layout=layout)
        with open('qm.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        # Maximum of "gain phase standard deviation per-antenna across file".
        data = do_xy_array_metric(session,
                                  'omnical_metrics_ant_phs_std_max',
                                  doubled_suffix=True,
                                  cutoff=cutoff
                                  )
        layout["yaxis"]["title"] = 'OC ant_phs_std_max'
        layout["title"]["text"] = "OmniCal Metrics Ant Phase Std max"
        rendered_js = js_template.render(plotname='oc-ant_phs_std_max',
                                         data=data,
                                         layout=layout)
        with open('qm.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')

        # "Median of chi-square across entire file".
        data = do_xy_array_metric(session,
                                  'omnical_metrics_chisq_tot_avg',
                                  doubled_suffix=True,
                                  cutoff=cutoff
                                  )
        layout["yaxis"]["title"] = 'OC chisq_tot_avg'
        layout["title"]["text"] = "OmniCal Metrics Chi-square total avg"
        rendered_js = js_template.render(plotname='oc-chisq_tot_avg',
                                         data=data,
                                         layout=layout)
        with open('qm.js', 'a') as js_file:
            js_file.write(rendered_js)
            js_file.write('\n\n')


if __name__ == '__main__':
    main()
