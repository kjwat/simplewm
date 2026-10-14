#include <errno.h>
#include <poll.h>
#include <stdlib.h>
#include <sys/timerfd.h>
#include <unistd.h>
#include "log.h"
#include "loop.h"
#include "ui.h"

static void frame_done(void *data, struct wl_callback *callback, uint32_t time) {
	struct swaylock_surface *surface = data;
	wl_callback_destroy(callback);
	surface->frame = NULL;
	render(surface);
}
static const struct wl_callback_listener frame_listener = { .done = frame_done };

void render(struct swaylock_surface *surface) {
	if (!surface->created || !surface->width || !surface->height ||
		!surface->dirty || surface->frame || surface->scale < 1) return;
	struct swaylock_state *state = surface->state;
	int width = surface->width * surface->scale, height = surface->height * surface->scale;
	struct pool_buffer background = {0};
	bool changed = width != surface->last_buffer_width || height != surface->last_buffer_height;
	if (changed) {
		if (!create_buffer(state->shm, &background, width, height, WL_SHM_FORMAT_ARGB8888)) {
			swaylock_log(LOG_ERROR, "Cannot allocate lock background");
			exit(EXIT_FAILURE);
		}
		draw_lock_background(background.cairo, surface->image, state->args.mode,
			state->args.colors.background, width, height, surface->scale);
		wl_surface_set_buffer_scale(surface->surface, surface->scale);
		wl_surface_attach(surface->surface, background.buffer, 0, 0);
		wl_surface_damage_buffer(surface->surface, 0, 0, INT32_MAX, INT32_MAX);
		surface->last_buffer_width = width; surface->last_buffer_height = height;
	}
	int pane_width = surface->width < 560 ? surface->width : 560;
	int pane_height = surface->height < 320 ? surface->height : 320;
	struct pool_buffer *buffer = get_next_buffer(state->shm, surface->indicator_buffers,
		pane_width * surface->scale, pane_height * surface->scale);
	if (buffer) {
		struct timespec now;
		clock_gettime(CLOCK_MONOTONIC, &now);
		double elapsed = now.tv_sec - state->shake_started.tv_sec +
			(now.tv_nsec - state->shake_started.tv_nsec) / 1e9;
		const char *layout = NULL;
		if (state->xkb.keymap && xkb_keymap_num_layouts(state->xkb.keymap) > 1) {
			xkb_layout_index_t index = xkb_state_serialize_layout(state->xkb.state, XKB_STATE_LAYOUT_EFFECTIVE);
			layout = xkb_keymap_layout_get_name(state->xkb.keymap, index);
		}
		struct lock_view view = {
			.colors = state->args.colors, .font = state->args.font, .layout = layout,
			.now = time(NULL), .entry = state->entry_visible,
			.validating = state->auth_state == AUTH_STATE_VALIDATING,
			.retry = state->retry_visible, .caps_lock = state->xkb.caps_lock,
			.characters = state->auth_state == AUTH_STATE_VALIDATING ?
				state->submitted_characters : state->password.characters,
			.shake = state->retry_visible ? lock_shake(elapsed) : 0,
		};
		cairo_t *cr = buffer->cairo;
		cairo_identity_matrix(cr);
		cairo_set_operator(cr, CAIRO_OPERATOR_SOURCE);
		cairo_set_source_rgba(cr, 0, 0, 0, 0); cairo_paint(cr);
		cairo_set_operator(cr, CAIRO_OPERATOR_OVER);
		cairo_scale(cr, surface->scale, surface->scale);
		draw_lock_view(cr, &view, pane_width, pane_height);
		wl_subsurface_set_position(surface->subsurface,
			(surface->width - pane_width) / 2, (surface->height - pane_height) / 2);
		wl_surface_set_buffer_scale(surface->child, surface->scale);
		wl_surface_attach(surface->child, buffer->buffer, 0, 0);
		wl_surface_damage_buffer(surface->child, 0, 0, INT32_MAX, INT32_MAX);
		wl_surface_commit(surface->child);
		surface->dirty = false;
	}
	surface->frame = wl_surface_frame(surface->surface);
	wl_callback_add_listener(surface->frame, &frame_listener, surface);
	wl_surface_commit(surface->surface);
	if (changed) destroy_buffer(&background);
}

static void clock_tick(int fd, short mask, void *data) {
	uint64_t ticks;
	/* ECANCELED on a wall-clock adjustment also redraws and rearms the timer. */
	ssize_t result = read(fd, &ticks, sizeof(ticks));
	if (result < 0 && errno != ECANCELED && errno != EAGAIN) {
		swaylock_log_errno(LOG_ERROR, "Clock timer failed"); exit(EXIT_FAILURE);
	}
	damage_state(data);
	struct itimerspec timer = { .it_value.tv_sec = (time(NULL) / 60 + 1) * 60 };
	if (timerfd_settime(fd, TFD_TIMER_ABSTIME | TFD_TIMER_CANCEL_ON_SET, &timer, NULL) < 0) {
		swaylock_log_errno(LOG_ERROR, "Cannot schedule lock clock"); exit(EXIT_FAILURE);
	}
}

void start_clock(struct swaylock_state *state) {
	/* Realtime timers expire across suspend and catch manual/NTP clock changes. */
	int fd = timerfd_create(CLOCK_REALTIME, TFD_CLOEXEC | TFD_NONBLOCK);
	if (fd < 0) { swaylock_log_errno(LOG_ERROR, "Cannot create lock clock"); exit(EXIT_FAILURE); }
	loop_add_fd(state->eventloop, fd, POLLIN, clock_tick, state);
	clock_tick(fd, 0, state);
}

static void shake_tick(void *data) {
	struct swaylock_state *state = data;
	state->shake_timer = NULL;
	damage_state(state);
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	double elapsed = now.tv_sec - state->shake_started.tv_sec +
		(now.tv_nsec - state->shake_started.tv_nsec) / 1e9;
	if (elapsed < .28 && state->retry_visible)
		state->shake_timer = loop_add_timer(state->eventloop, 16, shake_tick, state);
}

void start_rejection(struct swaylock_state *state) {
	state->entry_visible = state->retry_visible = true;
	state->submitted_characters = 0;
	clock_gettime(CLOCK_MONOTONIC, &state->shake_started);
	if (state->shake_timer) loop_remove_timer(state->eventloop, state->shake_timer);
	state->shake_timer = loop_add_timer(state->eventloop, 16, shake_tick, state);
}
