/* SimpleWM clock and password presentation. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "ui.h"

static void text(cairo_t *cr, const struct lock_view *v, const char *value,
		double size, double x, double y, uint32_t color) {
	cairo_select_font_face(cr, v->font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
	cairo_set_font_size(cr, size);
	cairo_text_extents_t ext;
	cairo_text_extents(cr, value, &ext);
	cairo_set_source_u32(cr, color);
	cairo_move_to(cr, x - ext.width / 2 - ext.x_bearing, y - ext.height / 2 - ext.y_bearing);
	cairo_show_text(cr, value);
}

double lock_shake(double seconds) {
	if (seconds < 0 || seconds >= .28) return 0;
	double progress = seconds / .28;
	return sin(progress * 6 * 3.141592653589793) * 10 * (1 - progress);
}

void draw_lock_background(cairo_t *cr, cairo_surface_t *image,
		enum background_mode mode, uint32_t background, int width, int height, int scale) {
	cairo_save(cr);
	cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
	cairo_set_source_u32(cr, background | 0xff);
	cairo_paint(cr);
	cairo_set_operator(cr, CAIRO_OPERATOR_OVER);
	if (image && mode != BACKGROUND_MODE_SOLID_COLOR) {
		render_background_image(cr, image, mode, width, height);
		/* A light overall tint leaves the heavily blurred wallpaper visible. */
		cairo_set_source_u32(cr, (background & 0xffffff00) | 77);
		cairo_paint(cr);
	}
	int pane_width = width < 560 * scale ? width : 560 * scale;
	int pane_height = height < 320 * scale ? height : 320 * scale;
	double inner = hypot(pane_width / 2., pane_height / 2.);
	cairo_pattern_t *halo = cairo_pattern_create_radial(width / 2., height / 2.,
		inner, width / 2., height / 2., fmax(inner + 1, fmax(width, height) * .7));
	double r = (background >> 24) / 255., g = ((background >> 16) & 255) / 255.;
	double b = ((background >> 8) & 255) / 255.;
	/* Together with the overall tint, the entire UI pane gets exactly the
	 * 199/255 tint whose worst-case contrast the launcher verifies. */
	cairo_pattern_add_color_stop_rgba(halo, 0, r, g, b, (199. - 77.) / (255. - 77.));
	cairo_pattern_add_color_stop_rgba(halo, 1, r, g, b, 0);
	cairo_set_source(cr, halo);
	cairo_paint(cr);
	cairo_pattern_destroy(halo);
	cairo_restore(cr);
}

void draw_lock_view(cairo_t *cr, const struct lock_view *v, int width, int height) {
	cairo_save(cr);
	cairo_set_antialias(cr, CAIRO_ANTIALIAS_BEST);
	cairo_font_options_t *options = cairo_font_options_create();
	cairo_font_options_set_antialias(options, CAIRO_ANTIALIAS_GRAY);
	cairo_font_options_set_hint_style(options, CAIRO_HINT_STYLE_SLIGHT);
	cairo_set_font_options(cr, options);
	cairo_font_options_destroy(options);
	cairo_translate(cr, width / 2., height / 2.);
	double scale = fmin(1, fmin(width / 480., height / 320.));
	cairo_scale(cr, scale, scale);
	char clock[16], date[64];
	struct tm local;
	localtime_r(&v->now, &local);
	strftime(clock, sizeof(clock), "%H:%M", &local);
	strftime(date, sizeof(date), "%a / %d %b %Y", &local);
	for (char *p = date; *p; ++p) if (*p >= 'a' && *p <= 'z') *p -= 'a' - 'A';
	const struct swaylock_colors *c = &v->colors;
	if (!v->entry) {
		text(cr, v, clock, 100, 0, -12, c->foreground);
		cairo_set_source_u32(cr, c->accent);
		cairo_rectangle(cr, -14, 53, 28, 2);
		cairo_fill(cr);
		text(cr, v, date, 13, 0, 78, c->muted);
		text(cr, v, "type to unlock", 12, 0, 120, c->muted);
	} else {
		text(cr, v, clock, 48, 0, -92, c->foreground);
		text(cr, v, date, 12, 0, -52, c->muted);
		/* Only the field shakes, leaving the clock and rejection text steady. */
		cairo_save(cr);
		cairo_translate(cr, v->shake, 0);
		cairo_rectangle(cr, -180, -26, 360, 52);
		cairo_set_source_u32(cr, c->surface);
		cairo_fill_preserve(cr);
		cairo_set_source_u32(cr, v->retry ? c->error : c->accent);
		cairo_set_line_width(cr, 1);
		cairo_stroke(cr);
		/* Clip a long mask to the entry; show the tail and its caret. */
		cairo_rectangle(cr, -158, -23, 316, 46);
		cairo_clip(cr);
		if (v->characters) {
			char mask[129];
			size_t n = v->characters < 128 ? v->characters : 128;
			memset(mask, '*', n); mask[n] = 0;
			cairo_select_font_face(cr, v->font, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
			cairo_set_font_size(cr, 20);
			cairo_text_extents_t ext;
			cairo_text_extents(cr, mask, &ext);
			double x = fmin(-ext.x_advance / 2, 146 - ext.x_advance);
			cairo_set_source_u32(cr, c->foreground);
			cairo_move_to(cr, x, 8);
			cairo_show_text(cr, mask);
			if (!v->validating) {
				cairo_rectangle(cr, x + ext.x_advance + 4, -10, 1, 20);
				cairo_fill(cr);
			}
		} else {
			text(cr, v, "password", 14, 0, 0, c->muted);
		}
		cairo_restore(cr);
		text(cr, v, v->validating ? "checking..." : v->retry ? "try again" : "enter to unlock",
			12, 0, 56, v->retry ? c->error : c->muted);
		if (v->caps_lock) text(cr, v, "caps lock", 11, 0, 82, c->error);
		if (v->layout) text(cr, v, v->layout, 11, 0, v->caps_lock ? 106 : 82, c->muted);
	}
	cairo_restore(cr);
}
