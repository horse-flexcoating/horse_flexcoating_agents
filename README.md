# HORSE FLEXCoating Agents

This script was developed in the scope of the [FLEXCoating](http://horse-project.eu/flexcoating) experiment that was part of the [HORSE](http://horse-project.eu) project. It implements two HORSE agents as defined in the HORSE Framework.


## Table of Contents

* [Installation](#installation)
* [Usage](#usage)
* [Credits](#credits)
* [License](#license)


## <a name="installation"></a>Installation

This script runs on Python 3.5.2 and uses the following packages:

* asyncio 3.4.3
* pymodbus 2.2.0
* roslibpy 0.6.0
* websockets 7.0

These can be installed with pip by running.

```console
$ pip install asyncio pymodbus roslibpy websockets
```


## <a name="usage"></a>Usage

Configuration is done inside the script. To execute, simply run:

```console
$ ./agents.py
```

The constructors for each of the classes are:

* __HorseAgent__ (name, address='localhost', port=10282, debug=False)

	The base class for an HORSE agent that implements the communication with an HORSE Middleware broker and provides some useful methods, e.g. to send/receive messages through it.

	* name - Agent name
	* address - Broker address
	* port - Broker port
	* debug - Debug flag

* __DemoAgent__ (name, address='localhost', port=10282, debug=False, duration=5)

	A demonstration agent that waits for a 'task_assigned' message, simulates its execution and replies with a 'task_completed' message.
    
    * duration - Task execution duration

* __PhoXi__ (name='PhoXi', address='localhost', port=10282, debug=False, rb_address='localhost', rb_port=9090, talus_address='localhost', talus_port=8765)

	An agent to interface with the the Photoneo PhoXi XL scanner using the object recognition and localization pipeline developed by INESC TEC as well as with a YRC1000 robot controller through an external socket server. The agent supports the storage of a reference point cloud and the obtaining of the position offset of a second point cloud relative to it. The offset is sent to the robot controller in order to correct a previously taught trajectory.
    
    * rb_address - Rosbridge server address
    * rb_port - Rosbridge server port
    * talus_address - Socket server address
    * talus_port - Socket server port
  
* __SafetyEye__ (name='SafetyEYE', address='localhost', port=10282, debug=False, mb_address='localhost', mb_port=5020, rate=2)

	An agent to interface with the PILZ SafetyEYE safety system through a Modbus TCP/IP server in order to monitor its emergency state.

	* mb_address - Modbus server address
	* mb_port - Modbus server port
	* rate - Monitoring rate in Hz

## <a name="credits"></a>Credits

[pdcribeiro](https://github.com/pdcribeiro)


## <a name="license"></a>License

[Apache License, Version 2.0](http://www.apache.org/licenses/LICENSE-2.0)
