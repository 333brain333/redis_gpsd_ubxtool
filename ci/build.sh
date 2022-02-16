#!/usr/bin/env sh
#исполняем в хостовой системе
#########################################################################
SCRIPT_DIR=`dirname $(readlink -f $0)`
#########################################################################
IMAGE_ARM=gitlab.cognitivepilot.com:4567/docker/images/armhf/dev:20-latest
if [ $# -ge 1 ]; then
  IMAGE_ARM="$1"
fi
echo "use IMAGE_ARM: ${IMAGE_ARM}"

docker pull ${IMAGE_ARM}
#########################################################################
docker run --rm --workdir=/external-dir --mount source=${SCRIPT_DIR},target=/external-dir,type=bind \
${IMAGE_ARM} /external-dir/buildGpsd.sh `id -u` `id -g`
#########################################################################
docker run --rm --workdir=/external-dir --mount source=${SCRIPT_DIR},target=/external-dir,type=bind \
${IMAGE_ARM} /external-dir/buildNtripclient.sh `id -u` `id -g`