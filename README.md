# File structure of the project:

/opt/cognitive/between_redis_and_ubx.py      # main script
/etc/default/gpsd                            # defaults options for gpsd.service (zed-f9p port, gpsd app parameters (-G -n))
/lib/systemd/system/gpsd.socket              # modifyed file for external access to gpsd 
/lib/systemd/system/gps_handler_agro.service # service that starts main script
/etc/cognitive/redis_fields_gpsd.json        # redis fileds
/etc/cognitive/redis_connection_gpsd.json    # redis connection params (ip, port, etc)

# Install

To install, download zip archive. Then unzip and run install. After that, make systemd daemon-reload and enable gps_handler_agro service. Here are commands aimed to process those steps:

unzip redis_gpsd_ubxtool-master.zip
rm redis_gpsd_ubxtool-master.zip
cd redis_gpsd_ubxtool-master
./install
sudo systemctl daemon-reload
sudo systemctl enable gps_handler_agro.service
sudo reboot

#Usage
After install main script will try to connect to resis database, specified in /etc/cognitive/redis_connection_gpsd.json. Also it will wait untill zed-f9p is present in /dev/serial/by-id/. After that main script will iteratively update fileds in redis by interacting with gpsd and ubxtool. All log of the main script is placed in the syslod. One may use next command to obtain logs for today related to main script:
journalctl -r -S today -u gps_handler_agro.service 

##Redis
Fields description:

'connection':'not connected',  # Shows zed-f9p connection status
'rtk_source':'disabled',       # Specify source of RTCM3 corrections 
'rtk':                         # RTK connection params. This field is set as hmset (hash table)
    'user':'Unknown',
    'password':'Unknown',
    'server':'Unknown',
    'port':'Unknown',
    'stream':'Unknown'
'CFG-NAVSPG-DYNMODEL':4,       # Sets dynamic platform model to automotive
'CFG-RATE-MEAS':100,           # Sets solution output rate to 1000/value
'CFG-SBAS-USE_TESTMODE':1,     # Enable sbas test mode 
'CFG-SBAS-USE_RANGING':0,      # Disable using sbas for ranging 
'CFG-SBAS-PRNSCANMASK':3145760,# SV number to listen to obtain sdcm corrections (125, 140, 141)
'CFG-SIGNAL-SBAS_ENA':1        # Turn on SBAS
'lat':None,                    # Latitude
'lon':None,                    # Longitude
'device':None,                 # Device that connected to gpsd
'mode':None,                   # NMEA mode:0=Unknown,1=no fix,2=2d fix,3=3d fix
'status':None,                 # GPS fix status: 0=Unknown,1=Normal,2=DGPS,3=RTK Fixed,4=RTK Floating,5=DR,6=GNSSDR,7=Time (surveyed),8=Simulated,9=P(Y)
'altHAE':None,                 # Altitude, height above ellipsoid, in meters. Probably WGS84.
'speed':None,                  # Speed over ground, meters per second.
'eph':None,                    # Estimated horizontal Position (2D) Error in meters. Also known as Estimated Position Error (epe). Certainty unknown.
'time':None                    # Time/date stamp in ISO8601 format, UTC. May have a fractional part of up to .001sec precision. May be absent if the mode is not 2D or 3D.
'hdop':None,                   # Horizontal dilution of precision, a dimensionless factor which should be multiplied by a base UERE to get a circular error estimate.
'nSat':None,                   # Number of satellite objects in "satellites" array.
'uSat':None                    # Number of satellites used in navigation solution.

One may add fields in /etc/cognitive/redis_fields_gpsd into 'gpsd':'TPV' and 'gpsd':'SKY' dictionaries from sheets from https://gpsd.gitlab.io/gpsd/gpsd_json.html#_tpv (table 1 and 2).

#How does main script work

