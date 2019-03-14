#!/bin/bash

ANSIBLE_HOST='somewhere.com'
ANSIBLE_PORT_WEB=5000
ANSIBLE_PORT_TRANSPORT=5001

ANSIBLE_FUNC=$1
ANSIBLE_CHANNEL=$2
ANSIBLE_FILEPATH=$3

CLIENT_UUID=''

echo ">> Trying to join the channel '${ANSIBLE_CHANNEL}'"
while true; do
    URL="http://${ANSIBLE_HOST}:${ANSIBLE_PORT_WEB}/${ANSIBLE_FUNC}/${ANSIBLE_CHANNEL}";
    OUTPUT=$(curl -s $URL);
    echo "$URL => $OUTPUT";

    if [ $(echo "$OUTPUT" | jq .result) = 'true' ]; then
        CLIENT_UUID=$(echo "$OUTPUT" | jq -r .uuid);
        break;
    fi
    sleep 1;
done;

echo ">> Trying to ${ANSIBLE_FUNC} a file '${ANSIBLE_FILEPATH}'"
if [ $ANSIBLE_FUNC = 'send' ]; then
    cat <(echo -n $CLIENT_UUID) <(base64 $ANSIBLE_FILEPATH) | nc -q 0 $ANSIBLE_HOST $ANSIBLE_PORT_TRANSPORT;
fi
if [ $ANSIBLE_FUNC = 'receive' ]; then
    base64 -d <(echo -n $CLIENT_UUID | nc -q -1 $ANSIBLE_HOST $ANSIBLE_PORT_TRANSPORT) > $ANSIBLE_FILEPATH;
fi

echo "done."
