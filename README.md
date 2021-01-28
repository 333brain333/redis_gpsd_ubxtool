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
