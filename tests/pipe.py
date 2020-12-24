#!/usr/bin/env python3

import redis
from time import sleep


def Get(cli, key):
  if cli.exists(key):
    pipe = cli.pipeline()
    return pipe.get(key).sadd('all_keys_set', key).execute()[0]
  else:
    return None

client = redis.Redis(host='127.0.0.1')
#client = redis.Redis(host='localhost', username='test')
print ("---------- PIPELINE -----------------")
try:
  #client.pipeline(transaction=False)
  a = Get(client, "Name")
  if a:
    print (a)
  
  a = Get(client, "Misss")
  if a:
    print (a)


except redis.exceptions.NoPermissionError as err:
  print ("Some thouble:", err)
finally:
  client.config_set("notify-keyspace-events", "")

print("End off story")
