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
