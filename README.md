# redis_gpsd_ubxtool

Don't forget to adjust syslog size:
- place this:
```
$outchannel mysyslog,/var/log/syslog,1048576
*.*;auth,authpriv.none  :omfile:$mysyslog
```
into file /etc/rsyslog.d/50-default.conf instead of 
`.*;auth,authpriv.none       -/var/log/syslog`
This will limit syslog to 100MB


Issues:
- by commit e493b5f2677fb3290da01c0d2e3a40e4889b4a1a script falls after start in case of redis server doesn't running. And falls in working mode if redis server stoped working. 

Page in Confluence about gpsd: [U-blox zed-f9p](https://confluence.cognitivepilot.com/display/AUTOBOT/U-blox+zed-f9p)


1) python requirement packages
* redis
* gps (usually comes with gpsd package)
2) running redis server with port 6379 without autentification
3) plugged  in ubx module
4) place gps_handler_agro@.service in /etc/systemd/system/
5) place between_redis_and_ubx.py in /home/$USER/
6) sudo chmod +x between_redis_and_ubx.py
7) add in file /etc/default/gpsd in DEVICES ="/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00" in GPSD_OPTIONS = "-n -G"
5) sudo systemctl daemon-reload
6) sudo systemctl start gps_handler_agro@$USER.service
7) to check wheteher the service is running: sudo systemctl status gps_handler_agro@$USER.service






