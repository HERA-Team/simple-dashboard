#!/usr/bin/env python

import redis
import time
import json
import argparse
import syslog

parser = argparse.ArgumentParser(
    description="Subscribe to the redis-based log stream",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "-r",
    dest="redishost",
    type=str,
    default="redishost",
    help="Host servicing redis requests",
)

args = parser.parse_args()
pool = redis.ConnectionPool(host=args.redishost)


priority_dict = {
    "LOG_EMERG": 0,
    "LOG_ALERT": 1,
    "LOG_CRIT": 2,
    "LOG_ERR": 3,
    "LOG_WARNING": 4,
    "LOG_NOTICE": 5,
    "LOG_INFO": 6,
    "LOG_DEBUG": 7,
}
severity_dict = {
    "CRITICAL": "LOG_CRIT",
    "WARNING": "LOG_WARNING",
    "ERR": "LOG_ERR",
    "INFO": "LOG_INFO"
}

last_command_id = None
while True:
    try:
        print(f"Connecting to redis server {args.redishost}")
        r = redis.Redis(connection_pool=pool)
        ps = r.pubsub()
        ps.subscribe("log-channel")
        for mess in ps.listen():
            if (
                mess is not None
                and mess["type"] != "subscribe"
                # messages come as byte strings, make sure an error didn't occur
                and mess["data"].decode() != "UnicodeDecodeError on emit!"
            ):
                message = json.loads(mess["data"])["formatted"]
                if not any(h in message for h in ["hera_corr_f", "hera_snap_redis_monitor"]):
                    input = message.split(":")[0]
                    try:
                        syslog.syslog(priority_dict[severity_dict[input]], message)
                    except KeyError:
                        syslog.syslog(priority_dict["LOG_INFO"], message)

    except KeyboardInterrupt:
        ps.close()
        exit()
    except Exception as e:
        if not str(e).startswith("'NoneType' object has no attribute 'readline'"):
            syslog.syslog(priority_dict["LOG_ERR"], str(e))
            print("An unexpected error occured!")
        time.sleep(1)
        ps.close()
        continue
