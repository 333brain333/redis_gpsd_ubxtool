#!/usr/bin/bash
export PYTHONPATH=/home/agrodroid/releases/active_release/redis_gpsd_ubxtool/gpsd/lib/python3/dist-packages
export PATH=/home/agrodroid/releases/active_release/redis_gpsd_ubxtool/gpsd/bin/:$PATH
python3 $@
