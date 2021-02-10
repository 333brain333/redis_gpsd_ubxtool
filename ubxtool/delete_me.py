import redis
redis_connection = {'host':'127.0.0.1',
'db':1,
'password':None,
'port':6379,
'socket_timeout':None,
'decode_responses':True
}
redis_client = redis.Redis(**redis_connection)
print('succeed')