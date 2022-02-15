#!/usr/bin/env sh

#исполняется внутри ARM dev образа (или на ARM системе)

GPSD_VERSION=gpsd-3.23.1

wget http://download-mirror.savannah.gnu.org/releases/gpsd/${GPSD_VERSION}.tar.gz
tar -xf ${GPSD_VERSION}.tar.gz

cd ${GPSD_VERSION}

python3 /usr/bin/scons -j8 build target_python=python3 shared=1

export DESTDIR=../../gpsd_bin_pack
python3 /usr/bin/scons install