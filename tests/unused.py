#!/usr/bin/env python3

import redis

print ("------ Unused Keys -----------")
client = redis.Redis(host='127.0.0.1')
#client = redis.Redis(host='localhost', username='test')
try:
  unused = set()
  for key in client.scan_iter():
    if client.object('FREQ', key) == 0:
      unused.add( key.decode("utf-8") )

  print(len(unused))
  print(unused)
except redis.exceptions.NoPermissionError as err:
  print ("Some thouble:", err)

print ('End')
