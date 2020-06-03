Dynamic Gravity Systems - Serial Data Recorder v0.6.0
=====================================================

1. Dependencies:
 	- Python v3.5 or 3.6 or later, and the following modules:
		- pyserial >= 3.3
		- RPi.GPIO >= 0.6.3
	- The following system packages are required for full functionality of the USB collector copying:
		- ntfs-3g
		- exfat-fuse
		- exfat-utils
            
2. Installation:
    
    - The installation of atgmlogger on a Raspberry Pi requires several supporting configuration changes and updates; 
    to automate the process an ansible playbook is provided: [ATGMLogger Ansible Playbook](https://github.com/DynamicGravitySystems/atgmlogger-ansible)
    
    - In general the following steps are taken to prepare the system:
        1. Configure values in /boot/cmdline.txt and /boot/config.txt to enable UART and disable the TTY on the serial GPIO
        2. Install dependencies that enable the use of NTFS/FAT/EXFAT formatted external devices (for data retrieval)
        3. Add a UDEV rule and systemd mount unit to auto-mount any removable block device (e.g. USB drive) in order to allow copying of logged data for retrieval
        4. Add a logrotate configuration to automatically rotate data and application logs
        5. Install python3 and the ATGMLogger python application
        6. Install a systemd service unit file to control the automatic startup of the ATGMLogger application
        7. Secure the raspberry Pi by changing the default 'pi' user password, and adding an authorized key for factory maintenance usage
    

3. Execution:

    - Once installed with the ansible deploy playbook, ATGMLogger will automatically start every time the system is booted
    via a systemd service unit.
    
    - ATGMLogger can otherwise be manually executed (e.g. for debugging purposes) with the following command
 
        ```commandline
        /usr/bin/python3 -m atgmlogger -vvv
        ```
