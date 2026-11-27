PYTHON = python
PIP = pip
# TODO: Read this from and .env file
# 	It should include:
#		- the port to use for the device
#		- the WiFi SSID to use for the device
#		- the Wifi password to use for the device
DEFAULT_PORT = /dev/cu.usbmodem2101
DEFAULT_WIFI_SSID = Xtalkie

ifeq (, $(shell which $(PYTHON) ))
  $(error "PYTHON=$(PYTHON) not found in $(PATH)")
endif

# This may be useless, but it could be useful for the default port detection. Remove it otherwise.
ifeq ($(OS), Darwin)
	IS_MAC := open
else
	IS_MAC := xdg-open
endif

# TODO: Detect if mpremote is installed, and if not, ask the user to install it (use make install)
#	- use this function whenever a target needs to use mpremote.
# TODO: Have a function that lists the available ports and sees 
#	- if the default port is there, 
#	- if the $1 argument is not empty, check if that port is available. 
#	- if not, print an error message and exit.
#	- use this function whenever a target needs to use a port.

.PHONY: install
install:
# From a given version on, one can't really install Python modules in the system's Python.
#	the extra parameter overrides this behaviour, but it is not recommended to use it.
	$(PIP) install -r pc/requirements.txt --break-system-packages

.PHONY: ports
ports:
# Shows the available ports in the system to communicate with the devices.
	$(PYTHON) pc/ports.py

.PHONY: settime
settime:
# Sets the time of the device to the current time of the computer.
	$(PYTHON) pc/settime.py $(or $1,$(DEFAULT_PORT))

.PHONY: clock_probe
clock_probe:
# Probes the clock of the device to see if it is working.
	$(PYTHON) -m mpremote connect $(or $1,$(DEFAULT_PORT)) run tools/clock_probe.py

.PHONY: watch
watch:
# Prints the logs of the device to the console. Survives device resets.
	$(PYTHON) pc/watch.py $(or $1,$(DEFAULT_PORT)) --reset

.PHONY: reset
reset:
# Resets the device. The device will be reset and the logs will be printed to the console. Survives device resets.
	$(PYTHON) -m mpremote connect $(or $1,$(DEFAULT_PORT)) reset

.PHONY: deploy_parent
deploy_parent:
# Deploys the code to the device. The device will be reset and the logs will be printed to the console. Survives device resets.
# TODO: Check if we have everything from the .env file, if so, we may only need an argument if we don't want the "night" param.
	$(PYTHON) pc/deploy.py $(DEFAULT_PORT) parent --ssid $(DEFAULT_WIFI_SSID) --password $1

.PHONY: deploy_child
deploy_child:
# Deploys the code to the device. The device will be reset and the logs will be printed to the console. Survives device resets.
# TODO: Check if we have everything from the .env file, if so, we may only need an argument if we don't want the "night" param.
	$(PYTHON) pc/deploy.py $(DEFAULT_PORT) child --ssid $(DEFAULT_WIFI_SSID) --password $1

.PHONY: help
help:
# Prints this help message.
	@echo "Available targets:"
	@echo "  install: Installs the required Python modules."
	@echo "  ports: Shows the available ports in the system to communicate with the devices."
	@echo "  settime: Sets the time of the device to the current time of the computer. Survives device resets. Usage: make settime [PORT]"
	@echo "  watch: Prints the logs of the device to the console. Survives device resets. Usage: make watch [PORT]"
	@echo "  reset: Resets the device. The device will be reset and the logs will be printed to the console. Survives device resets. Usage: make reset [PORT]"
	@echo "  deploy_parent: Deploys the code to the device. The device will be reset and the logs will be printed to the console. Survives device resets. Usage: make deploy_parent [PORT]"
	@echo "  deploy_child: Deploys the code to the device. The device will be reset and the logs will be printed to the console. Survives device resets. Usage: make deploy_child [PORT]"
	@echo "  help: Prints this help message."
