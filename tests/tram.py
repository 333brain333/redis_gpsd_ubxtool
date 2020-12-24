#!/usr/bin/env python3

import redis
from time import sleep

print ("Tram Route")
#client = redis.Redis(host='127.0.0.1')
client = redis.Redis(host='localhost', username='test')
print ("-----------------------------------")
try:
  trm = client.get('tram_route.yaml')
  print ( trm.decode("utf-8") )
except redis.exceptions.NoPermissionError as err:
  print ("Some thouble:", err)

try:
  val = client.get('test:key0')
  print ('test:key0', val.decode("utf-8"))
except redis.exceptions.NoPermissionError as err:
  print ("Some thouble:", err)

try:
  val = client.set('test:key22', 'My test22')
except redis.exceptions.NoPermissionError as err:
  print ("Some thouble:", err)

#disconnect