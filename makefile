SHELL = /bin/sh
PREFIX = /opt
SYSTEMD = /usr/lib/systemd/system
UDEV = /etc/udev/rules.d

SRCDIR = .
INSTALL = /usr/bin/install -m644
MKDIR = /usr/bin/install -d

# Installation Path for Scripts
BUILD_PATH = $(DESTDIR)$(PREFIX)/SerialLogger
# Installation Path for Systemd unit files
UNIT_PATH = $(DESTDIR)$(SYSTEMD)
# Installation Path for UDEV rules
UDEV_PATH = $(DESTDIR)$(UDEV)

### Define files to be installed ###
BUILD_FILES = $(BUILD_PATH)/SerialLogger.py $(BUILD_PATH)/logging.yaml
SYSTEMD_FILES = $(UNIT_PATH)/SerialLogger.service $(UNIT_PATH)/media-removable.mount
UDEV_FILES = $(UDEV_PATH)/90-removable-storage.rules

$(BUILD_PATH)/SerialLogger.py: $(SRCDIR)/SerialLogger.py
$(BUILD_PATH)/logging.yaml: $(SRCDIR)/logging.yaml
$(UNIT_PATH)/SerialLogger.service: $(SRCDIR)/system/SerialLogger.service
$(UNIT_PATH)/media-removable.mount: $(SRCDIR)/system/media-removable.mount
$(UDEV_PATH)/90-removable-storage.rules: $(SRCDIR)/system/90-removable-storage.rules

### Begin Target Defs ###

.PHONY: all
all: system/SerialLogger.service

system/SerialLogger.service:
        sed 's=@BINDIR@=$(abspath $(BUILD_PATH))=g' $(SRCDIR)/system/SerialLogger.in > $(SRCDIR)/system/SerialLogger.service

.PHONY: install
install: $(BUILD_FILES) $(SYSTEMD_FILES) $(UDEV_FILES)
        systemctl daemon-reload
        systemctl enable media-removable.mount
        systemctl enable SerialLogger.service

$(BUILD_PATH):
        $(MKDIR) $(BUILD_PATH)

$(BUILD_PATH)/%: | $(BUILD_PATH)
        $(INSTALL) $< $@

$(UNIT_PATH):
        $(MKDIR) $(UNIT_PATH)

$(UNIT_PATH)/%: | $(UNIT_PATH)
        $(INSTALL) $< $@

$(UDEV_PATH):
        $(MKDIR) $(UDEV_PATH)

$(UDEV_PATH)/%: | $(UDEV_PATH)
        $(INSTALL) $< $@

.PHONY: clean
clean:
        rm -f $(SRCDIR)/system/SerialLogger.service
