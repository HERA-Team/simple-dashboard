#print out interesting things for our web dashboard
from hera_mc import mc
from hera_mc.observations import Observation
from hera_mc.librarian import LibFiles
from hera_mc.node import NodeSensor
from astropy.time import TimeDelta,Time
from hera_mc.librarian import LibFiles
from astropy.units import Quantity
from sqlalchemy import func
import os
from math import floor

PREAMBLE="""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="300">
    <!-- The above 3 meta tags *must* come first -->

    <title>  HERA Dashboard</title>

    <!-- Latest compiled and minified CSS -->
    <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css">

    <!-- Optional theme -->
    <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap-theme.min.css">
    </head>
"""
import platform
if platform.python_version().startswith('3'):
    hostname = os.uname().nodename
else:
    hostname = os.uname()[1]
POSTAMBLE="""
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/1.11.3/jquery.min.js"></script>
  <!-- Include all compiled plugins (below), or include individual files as needed -->
  <!-- Latest compiled and minified JavaScript -->
  <script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js"></script>

  <footer class="footer navbar-default">
    <p class="text-muted text-center"><small><small>Table last updated: {now}<br>
    Script location: {scriptname}<br>
    Executing host: {hostname}
    </small></small></p>
  </footer>

</body>
</html>
""".format(now=Time.now().iso,scriptname=__file__,hostname=hostname)


  # <thead>
  #   <tr>
  #     <th scope="col">Item</th>
  #     <th scope="col">Status</th>
  #   </tr>
  # </thead>
TABLEHEAD="""
<table class="table">
  <tbody>
"""
TABLEEND="""
</tbody>
</table>
"""

BODY=""
BODY += PREAMBLE

parser = mc.get_mc_argument_parser()
args = parser.parse_args()
db  = mc.connect_to_mc_db(args)
session = db.sessionmaker()


BODY += TABLEHEAD

#get the most recent observation logged by the correlator
most_recent_obs = session.get_obs_by_time()[0]

dt = Time.now().gps - Time(most_recent_obs.starttime,format='gps',scale='utc').gps
dt_days = int(floor((dt/3600.)/24))
dt_hours= (dt - dt_days*3600*24)/3600.
BODY += """
            <tr>
               <th scope="row">Time Since Last Obs</th>
                  <td>{dt} days {h} hours </td>
               </th>
            </tr>
            """.format(dt=dt_days,h=int(dt_hours))
#get the number of raw files in the last 24 hours
numfiles = session.query(LibFiles).filter(LibFiles.time>(Time.now()+TimeDelta(Quantity(1,'day'))).gps).filter(LibFiles.filename.like('%uvh5')).count()
BODY += """
            <tr>
                <th scope="row">Raw Files Recorded (last 24 hours)</th>
                    <td>{n}</td>
                </th>
            </tr>
            """.format(n=numfiles)
#get the number of samples recorded by each node in the last 24 hours
result = session.query(NodeSensor.node,func.count(NodeSensor.time)).filter(NodeSensor.time>(Time.now()-TimeDelta(Quantity(1,'day'))).gps).group_by(NodeSensor.node)
BODY += """
            <tr>
                <th scope="row">Pings from Nodes (last 24 hours)</th>
            """
for l in result:
    BODY += "<td>Node{node}:{pings}</td>\n".format(node=l[0],pings=l[1])
BODY += "</tr>\n"
BODY += TABLEEND
BODY += POSTAMBLE

F = open("mc_html_summary.html",'w')
F.write(BODY)
F.close()
