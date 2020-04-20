# Examples

Below is the list of examples. We provide one example
for each, provided by the application manager, interface.

- **Get Applications**: Returns the list of installed applications
- **Get Running Applications**: Returns the list of currently running applications
- **Install Application**: Nothing to explain here, the functionality is obvious.
- **Start Application**: Start a previously installed application
- **Stop Application**: Stop a currently running application
- **Delete Application**: Delete an application. Does not terminate the currently running
application instance. Use the **Stop Application** service in case you need such
functionality.

## Get Running Applications Example

Returns a list of the installed applications.

Usage example:

```bash
./get_running_apps.py \
    --device-id device2 \
    --host r4a-platform.ddns.net \
    --port 5782 \
    --vhost / \
    --debug \
```

## Get Applications Example

Returns a list of the installed applications.

Usage example:

```bash
./get_apps.py \
    --device-id device2 \
    --host r4a-platform.ddns.net \
    --port 5782 \
    --vhost / \
    --debug \
```

## Start Application Example

An example demonstrating application deployment call can be found in
`examlles/` examples folder.

Usage example:

```bash
./start_app.py \
    --app-id test-app
    --device-id device2 \
    --host r4a-platform.ddns.net \
    --port 5782 \
    --vhost / \
    --debug \
```

## Stop Application Example

An example demonstrating application kill call can be found in
`examlles/` examples folder.

Usage example:

```bash
./stop_app.py \
    --app-id test-app \
    --device-id device2 \
    --host r4a-platform.ddns.net \
    --port 5782 \
    --vhost / \
    --debug
```

## Install Application Example

Usage example:

```bash
./install_app.py		  \
    --device-id device2		  \
    --fpath app.tar.gz		  \
    --app-type r4a_ros2_py	  \
    --host r4a-platform.ddns.net  \
    --port 5782			  \
    --vhost /			  \
    --debug			  \
```
