#!/usr/bin/env python

import redis
import time
import json
import slacker
import argparse
import sys

with open("correlator.token", "r") as f:
    token = f.read()

slack = slacker.Slacker(token)
slack_chan = "#correlator_robot"
username = "Correlator Log Bot"

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

try:
    channel_id = None
    for channel in json.loads(slack.channels.list().raw)["channels"]:
        if channel["name_normalized"] == slack_chan.lstrip("#"):
            channel_id = channel["id"]
    if channel_id is not None:
        print(f"Channel ID: {channel_id}")
except:
    channel_id = None

last_command_id = None
post_cnt = 0
while True:
    try:
        # Try to get 50 messages at a time
        # this loop blocks for 1s if there are no messages.
        message = ""
        for i in range(100):
            mess = ps.get_message(ignore_subscribe_messages=True, timeout=1)
            if mess is not None:
                message += json.loads(mess["data"])["formatted"] + "\n"
            else:
                break
        message = message.rstrip()  # Get rid of trailing \n

        if message != "":
            print(message)
            slack.chat.post_message(slack_chan, username=username, text=message)
            time.sleep(1)
        post_cnt += 1

        s_mess = slack.channels.history(channel_id, count=2)
        if not s_mess.successful:
            print("Not ok")
        else:
            for m in s_mess.body["messages"]:
                u = m.get("username", m.get("user"))
                if u != username:
                    command_id = m["ts"]
                    command_text = m["text"]
                    if command_id != last_command_id:
                        last_command_id = command_id
                        if command_text == "flush":
                            print("Flushing")
                            slack.chat.post_message(
                                slack_chan, username=username, text="Flushing"
                            )
                            ps.unsubscribe()
                            ps.subscribe("log-channel")
                        elif command_text == "stop":
                            print("Stopping")
                            slack.chat.post_message(
                                slack_chan, username=username, text="Stopping"
                            )
                            ps.unsubscribe()
                        elif command_text == "start":
                            print("Starting")
                            slack.chat.post_message(
                                slack_chan, username=username, text="Starting"
                            )
                            ps.unsubscribe()
                            ps.subscribe("log-channel")
                        else:
                            print("Unknown command")
                            slack.chat.post_message(
                                slack_chan,
                                username=username,
                                text="Allowed commands: flush, stop, start",
                            )
                    break  # only process 1 user message

    except KeyboardInterrupt:
        ps.close()
        exit()
    except:
        print("An unexpected error occured!")
        time.sleep(1)
