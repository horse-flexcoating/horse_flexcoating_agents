#!/usr/bin/env python3

import asyncio
import json
import math
import roslibpy
import socket
import websockets

from copy import deepcopy
from datetime import datetime
from pymodbus.client.sync import ModbusTcpClient


# General HORSE agent
class HorseAgent :

	max_name_len = 0


	# constructor
	def __init__(self, name, address='localhost', port=10282, debug=False) :

		self.name = name
		self.broker_address = address
		self.broker_port = str(port)
		self.debug = debug

		# update maximum name length
		HorseAgent.max_name_len = max(HorseAgent.max_name_len, len(self.name) + 2)


	# connects to server and runs main function
	async def start(self):

		self.log('Starting agent execution...')

		# connect to broker
		uri = 'ws://{}:{}/horse/message'.format(self.broker_address, self.broker_port)
		self.log("Connecting to broker on '{}' as '{}'...".format(uri, self.name))
		self.websocket = await self.attempt(websockets.connect, uri)

		try :

			# register agent with broker
			await self.send('___CONTROL___{"ID":"' + self.name + '","Operation":"connect"}')
			self.log('Connected to broker.')

			# execute main function
			await self.main()
			
		except AgentExecutionAbort :
			self.log('Aborting agent execution...')
		
		finally :
			await self.websocket.close()
		
		self.log('Finished agent execution.')


	# run fun(*args) until valid return or maxed tries; -1 for unlimited tries #TODO ? handle max_fails inside
	async def attempt(self, fun, *args, check=(lambda x : x is not None), max_fails=-1, interval=5, sync=False, **kwargs) :

		count = 0

		while True :

			try :

				result = fun(*args, **kwargs) if sync else await fun(*args, **kwargs) #TODO try to use 'await' when passing function as argument

				if check(result) :
					self.log('Succeeded.')
					return result

			except Exception as e : self.log(e)

			self.log('Failed.')
			count += 1
			if count == max_fails :	break

			self.log( 'Retrying{} in {} seconds...'.format(' ({}/{})'.format(count, max_fails) if max_fails > 0 else '', interval) )
			await asyncio.sleep(interval)

		self.log('Maximum of {} tries exceeded.'.format(max_fails))
		raise AgentExecutionAbort


	# logs msg to terminal, prepended with datetime and agent name
	def log(self, msg, end='\n') :

#		print(str(datetime.now()) + '  ' + ('[' + self.name + ']').ljust(HorseAgent.max_name_len, ' ') + ' ' + str(msg), end=end)
		print( '{}  {} {}'.format( datetime.now(), ('[' + self.name + ']').ljust(HorseAgent.max_name_len, ' '), msg ), end=end )


	# sends a message to the broker
	async def send(self, msg, websocket=None, feedback=True) :
	
		resp = None

		# send message to broker
		await (websocket if websocket else self.websocket).send(msg)
		
		# wait for broker response
		if feedback :
			resp = await self.receive()

		# print message
		if self.debug :
			self.log('Message sent: {}'.format(msg))
			
		return resp


	# waits for a message from the broker
	async def receive(self, websocket=None) :

		msg = await (self.websocket if websocket is None else websocket).recv()

		if self.debug :
			self.log('Message received: {}'.format(msg))

		return msg


	# main function
	async def main(self):

		raise NotImplementedException("HorseAgent derived classes must implement a 'main' method")


	# waits for valid request; -1 for unlimited #TODO receive request from different source
	async def receive_request(self, req_type='request', max_fails=-1, interval=5) :
		
		self.log('Waiting for {}...'.format(req_type))
		
		async def receive_request() :
			return json.loads(await self.receive())
		
		req = await self.attempt(receive_request, check=self.request_valid, max_fails=max_fails, interval=interval)
		
		if req is not None :
			self.log('Received {}.'.format(req_type))

		return req


	# returns true if request is valid
	def request_valid(self, req) :
		
		if req['Topic'] != 'task_assigned' :
			self.log('Unexpected topic: {}'.format(req['Topic']))

		elif req['Type'] != '2' :
			self.log('Unexpected type: {}'.format(req['Type']))

		# elif req['Subtype'] != 'notification' :
		# 	self.log('Unexpected subtype: {}'.format(req['Subtype']))

		else :
			return True
			
		return False
		
		
class AgentExecutionAbort (Exception) :
	pass


# Demo HORSE agent
class DemoAgent (HorseAgent) :


	# constructor
	def __init__(self, name, address='localhost', port=10282, debug=False, duration=5) :

		super().__init__(name, address=address, port=port, debug=debug)
		
		self.task_duration = duration


	# main function
	async def main(self):

		while True :

			# wait for valid request, exit on failure
			self.request = await self.receive_request("'task_assigned' message")

			# simulate task execution
			self.log('Executing task...')
			await asyncio.sleep(self.task_duration)
			self.log('Finished execution.')

			# create response
			resp = deepcopy(self.request)
			resp['Topic'] = 'task_completed'
			resp['SenderID'], resp['Receivers'] = self.request['Receivers'], self.request['SenderID']

			# reply with task_completed message
			await self.send(json.dumps(resp))


# PhoXi HORSE agent
class PhoXi (HorseAgent) :

	# constructor
	def __init__(self,
		name='PhoXi',
		address='localhost', port=10282,
		rb_address='localhost', rb_port=9090,
		talus_address='localhost', talus_port=8765,
		debug=False) :

		super().__init__(name, address=address, port=port, debug=debug)
		
		self.rosbridge_address = rb_address
		self.rosbridge_port = rb_port
		self.rosbridge_client = None
		self.subscriber = None
		self.publisher = None
		
#		self.topic_req_name = topic_req
#		self.topic_req_type = msg_req
#		self.topic_resp_name = topic_resp
#		self.topic_resp_type = msg_resp
		
		self.frame_req_service_name='/phoxi_camera/get_frame'
		self.frame_req_msg_type='phoxi_camera/GetFrame'
		self.frame_resp_topic_name='/phoxi_camera/camera_info'
		self.frame_resp_msg_type='sensor_msgs/CameraInfo'
		self.storage_req_topic_name='/pointcloud_storage/ObjectRecognitionSkill/goal'
		self.storage_req_msg_type='object_recognition_skill_msgs/ObjectRecognitionSkillActionGoal'
		self.storage_resp_topic_name='/pointcloud_storage/ObjectRecognitionSkill/result'
		self.storage_resp_msg_type='object_recognition_skill_msgs/ObjectRecognitionSkillActionResult'
		self.registration_req_topic_name='/pointcloud_registration/ObjectRecognitionSkill/goal'
		self.registration_req_msg_type='object_recognition_skill_msgs/ObjectRecognitionSkillActionGoal'
		self.registration_resp_topic_name='/pointcloud_registration/ObjectRecognitionSkill/result'
		self.registration_resp_msg_type='object_recognition_skill_msgs/ObjectRecognitionSkillActionResult'
		
		self.ros_req = {'header': {'seq': 0, 'stamp': {'secs': 0, 'nsecs': 0}, 'frame_id': ''}, 'goal_id': {'stamp': {'secs': 0, 'nsecs': 0}, 'id': ''}, 'goal': {'objectModel': '', 'clusterIndex': 0}}
		self.ros_resp = None
		
		self.talus_address = talus_address
		self.talus_port = int(talus_port)
		self.talus_client = None


	# main function
	async def main(self):

		try :
	
			# connect to rosbridge
			self.log("Connecting to rosbridge on '{}:{}'...".format(self.rosbridge_address, self.rosbridge_port))
			await self.setup_rosbridge()
			self.log('Connected to rosbridge.')

			# connect to talus server
			self.log("Connecting to TALUS server on '{}:{}'...".format(self.talus_address, self.talus_port))
			self.talus_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			await self.attempt(self.talus_client.connect, (self.talus_address, self.talus_port), check=(lambda x : True), sync=True)
			self.log('Connected to TALUS server.')

			while True :

				# wait for valid request, exit on failure
				req = await self.receive_request("'task_assigned' message")
				self.log("Received request of subtype '{}'".format(req['Subtype']))
				
				self.log(str(req))
				
				# get pointcloud name
				pointcloud_name = str(req['Body']['PointcloudName']) + '.ply'
				self.ros_req['goal']['objectModel'] = pointcloud_name
				self.log("Pointcloud: '{}'".format(pointcloud_name))
				
				self.log('Scanning part...')
				
#				self.ros_resp = self.frame_service.call(roslibpy.ServiceRequest())
				self.frame_service.call(roslibpy.ServiceRequest({'in_': -1}))
				
				# wait for result
				while self.ros_resp is None :
					await asyncio.sleep(0.5)
				
				#TODO wait a bit?		
				
				self.ros_resp = None	

				self.log('Part scanned.')
				
#TODO send pointcloud_name, send get_ref operation

				if req['Subtype'] == 'get_ref_pos' :
					self.publisher = self.storage_publisher

				elif req['Subtype'] == 'get_pos_offset' :
					self.publisher = self.registration_publisher

				else :
					raise AgentExecutionAbort
				
				self.log('Locating part...')

				# publish to goal topic
				self.publisher.publish(roslibpy.Message(self.ros_req))

				# wait for result
				while self.ros_resp is None :
					await asyncio.sleep(0.5)

				self.log(str(self.ros_resp))

#				#TODO parse data from ros message
#				outcome = str(self.ros_resp['result']['outcome']) #TODO json?
#				self.log('Outcome: ' + outcome)

#				#TMP create random data
#				transform = '{"translation": {"x": 1, "y": 2, "z": 3}, "rotation": {"x": 1, "y": 2, "z": 3, "w": 4}}'
#				self.log('Transform: ' + str(transform))

				# create task_completed message
				resp = deepcopy(req)
				resp['Topic'] = 'task_completed' if self.ros_resp['result']['skillStatus'].find('Succeeded') > -1 else 'task_cancelled'
				resp['SenderID'], resp['Receivers'] = req['Receivers'], req['SenderID']
				
				self.log('Part {}.'.format('located' if resp['Topic'] == 'task_completed' else 'localization failed'))
				
				#TMP if get_pos_offset, send data to talus server  #TODO create separate client
				if req['Subtype'] == 'get_pos_offset' and resp['Topic'] == 'task_completed' :
					
					# parse offset
#					offset = deepcopy(self.ros_resp['result']['pose'])
#					offset['orientation'] = self.yaskawa_euler_from_quaternion(self.ros_resp['result']['pose']['orientation'])
#					resp['Topic']['Offset'] = offset
#					offset_str = str(offset)
					offset_str = str(self.ros_resp['result']['pose'])
					
					# send offset to talus server
					self.log('Sending offset to TALUS server...')
					self.talus_client.sendall(bytes(offset_str, 'ascii'))
					self.log('Offset sent.')
					
					# wait for response from talus server
					self.log('Waiting for respose from TALUS server...')
					talus_resp = self.talus_client.recv(len(offset_str)).decode('ascii')
					self.log('{} response received: {}'.format('GOOD' if talus_resp == offset_str else 'BAD', talus_resp))

				self.log(str(resp))

				# send task_completed message to mpms
				await self.send(json.dumps(resp))
				self.log('Task completed.')
				
				self.ros_resp = None
				
		except AgentExecutionAbort : raise

		finally :

			if self.talus_client is not None :
#				await self.talus_client.close()
				self.talus_client.close()

			if self.subscriber is not None :
				self.subscriber.unsubscribe()

			if self.publisher is not None :
				self.publisher.unadvertise()

			if self.rosbridge_client is not None :
				self.rosbridge_client.terminate()


	# sets up rosbridge connection and subscribes/advertises to topics
	async def setup_rosbridge(self) :

		# connect to rosbridge
		self.rosbridge_client = roslibpy.Ros(host=self.rosbridge_address, port=self.rosbridge_port)
		await self.attempt(self.rosbridge_client.run, check=(lambda x : self.rosbridge_client.is_connected), sync=True, timeout=1)

		# create client for frame service
		self.frame_service = roslibpy.Service(self.rosbridge_client, self.frame_req_service_name, self.frame_req_msg_type)

		# subscribe to frame topic
		self.frame_subscriber = roslibpy.Topic(self.rosbridge_client, self.frame_resp_topic_name, self.frame_resp_msg_type)
		self.frame_subscriber.subscribe(lambda msg: self.subscriber_callback(msg))

		# setup publisher for storage goal topic
		self.storage_publisher = roslibpy.Topic(self.rosbridge_client, self.storage_req_topic_name, self.storage_req_msg_type)
		self.storage_publisher.advertise()

		# subscribe to storage result topic
		self.storage_subscriber = roslibpy.Topic(self.rosbridge_client, self.storage_resp_topic_name, self.storage_resp_msg_type)
		self.storage_subscriber.subscribe(lambda msg: self.subscriber_callback(msg))

		# setup publisher for registration goal topic
		self.registration_publisher = roslibpy.Topic(self.rosbridge_client, self.registration_req_topic_name, self.registration_req_msg_type)
		self.registration_publisher.advertise()

		# subscribe to registration result topic
		self.registration_subscriber = roslibpy.Topic(self.rosbridge_client, self.registration_resp_topic_name, self.registration_resp_msg_type)
		self.registration_subscriber.subscribe(lambda msg: self.subscriber_callback(msg))
		
#		#TODO ? subscribe to tf
#		roslibpy.tf.TFClient(


	# saves response message
	def subscriber_callback(self, msg) :

		self.ros_resp = msg


	# converts quaternion to zyx euler angles
	def yaskawa_euler_from_quaternion(q) :

		angles = {}

		# roll (x-axis rotation)
		sinr_cosp = +2.0 * (q['w'] * q['x'] + q['y'] * q['z'])
		cosr_cosp = +1.0 - 2.0 * (q['x'] * q['x'] + q['y'] * q['y'])
		angles['x'] = math.atan2(sinr_cosp, cosr_cosp)

		# pitch (y-axis rotation)
		sinp = +2.0 * (q['w'] * q['y'] - q['z'] * q['x'])
		if (abs(sinp) >= 1) :
		    angles['y'] = math.copysign(math.pi / 2, sinp)  # use 90 degrees if out of range
		else :
		    angles['y'] = math.asin(sinp)

		# yaw (z-axis rotation)
		siny_cosp = +2.0 * (q['w'] * q['z'] + q['x'] * q['y'])
		cosy_cosp = +1.0 - 2.0 * (q['y'] * q['y'] + q['z'] * q['z'])  
		angles['z'] = math.atan2(siny_cosp, cosy_cosp)

		return angles


# SafetyEYE HORSE agent
class SafetyEye (HorseAgent) :

	# constructor
	def __init__(self, name='SafetyEYE', address='localhost', port=10282, mb_address='localhost', mb_port=5020, rate=2, debug=False) :

		super().__init__(name, address=address, port=port, debug=debug)
		
		self.modbus_address = mb_address
		self.modbus_port = str(mb_port)
		self.read_interval = 1 / rate


	# main function
	async def main(self):

		# connect to safetyplc modbus server
		uri = '{}:{}'.format(self.modbus_address, self.modbus_port)
		self.log("Connecting to modbus server on '{}'...".format(uri))
		self.modbus_client = ModbusTcpClient(self.modbus_address, self.modbus_port)
		await self.attempt(self.modbus_client.connect, check=(lambda x : x is True), sync=True)
		self.log('Connected to modbus server.')

		try :

			# wait for valid request, exit on failure
			self.request = await self.receive_request("'connection_requested' message")

			# send emergency state updates to mpms
			self.log('Monitoring...')
			old_coil = True
			while True :

				# read coil from SafePLC
				coil = self.modbus_client.read_coils(0,1).bits[0]

				# if changed, send to mpms
				if coil != old_coil :

					# create message
					msg = deepcopy(self.request)
					msg['Topic'] = 'emergency_disabled' if coil else 'emergency_enabled' 
					msg['SenderID'], msg['Receivers'] = self.request['Receivers'], self.request['SenderID']
	
					await self.send(json.dumps(msg))

					self.log(('Left' if coil else 'Entered') + ' emergency state.')

				old_coil = coil

				await asyncio.sleep(self.read_interval)

		finally :
		
			self.modbus_client.close()
			

	# returns true if request is valid
	def request_valid(self, req) :
		
		if req['Topic'] != 'connection_requested' :
			self.log('Unexpected topic: ' + req['Topic'])

		elif req['Type'] != '3' :
			self.log('Unexpected type: ' + req['Type'])

		elif req['Subtype'] != 'safety' :
			self.log('Unexpected subtype: ' + req['Subtype'])

		else :
			return True
			
		return False


# main block
if __name__ == '__main__' :

	# create agents
#	sensor = DemoAgent('PhoXi')
	sensor = PhoXi()
	safety = SafetyEye()
#	sensor = PhoXi(talus_address='192.168.123.2', talus_port=11000)
#	safety = SafetyEye(mb_address='127.0.0.1', mb_port=5020)

	# run agents asynchronously
	loop = asyncio.get_event_loop()
	loop.run_until_complete(asyncio.gather( sensor.start(), safety.start() ))
#	loop.run_until_complete(safety.start())
	loop.close()

