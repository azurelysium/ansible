#!/bin/bash

ANSIBLE_HOST='somewhere.com'
ANSIBLE_PORT_WEB=5000
ANSIBLE_PORT_TRANSPORT=5001

ANSIBLE_FUNC=$1
ANSIBLE_CHANNEL=$2
ANSIBLE_FILEPATH=$3

echo ">> Trying to join the channel '${ANSIBLE_CHANNEL}'"
while true; do
    URL="http://${ANSIBLE_HOST}:${ANSIBLE_PORT_WEB}/${ANSIBLE_FUNC}/${ANSIBLE_CHANNEL}";
    OUTPUT=$(curl -s $URL);
    echo "$URL => $OUTPUT";

    if [ $(echo "$OUTPUT" | jq .result) = 'true' ]; then
       break;
    fi
    sleep 1;
done;

echo ">> Trying to send/receive a file '${ANSIBLE_FILEPATH}'"
if [ $ANSIBLE_FUNC = 'send' ]; then
    nc $ANSIBLE_HOST $ANSIBLE_PORT_TRANSPORT < $ANSIBLE_FILEPATH
elif [ $ANSIBLE_FUNC = 'receive' ]; then
    nc $ANSIBLE_HOST $ANSIBLE_PORT_TRANSPORT > $ANSIBLE_FILEPATH
fi

echo "done."
