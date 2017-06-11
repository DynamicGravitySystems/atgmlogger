SHELL=/bin/sh
PREFIX=/opt

BUILD_PATH=$(DESTDIR)$(PREFIX)/SerialLogger
SYSD_PATH=$(DESTDIR)/usr/lib/systemd/system

INSTALL_FILES = $(BUILD_PATH)/SerialLogger.py $(BUILD_PATH)/logging.yaml
SYSTEMD_FILES = $(SYSD_PATH)/SerialLogger.service $(SYSD_PATH)/media-removable.mount

.PHONY:install
install: $(INSTALL_FILES) $(SYSTEMD_FILES)
        systemctl daemon-reload

$(BUILD_PATH):
        install -d $(BUILD_PATH)

$(BUILD_PATH)/SerialLogger.py: lib/SerialLogger.py
$(BUILD_PATH)/logging.yaml: lib/logging.yaml
$(BUILD_PATH)/%: | $(BUILD_PATH)
        install -m660 $< $@

$(SYSD_PATH):
        install -d $(SYSD_PATH)

$(SYSD_PATH)/SerialLogger.service: sys/SerialLogger.service
$(SYSD_PATH)/media-removable.mount: sys/media-removable.mount
$(SYSD_PATH)/%: | $(SYSD_PATH)
        install $< $@

