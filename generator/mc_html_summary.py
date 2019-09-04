#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-
# Copyright 2017-2019 the HERA Collaboration
# Licensed under the 2-clause BSD license.

"""print out interesting things for our web dashboard."""
from hera_mc import mc
from hera_mc.librarian import LibFiles
from hera_mc.node import NodeSensor
from hera_mc.correlator import CorrelatorControlState
from astropy.time import TimeDelta, Time
from astropy.units import Quantity
from sqlalchemy import func
import os
from math import floor
from jinja2 import Environment, FileSystemLoader
import platform


def main():
    if platform.python_version().startswith('3'):
        hostname = os.uname().nodename
    else:
        hostname = os.uname()[1]

    # templates are stored relative to the script dir
    script_dir = os.path.dirname(os.path.realpath(__file__))
    template_dir = os.path.join(script_dir, 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))

    parser = mc.get_mc_argument_parser()
    args = parser.parse_args()
    db = mc.connect_to_mc_db(args)
    session = db.sessionmaker()

    # get the most recent observation logged by the correlator
    most_recent_obs = session.get_obs_by_time()[0]

    dt = (Time.now().gps
          - Time(most_recent_obs.starttime, format='gps', scale='utc').gps
          )
    dt_days = int(floor((dt / 3600.) / 24))
    dt_hours = (dt - dt_days * 3600 * 24) / 3600.

    # get the number of raw files in the last 24 hours
    numfiles = (session.query(LibFiles)
                .filter(LibFiles.time
                        > (Time.now() - TimeDelta(Quantity(1, 'day'))).gps)
                .filter(LibFiles.filename.like('%uvh5')).count()
                )
    # get the number of samples recorded by each node in the last 24 hours
    result = (session.query(NodeSensor.node,
                            func.count(NodeSensor.time))
              .filter(NodeSensor.time
                      > (Time.now() - TimeDelta(Quantity(1, 'day'))).gps)
              .group_by(NodeSensor.node)
              )
    node_pings = ''
    for l in result:
        node_pings += "Node{node}:{pings}   ".format(node=l[0], pings=l[1])

    # get the current state of is_recording()
    result = (session.query(CorrelatorControlState.state,
                            CorrelatorControlState.time)
              .filter(CorrelatorControlState.state_type.like('taking_data'))
              .order_by(CorrelatorControlState.time.desc()).limit(1).one()
              )
    is_recording = result[0]
    last_update = Time(result[1], scale='utc', format='gps')

    html_template = env.get_template("mc_table.html")

    rendered_html = html_template.render(dt_days=dt_days,
                                         dt_hours=dt_hours,
                                         numfiles=numfiles,
                                         node_pings=node_pings,
                                         is_recording=is_recording,
                                         last_update=last_update.iso,
                                         now=Time.now().iso,
                                         scriptname=__file__,
                                         hostname=hostname)

    with open("mc_html_summary.html", 'w') as h_file:
        h_file.write(rendered_html)


if __name__ == "__main__":
    main()
