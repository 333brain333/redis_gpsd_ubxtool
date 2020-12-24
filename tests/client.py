#!/usr/bin/env python3

import redis
from time import sleep


print ("Hello Redis")

client = redis.Redis(host='127.0.0.1')

client.set('Language', 'Python', ex=5)
print ( client.get('Language') )
sleep(3)
print ( client.ttl('Language') )

client.set('tl_net', 'False')

print ( client.get('tl_net'))

# Пример использования множеств
client.sadd('pythonlist', 'value1', 'value2', 'value3')
print (client.smembers('pythonlist'))
client.sadd('redislist', 'value1', 'value5', 'value6', 'value7', 'value8')
print ("sinter", client.sinter('pythonlist', 'redislist'))
print ("sunion", client.sunion('pythonlist', 'redislist'))
print (client.scard('pythonlist'))

# Пример использования хеш таблиц
client.hset('Person', 'Name', 'Person1')
client.hset('Person', 'Health', '600')
client.hset('Person', 'Mana', '200')
print ( client.hgetall('Person') )

