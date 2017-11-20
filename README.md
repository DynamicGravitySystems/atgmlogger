Dynamic Gravity Systems - Serial Data Recorder
==============================================

1. Dependencies:
 	- Python v3.5, 3.6 and the following modules:
		- pyserial >= 3.3
		- jinja2 >= 2.9.6
		- MarkupSafe == 1.0
		- PyYAML == 3.12
		- RPi.GPIO == 0.6.3
	- The following system packages are required for full functionality of the USB data copying:
		- ntfs-3g
		- exfat-fuse
		- exfat-utils
2. Preparing the Raspberry Pi:
	1. Installing Python3.6 from source:
		- Download Python3.6 source tarball from https://www.python.org 
		- Install the required development libraries to build the source:
			- make
			- build-essential
			- libssl-dev
			- zliblg-dev
			- libbz2-dev
			- libreadline-dev
			- libsqlite3-dev
			- wget
			- curl
			- llvm
			- libncurses5-dev
			- libncursesw5-dev
			- xz-utils
			- tk-dev
		```commandline
		sudo apt-get install -y make build-essential libssl-dev zlib1g-dev   
		sudo apt-get install -y libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm 
		sudo apt-get install -y libncurses5-dev  libncursesw5-dev xz-utils tk-dev
		```
		- Extract, Configure and Build:
		```commandline
		tar -xzf python-3.6.2.tgz 
		cd python-3.6.2
		./configure
		make
		sudo make altinstall
		```
	
	2. Installing Python3.6 (armhf) from precompiled binary:
		- e.g. Built on another raspberry pi and zipped.
	3. **Configure Raspberry Pi GPIO Console:**
		- By default the Raspberry Pi GPIO console is enabled as a TTY terminal, this needs to be disabled to allow it 
		to be used as a Serial Data input.
		- Modify /boot/cmdline.txt removing the section similar to: 'console=serial0,115200'
			
			```commandline(bash)
				# All Commands executed as Root (sudo)
				sed -i -e s/console=serial0,115200//g /boot/cmdline.txt
				echo 'enable_uart=1' >> /boot/config.txt
				systemctl stop serial-getty@ttyS0.service
				systemctl disable serial-getty@ttyS0.service
			``` 
 	
3. Installation:
	Use the provided makefile to install the Serial Data Recorder program on a Raspberry PI microcomputer. (See the code snippet below)
	
```commandline
tar -xzf serial_logger-1.0.tar.gz 
cd serial_logger
sudo make install

sudo systemctl status SerialLogger
  ```
  

Automated Installation with (GNU) Make:
---------------------------------------
Execute the following in the package directory:
```
make install
systemctl start SerialLogger
```

#####Issues:

- Depending on the version of Raspberry Pi, the serial port name (symlink) may vary between /dev/ttyS0 and /dev/ttyAMA0
  - Raspberry Pi Zero - /dev/ttyAMA0
  - Raspberry Pi Zero W (Wireless) - /dev/ttyS0


Manual Installation:
--------------------

Installation Directories (copy the following files to the specified destinations):
  - 90-removable-usb.rules -> /etc/udev/rules.d/90-removable-usb.rules
  - media-removable.mount -> /etc/systemd/system/media-removable.mount
  - SerialLogger.service -> /etc/systemd/system/SerialLogger.service

After installing .mount and .service files run the following commands:
```commandline
sudo systemctl daemon-reload
sudo systemctl enable media-removable.mount
sudo systemctl enable SerialLogger.service
```

Explanation:
- 90-removable-usb.rules creates a UDEV rule that adds a symbolic link to /dev/usbstick when a usb block device (hdd)
is inserted. This symlink is used by the following mount file to mount the filesystem.
- media-removable.mount is a systemd mount unit which instructs systemd to mount /dev/usbstick to /media/removable when
it detects the device 'dev-usbstick.device'. The unit will also dismount the device when it becomes unavailable.
- SerialLogger.service is a systemd service unit which executes the Serial Logging python script. When this unit is
enabled (see above command - systemctl enable SerialLogger.service) the program will be executed upon system startup.
