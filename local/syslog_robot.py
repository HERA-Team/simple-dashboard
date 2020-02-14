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

print(f"Connecting to redis server {args.redishost}")
r = redis.Redis(args.redishost)

ps = r.pubsub()

ps.subscribe("log-channel")

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
        # Try to get 50 messages at a time
        # this loop blocks for 1s if there are no messages.
        for mess in ps.listen():
            if (
                mess["type"] != "subscribe"
                and mess["channel"] == args.channel
                # messages come as byte strings, make sure an error didn't occur
                and mess["data"].decode() != "UnicodeDecodeError on emit!"
            ):
                message = json.loads(mess["data"])["formatted"]
                if not any(h in message for h in ["hera_corr_f", "hera_snap_redis_monitor"]):
                    input = message.split(":")[0]
                    syslog.syslog(priority_dict[severity_dict[input]], message)

    except KeyboardInterrupt:
        ps.close()
        exit()
    except Exception as e:
        print("An unexpected error occured!")
        raise e
        time.sleep(1)
        continue
