#!/usr/bin/env python3

import redis
from time import sleep

print ("Tram Route")
client = redis.Redis(host='127.0.0.1')
#client = redis.Redis(host='localhost', username='test')
print ("-----------------------------------")
try:
  client.config_set("notify-keyspace-events", "AEm")

  sub = client.pubsub()
# subscribe to classical music
  #sub.psubscribe('__keyevent@0__:*')
  #sub.psubscribe('__key*@0__:*')
  sub.psubscribe('__keyevent@0__:keymiss')
  
  # drop first msg about subscribe to channel
  sub.get_message()

  for msg in sub.listen():
    #do_something(new_message)
    print(type(msg))
    print(msg['channel'])
    print(msg['data'])

  sub.unsubscribe()

except redis.exceptions.NoPermissionError as err:
  print ("Some thouble:", err)
finally:
  client.config_set("notify-keyspace-events", "")

print("End off story")
