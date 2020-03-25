# device-app-manager
Component for remotely deploying Applications on Things

## Supported Application Deployments

### Python3 Application

This kind of application is not stored locally and it is destroyed after
execution.

Tarball contents:

- `app.py`: python executable
- `requirements.txt`: python package dependencies file

### R4A Python3 Application

Tarball contents:

- `app.py`: python executable
- `requirements.txt`: python package dependencies file
- `init.conf`: Describes the necessary variables (and their types, but not the values) the app needs to correctly operate.
- `app.info`: Gives information of the application
- `exec.conf`: Scheduling parameters and stored here. This file is used by the
  application scheduler.

Example `init.conf`:

```yaml
params:
  - name: <string>
    type: <type>
    value: <>
  - name: <string>
    type: <type>
    value: <>
```

where `<type>` is an enumeration and supports the following values:

- `string`
- `float`
- `int`
- `array`

Example `app.info`:

```yaml
name: <string>
version: <string>
elsa_version: <string>
description: <string>
tags: <array_of_strings>
```

Example `exec.conf`:

```yaml
priority: <int>
execution_timestamp: <timestamp>
retry: <bool>
max_retries: <int>
```


## Usage

### Application Manager Daemon
```bash
[I] ➜ ./app_manager.py --help
usage: app_manager.py [-h] [--host HOST] [--port PORT] [--vhost VHOST] [--username USERNAME] [--password PASSWORD] [--queue-size QUEUE_SIZE] [--debug [DEBUG]]

Application Manager CLI.

optional arguments:
  -h, --help            show this help message and exit
  --host HOST           AMQP broker host (IP/Hostname)
  --port PORT           AMQP broker listening port
  --vhost VHOST         Virtual host to connect to.
  --username USERNAME   Authentication username
  --password PASSWORD   Authentication password
  --queue-size QUEUE_SIZE
                        Maximum queue size.
  --debug [DEBUG]       Enable debugging

```

Username defines the unique id of the device (`{thing_id}`).

### Start Application Example

An example demonstrating application deployment call can be found in
`examlles/` examples folder.

Usage example:

```bash
./start_app.py \
    --device-id device2 \
    --host 155.207.33.189 \
    --port 5782 \
    --vhost / \
    --debug \
    --app-id test-app
```

### Stop Application Example

An example demonstrating application kill call can be found in
`examlles/` examples folder.

Usage example:

```bash
/stop_app.py \
    --app-id test-app \
    --device-id device2 \
    --host 155.207.33.189 \
    --port 5782 \
    --vhost / \
    --debug
```

## Application Manager Endpoints

### RPC Endpoints

All RPC Endpoints are binded to the `DEFAULT` exchange by default.

- Download Application:
  - URI: `thing.{thing_id}.appmanager.download_app`
  - DataModel:
    - In: `{"app_id": "<application_unique_id>", "app_type": <py3/r4a_ros2_py>, "app_tarball": <BASE64_ENCODED_TARBALL>}`
    - Out: `{"status": <200/404>, "app_id": <application_unique_id>, "error": "<error_message>"}`
- Start Application:
  - URI: `thing.{thing_id}.appmanager.start_app`
  - DataModel:
    - In: `{"app_id": <application_unique_id>}`
    - Out: `{"status": <200/404>, "app_id": <unique_app_id>, "error": "<error_message>"}`
- Stop Application:
  - URI: `thing.{thing_id}.appmanager.stop_app`
  - DataModel:
    - In: `{"app_id": <application_unique_id>}`
    - Out: `{"status": <200/404>, "error": "<error_message>"}`
- Delete Application:
  - URI: `thing.{thing_id}.appmanager.delete_app`
  - DataModel:
    - In: `{"app_id": <application_unique_id>}`
    - Out: `{"status": <200/404>, "error": "<error_message>"}`
- Is Alive:
  - URI: `thing.{thing_id}.appmanager.is_alive`
  - DataModel:
    - In: `{}`
    - Out: `{}`

### Publish Endpoints

All Publish Endpoints are binded to the `amq.topic` exchange by default.

- Heartbeat Frames: Sends heartbeat frames periodically
  - URI: `thing.{thing_id}.appmanager.heartbeat`
  - DataModel: `{}`

- Connected Event: Fires once when connected to the message broker
  - URI: `thing.{thing_id}.appmanager.connected`
  - DataModel: `{}`

- Disconnected Event: Fires once when disconnected from the message broker
  - URI: `thing.{thing_id}.appmanager.disconnected`
  - DataModel: `{}`


## Per Application Endpoints

Each application deployment creates a series of endpoints.

### Publish Endpoints

- Logs: Sends application logs captured from stdout and stderr to a topic.
  - URI: `thing.{thing_id}.app.{app_id}.logs`
  - DataModel: `{"timestamp": <timestamp_ms>, "log_msg": "<LOG_MSG>"}`

- AppStarted Event: Fires once, on application launch.
  - URI: `thing.{thing_id}.app.{app_id}.started`
  - DataModel: `{}`
