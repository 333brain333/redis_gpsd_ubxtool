#!/usr/bin/env sh

#исполняется внутри ARM dev образа (или на ARM системе)

NTRIPCLIENT_VERSION=1.51

wget --no-check-certificate -O ntripclient-${NTRIPCLIENT_VERSION}.tar.gz https://github.com/nunojpg/ntripclient/archive/refs/tags/v${NTRIPCLIENT_VERSION}.tar.gz
tar -xf ntripclient-${NTRIPCLIENT_VERSION}.tar.gz

cd ntripclient-${NTRIPCLIENT_VERSION}
make
mkdir -p ../ntripclient_bin_pack/
cp ntripclient ../ntripclient_bin_pack