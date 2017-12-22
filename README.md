# simple-dashboard

A really simple system for making HERA dashboards.

The [server](server/README.md) subdirectory contains files and notes on
setting up a dashboard server using Google Compute Engine. At the moment, this
server is really dumb: you can `scp` files to it, and it will serve up those
files using a web server.

The [generator](generator/) subdirectory has scripts that make dashboards.
Every 10 minutes on `qmaster`,
[a cronjob](https://github.com/HERA-Team/HERA_Commissioning/blob/master/scripts/qmaster/dashboard.sh)
runs the scripts and uploads the outputs to the server.

The “meat” of the server happens inside a Docker container, and it would be
straightforward to have the server run additional Docker containers that
provide more sophisticated services (subject to the constraints that the
server runs on a
[f1-micro](https://cloud.google.com/compute/pricing#sharedcore) machine
because that’s free).
