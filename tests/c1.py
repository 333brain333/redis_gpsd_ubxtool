#!/usr/bin/env python3

import redis
from time import sleep

print ("Connect to Redis")
client = redis.Redis(host='127.0.0.1')
print ("-----------------------------------")

print ( 'tl_net:', client.get('tl_net'))
print ( 'Foo:', client.get('Foo'))

print ('pythonlist:', client.smembers('pythonlist'))
print ('redislist:', client.smembers('redislist'))
print ("set inter:", client.sinter('pythonlist', 'redislist'))
print ("set union:", client.sunion('pythonlist', 'redislist'))
print ("scard:", client.scard('pythonlist'))
