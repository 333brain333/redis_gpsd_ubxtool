'''import redis

host_ip = '127.0.0.1'
database = 1
user_name = None
user_password = None
host_port = 6379
s_t = None
client = redis.Redis(host=host_ip,\
                     password=user_password,\
                     port=host_port,\   
                     socket_timeout=s_t,\
                     db=database)
data = client.get()'''
from gps import *
session = gps() # assuming gpsd running with default options on port 2947
session.stream(WATCH_ENABLE|WATCH_JSON)
report = session.next()
print(report['class'])
if report['class'] == 'TPV':
    lat = getattr(report, 'lat', 'Unknown')
    lon = getattr(report, 'lon', 'Unknown')
    print("Your position: lon = " + str(longitude) + ", lat = " + str(latitude))
