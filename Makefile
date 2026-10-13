CC ?= cc
PKG_CONFIG ?= pkg-config
PREFIX ?= /usr/local
BUILD = build
PKGS = wlroots-0.18 wayland-server xkbcommon libinput xcb xcb-icccm
CPPFLAGS += -I. -I$(BUILD) -DWLR_USE_UNSTABLE -DXWAYLAND -D_POSIX_C_SOURCE=200809L -DVERSION=\"0.8.0\"
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wno-unused-parameter -Werror=implicit-function-declaration -Werror=incompatible-pointer-types
LDLIBS = $(shell $(PKG_CONFIG) --libs $(PKGS)) -lm
PROTO_DIR = $(shell $(PKG_CONFIG) --variable=pkgdatadir wayland-protocols)
HEADERS = $(addprefix $(BUILD)/,cursor-shape-v1-protocol.h pointer-constraints-unstable-v1-protocol.h wlr-layer-shell-unstable-v1-protocol.h wlr-output-power-management-unstable-v1-protocol.h xdg-shell-protocol.h)
all: $(BUILD)/simplewm
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
install: all
	install -Dm755 $(BUILD)/simplewm $(DESTDIR)$(PREFIX)/bin/simplewm
	install -Dm644 config $(DESTDIR)$(PREFIX)/share/simplewm/config
	install -Dm644 README.md $(DESTDIR)$(PREFIX)/share/doc/simplewm/README.md
	install -Dm644 LICENSE $(DESTDIR)$(PREFIX)/share/doc/simplewm/LICENSE
	install -Dm644 HELP.txt $(DESTDIR)$(PREFIX)/share/simplewm/HELP.txt
	install -Dm644 simplewm.desktop $(DESTDIR)$(PREFIX)/share/wayland-sessions/simplewm.desktop
	for f in scripts/simplewm-* scripts/simplewmctl scripts/simpleupdate; do install -m755 $$f $(DESTDIR)$(PREFIX)/bin/; done
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
clean:
	rm -rf $(BUILD)
.PHONY: all install uninstall clean
