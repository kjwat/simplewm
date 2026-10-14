#ifndef SIMPLEWM_LOCK_UI_H
#define SIMPLEWM_LOCK_UI_H
#include "swaylock.h"

/* Only counts and status cross into drawing code; it never receives a password. */
struct lock_view {
	struct swaylock_colors colors;
	const char *font, *layout;
	time_t now;
	size_t characters;
	bool entry, validating, retry, caps_lock;
	double shake;
};
void draw_lock_background(cairo_t *cr, cairo_surface_t *image,
	enum background_mode mode, uint32_t background, int width, int height, int scale);
void draw_lock_view(cairo_t *cr, const struct lock_view *view, int width, int height);
double lock_shake(double seconds);
#endif
