/* Offline renderer for review and tests. This program is never installed and
 * has no Wayland connection, authentication backend, or ability to unlock. */
#include <getopt.h>
#include <stdlib.h>
#include <string.h>
#include "ui.h"

static uint32_t color(const char *s) {
	if (*s == '#') s++;
	return ((uint32_t)strtoul(s, NULL, 16) << 8) | 0xff;
}

int main(int argc, char **argv) {
	struct lock_view v = { .font = "monospace", .now = time(NULL),
		.colors = { .background = 0x101313ff, .foreground = 0xffffffff,
			.surface = 0x181b1bff, .accent = 0x92a58eff,
			.muted = 0xa3aba3ff, .error = 0xeaa08aff } };
	int width = 1920, height = 1080;
	const char *image_path = NULL;
	enum background_mode mode = BACKGROUND_MODE_FILL;
	enum { STATE = 256, COUNT, WIDTH, HEIGHT, FONT, BACKGROUND, FOREGROUND,
		SURFACE, ACCENT, MUTED, ERROR, IMAGE, MODE, SHAKE, TIME, CAPS };
	static const struct option options[] = {
		{"state", required_argument, NULL, STATE}, {"count", required_argument, NULL, COUNT},
		{"width", required_argument, NULL, WIDTH}, {"height", required_argument, NULL, HEIGHT},
		{"font", required_argument, NULL, FONT}, {"background", required_argument, NULL, BACKGROUND},
		{"foreground", required_argument, NULL, FOREGROUND}, {"surface", required_argument, NULL, SURFACE},
		{"accent", required_argument, NULL, ACCENT}, {"muted", required_argument, NULL, MUTED},
		{"error", required_argument, NULL, ERROR}, {"image", required_argument, NULL, IMAGE},
		{"mode", required_argument, NULL, MODE}, {"shake", required_argument, NULL, SHAKE},
		{"time", required_argument, NULL, TIME}, {"caps-lock", no_argument, NULL, CAPS}, {0},
	};
	int opt;
	while ((opt = getopt_long(argc, argv, "", options, NULL)) != -1) {
		switch (opt) {
		case STATE:
			v.entry = strcmp(optarg, "idle") != 0;
			v.validating = !strcmp(optarg, "checking"); v.retry = !strcmp(optarg, "wrong"); break;
		case COUNT: v.characters = strtoul(optarg, NULL, 10); break;
		case WIDTH: width = atoi(optarg); break;
		case HEIGHT: height = atoi(optarg); break;
		case FONT: v.font = optarg; break;
		case BACKGROUND: v.colors.background = color(optarg); break;
		case FOREGROUND: v.colors.foreground = color(optarg); break;
		case SURFACE: v.colors.surface = color(optarg); break;
		case ACCENT: v.colors.accent = color(optarg); break;
		case MUTED: v.colors.muted = color(optarg); break;
		case ERROR: v.colors.error = color(optarg); break;
		case IMAGE: image_path = optarg; break;
		case MODE: mode = parse_background_mode(optarg); break;
		case SHAKE: v.shake = lock_shake(strtod(optarg, NULL)); break;
		case TIME: v.now = strtoll(optarg, NULL, 10); break;
		case CAPS: v.caps_lock = true; break;
		default: return 1;
		}
	}
	if (optind != argc - 1 || width < 1 || height < 1 || width > 8192 || height > 8192) return 1;
	cairo_surface_t *image = image_path ? load_background_image(image_path) : NULL;
	cairo_surface_t *frame = cairo_image_surface_create(CAIRO_FORMAT_RGB24, width, height);
	cairo_t *cr = cairo_create(frame);
	draw_lock_background(cr, image, mode, v.colors.background, width, height, 1);
	int pane_width = width < 560 ? width : 560, pane_height = height < 320 ? height : 320;
	cairo_translate(cr, (width - pane_width) / 2., (height - pane_height) / 2.);
	draw_lock_view(cr, &v, pane_width, pane_height);
	cairo_status_t status = cairo_surface_write_to_png(frame, argv[optind]);
	cairo_destroy(cr); cairo_surface_destroy(frame);
	if (image) cairo_surface_destroy(image);
	return status != CAIRO_STATUS_SUCCESS;
}
