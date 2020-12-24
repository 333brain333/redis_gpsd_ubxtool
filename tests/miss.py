#!/usr/bin/env python3

import redis
from time import sleep

print ("Tram Route")
client = redis.Redis(host='127.0.0.1')
#client = redis.Redis(host='localhost', username='test')
print ("-----------------------------------")
try:
  m = client.get('miss2')
  if m:
    print ( m.decode("utf-8") )
  else:
    print ( "No miss2")

except redis.exceptions.NoPermissionError as err:
  print ("Some thouble:", err)
  
  

client.set('Language', 'Pytho123123')
