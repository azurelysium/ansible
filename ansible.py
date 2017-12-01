#
# Ansible - simple relay server for file transfer
#
# Usage:
#
# $ ansible receive <channel_name> <destination_file>
#
# In anoter host,
# $ ansible send <channel_name> <source_file>
#
from twisted.web import server, resource
from twisted.internet import reactor, endpoints, protocol

import re
import time
import json
from pprint import pprint


ANSIBLES_MAX = 100
ansible_map = {}
address_map = {}

# Ansible Web Server
class AnsibleWeb(resource.Resource):
    isLeaf = True

    def _process_send(self, request, channel):
        if channel not in ansible_map:
            return json.dumps({'result': False, 'reason': 'there is no receiver'})

        client_ip = request.getClientIP()
        if 'sender' not in ansible_map[channel]:
            ansible_map[channel]['sender'] = client_ip
            address_map[client_ip] = {'channel': channel}
            
        elif ansible_map[channel]['sender'] != client_ip:
            return json.dumps({'result': False, 'reason': 'this channel is already in use'})

        return json.dumps({'result': True})


    def _process_receive(self, request, channel):
        if len(ansible_map) >= ANSIBLES_MAX:
            return json.dumps({'result': False,
                               'reason': 'the number of ansibles reaches its limit: {}'.format(ANSIBLES_MAX)})

        client_ip = request.getClientIP()
        if (channel not in ansible_map) or (ansible_map[channel]['expired_at'] < time.time()):
            ansible_map[channel] = {'receiver': client_ip, 'created_at': time.time()}
            ansible_map[channel]['expired_at'] = ansible_map[channel]['created_at'] + (60 * 5) # 5 minutes

            # Remove the existing channel
            if client_ip in address_map:
                del ansible_map[address_map[client_ip]['channel']]
            address_map[client_ip] = {'channel': channel}

        elif ansible_map[channel]['receiver'] != client_ip:
            return json.dumps({'result': False, 'reason': 'this channel is already in use'})

        return json.dumps({'result': True})


    def render_GET(self, request):
        print 'AnsibleWeb: {} => {}'.format(request.getClientIP(), request.uri)
        retval = json.dumps({'result': False, 'reason': 'invalid endpoint'})

        if re.match('^/send/[^/?]+$', request.uri):
            (_, _, channel) = request.uri.split('/')
            retval = self._process_send(request, channel)

        if re.match('^/receive/[^/?]+$', request.uri):
            (_, _, channel) = request.uri.split('/')
            retval = self._process_receive(request, channel)

        if re.match('^/script$', request.uri):
            with open('ansible.sh', 'r') as f:
                retval = f.read()

        pprint(ansible_map)
        return retval


# Ansible Transport Server
class AnsibleTransport(protocol.Protocol):
    def __init__(self, factory):
        self.factory = factory


    def connectionMade(self):
        self.factory.numProtocols = self.factory.numProtocols + 1

        self.client_ip = self.transport.getPeer().host
        if self.client_ip in address_map:
            address_map[self.client_ip]['transport'] = self.transport
        else:
            self.transport.loseConnection()

        print 'AnsibleTrnasport: {}'.format(self.client_ip)
        pprint(address_map)


    def connectionLost(self, reason):
        self.factory.numProtocols = self.factory.numProtocols - 1

        if self.client_ip in address_map:
            channel = address_map[self.client_ip]['channel']
            if channel in ansible_map:
                ansible = ansible_map[channel]
                if ansible['sender'] != self.client_ip:
                    address_map[ansible['sender']]['transport'].loseConnection()
                if ansible['receiver'] != self.client_ip:
                    address_map[ansible['receiver']]['transport'].loseConnection()
                del ansible_map[channel]
            del address_map[self.client_ip]


    def dataReceived(self, data):
        channel = address_map[self.client_ip]['channel']
        ansible = ansible_map[channel]
        if self.client_ip == ansible['sender']:
            transport = address_map[ansible['receiver']]['transport']
            transport.write(data)


class AnsibleTransportFactory(protocol.Factory):
    def __init__(self):
        self.numProtocols = 0

    def buildProtocol(self, addr):
        return AnsibleTransport(self)


# Reactor
endpoint = endpoints.TCP4ServerEndpoint(reactor, 5000)
endpoint.listen(server.Site(AnsibleWeb()))

endpoint = endpoints.TCP4ServerEndpoint(reactor, 5001)
endpoint.listen(AnsibleTransportFactory())

reactor.run()
