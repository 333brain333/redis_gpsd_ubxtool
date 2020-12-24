#!/usr/bin/env python3

import redis
from time import sleep

print ("Hello Redis")

client = redis.Redis(host='127.0.0.1')

client.set('Language', 'Python')
client.set('tl_net', 'False')
# Пример использования множеств
client.sadd('pythonlist', 'PL-1', 'PL-2', 'PL-3')
client.sadd('redislist', 'value1', 'value5', 'value6', 'value7', 'value8')

#print ("Save")
#client.save()

#print (client.smembers('pythonlist'))

#print ("sinter", client.sinter('pythonlist', 'redislist'))
#print ("sunion", client.sunion('pythonlist', 'redislist'))
#print (client.scard('pythonlist'))
