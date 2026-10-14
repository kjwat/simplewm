CC ?= cc
PKG_CONFIG ?= pkg-config
PREFIX ?= /usr/local
BUILD = build
WLROOTS_PKG ?= $(shell $(PKG_CONFIG) --list-all | awk '/^wlroots(-[0-9.]+)? / {print $$1}' | sort -V | tail -1)
PKGS = $(WLROOTS_PKG) wayland-server xkbcommon libinput xcb xcb-icccm
LOCK_PKGS = wayland-client xkbcommon cairo
LOCK_SRC = $(filter-out lock/preview.c,$(wildcard lock/*.c))
LOCK_HEADERS = $(wildcard lock/include/*.h)
CPPFLAGS += -I. -I$(BUILD) -DWLR_USE_UNSTABLE -DXWAYLAND -D_POSIX_C_SOURCE=200809L -DVERSION=\"0.8.0\"
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wno-unused-parameter -Werror=implicit-function-declaration -Werror=incompatible-pointer-types
LDLIBS = $(shell $(PKG_CONFIG) --libs $(PKGS)) -lm
PROTO_DIR = $(shell $(PKG_CONFIG) --variable=pkgdatadir wayland-protocols)
HEADERS = $(addprefix $(BUILD)/,cursor-shape-v1-protocol.h pointer-constraints-unstable-v1-protocol.h wlr-layer-shell-unstable-v1-protocol.h wlr-output-power-management-unstable-v1-protocol.h xdg-shell-protocol.h)
all: $(BUILD)/simplewm $(BUILD)/simplewm-lock-client
$(BUILD):
	mkdir -p $@
$(BUILD)/simplewm: Makefile simplewm.c config.h config.c desktop.c client.h util.c util.h $(HEADERS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(shell $(PKG_CONFIG) --cflags $(PKGS)) simplewm.c util.c $(LDFLAGS) $(LDLIBS) -o $@
$(BUILD)/cursor-shape-v1-protocol.h: | $(BUILD)
	wayland-scanner enum-header $(PROTO_DIR)/staging/cursor-shape/cursor-shape-v1.xml $@
$(BUILD)/pointer-constraints-unstable-v1-protocol.h: | $(BUILD)
	wayland-scanner enum-header $(PROTO_DIR)/unstable/pointer-constraints/pointer-constraints-unstable-v1.xml $@
$(BUILD)/wlr-layer-shell-unstable-v1-protocol.h: protocols/wlr-layer-shell-unstable-v1.xml | $(BUILD)
	wayland-scanner enum-header $< $@
$(BUILD)/wlr-output-power-management-unstable-v1-protocol.h: protocols/wlr-output-power-management-unstable-v1.xml | $(BUILD)
	wayland-scanner server-header $< $@
$(BUILD)/xdg-shell-protocol.h: | $(BUILD)
	wayland-scanner server-header $(PROTO_DIR)/stable/xdg-shell/xdg-shell.xml $@
$(BUILD)/ext-session-lock-v1-client-protocol.h: | $(BUILD)
	wayland-scanner client-header $(PROTO_DIR)/staging/ext-session-lock/ext-session-lock-v1.xml $@
$(BUILD)/ext-session-lock-v1-protocol.c: | $(BUILD)
	wayland-scanner private-code $(PROTO_DIR)/staging/ext-session-lock/ext-session-lock-v1.xml $@
$(BUILD)/simplewm-lock-client: Makefile $(LOCK_SRC) $(LOCK_HEADERS) $(BUILD)/ext-session-lock-v1-client-protocol.h $(BUILD)/ext-session-lock-v1-protocol.c
	$(CC) -Ilock/include -I$(BUILD) -D_POSIX_C_SOURCE=200809L $(CFLAGS) $(shell $(PKG_CONFIG) --cflags $(LOCK_PKGS)) $(LOCK_SRC) $(BUILD)/ext-session-lock-v1-protocol.c $(LDFLAGS) $(shell $(PKG_CONFIG) --libs $(LOCK_PKGS)) -l:libpam.so.0 -lm -o $@
$(BUILD)/simplewm-lock-preview: lock/preview.c lock/ui.c lock/background-image.c lock/cairo.c lock/log.c $(LOCK_HEADERS) | $(BUILD)
	$(CC) -Ilock/include -D_POSIX_C_SOURCE=200809L $(CFLAGS) $(shell $(PKG_CONFIG) --cflags $(LOCK_PKGS)) lock/preview.c lock/ui.c lock/background-image.c lock/cairo.c lock/log.c $(LDFLAGS) $(shell $(PKG_CONFIG) --libs $(LOCK_PKGS)) -lm -o $@
lock-preview: $(BUILD)/simplewm-lock-preview
install: all
	install -Dm755 $(BUILD)/simplewm $(DESTDIR)$(PREFIX)/bin/simplewm
	install -Dm755 $(BUILD)/simplewm-lock-client $(DESTDIR)$(PREFIX)/bin/simplewm-lock-client
	install -Dm644 config $(DESTDIR)$(PREFIX)/share/simplewm/config
	install -Dm644 README.md $(DESTDIR)$(PREFIX)/share/doc/simplewm/README.md
	install -Dm644 LICENSE $(DESTDIR)$(PREFIX)/share/doc/simplewm/LICENSE
	install -Dm644 LICENSE.swaylock $(DESTDIR)$(PREFIX)/share/doc/simplewm/LICENSE.swaylock
	install -Dm644 LICENSE.pam $(DESTDIR)$(PREFIX)/share/doc/simplewm/LICENSE.pam
	install -Dm644 HELP.txt $(DESTDIR)$(PREFIX)/share/simplewm/HELP.txt
	install -Dm644 simplewm.desktop $(DESTDIR)$(PREFIX)/share/wayland-sessions/simplewm.desktop
	for f in scripts/simplewm-* scripts/simplewmctl scripts/simpleupdate; do install -m755 $$f $(DESTDIR)$(PREFIX)/bin/; done
	install -Dm755 scripts/simpleupdate-target $(DESTDIR)$(PREFIX)/bin/simpleupdate-target
	install -m755 scripts/wallpaper-theme-simplewm.sh $(DESTDIR)$(PREFIX)/bin/
	ln -sfn wallpaper-theme-simplewm.sh $(DESTDIR)$(PREFIX)/bin/wallpaper-theme
	ln -sfn wallpaper-theme-simplewm.sh $(DESTDIR)$(PREFIX)/bin/wallpaper-theme.sh
	install -d $(DESTDIR)$(PREFIX)/share/applications
	install -m644 applications/*.desktop $(DESTDIR)$(PREFIX)/share/applications/
uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/simplewm $(DESTDIR)$(PREFIX)/bin/simplewmctl $(DESTDIR)$(PREFIX)/bin/simpleupdate $(addprefix $(DESTDIR)$(PREFIX)/bin/,$(notdir $(wildcard scripts/simplewm-*)))
	rm -rf $(DESTDIR)$(PREFIX)/share/simplewm $(DESTDIR)$(PREFIX)/share/doc/simplewm
	rm -f $(DESTDIR)$(PREFIX)/share/wayland-sessions/simplewm.desktop
	rm -f $(DESTDIR)$(PREFIX)/bin/wallpaper-theme-simplewm.sh $(DESTDIR)$(PREFIX)/bin/wallpaper-theme
	rm -f $(DESTDIR)$(PREFIX)/libexec/simpleupdate-target
	rm -f $(DESTDIR)$(PREFIX)/bin/simpleupdate-target $(DESTDIR)$(PREFIX)/bin/simplewm-lock-client
clean:
	rm -rf $(BUILD)
.PHONY: all install uninstall clean lock-preview
