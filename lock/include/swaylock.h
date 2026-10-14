#ifndef _SWAYLOCK_H
#define _SWAYLOCK_H
#include <stdbool.h>
#include <stdint.h>
#include <time.h>
#include <wayland-client.h>
#include "background-image.h"
#include "cairo.h"
#include "pool-buffer.h"
#include "seat.h"

enum auth_state { AUTH_STATE_IDLE, AUTH_STATE_VALIDATING, AUTH_STATE_INVALID };
enum input_state {
	INPUT_STATE_IDLE, INPUT_STATE_CLEAR, INPUT_STATE_LETTER,
	INPUT_STATE_BACKSPACE, INPUT_STATE_NEUTRAL,
};

struct swaylock_colors {
	uint32_t background, foreground, surface, accent, muted, error;
};

struct swaylock_args {
	struct swaylock_colors colors;
	enum background_mode mode;
	char *font;
	bool ignore_empty, daemonize;
	int ready_fd;
};

struct swaylock_password {
	size_t len, buffer_len, characters;
	char *buffer;
};

struct swaylock_state {
	struct loop *eventloop;
	struct loop_timer *input_idle_timer, *auth_idle_timer, *clear_password_timer;
	struct loop_timer *shake_timer;
	struct timespec shake_started;
	struct wl_display *display;
	struct wl_compositor *compositor;
	struct wl_subcompositor *subcompositor;
	struct wl_shm *shm;
	struct wl_list surfaces, images;
	struct swaylock_args args;
	struct swaylock_password password;
	struct swaylock_xkb xkb;
	enum auth_state auth_state;
	enum input_state input_state;
	size_t submitted_characters;
	int failed_attempts;
	bool run_display, locked, authenticated, entry_visible, retry_visible;
	struct ext_session_lock_manager_v1 *ext_session_lock_manager_v1;
	struct ext_session_lock_v1 *ext_session_lock_v1;
};

struct swaylock_surface {
	cairo_surface_t *image;
	struct swaylock_state *state;
	struct wl_output *output;
	uint32_t output_global_name;
	struct wl_surface *surface, *child;
	struct wl_subsurface *subsurface;
	struct ext_session_lock_surface_v1 *ext_session_lock_surface_v1;
	struct pool_buffer indicator_buffers[2];
	bool created, dirty;
	uint32_t width, height;
	int32_t scale;
	enum wl_output_subpixel subpixel;
	char *output_name;
	struct wl_list link;
	struct wl_callback *frame;
	int last_buffer_width, last_buffer_height;
};

struct swaylock_image {
	char *path, *output_name;
	cairo_surface_t *cairo_surface;
	struct wl_list link;
};

void swaylock_handle_key(struct swaylock_state *state, xkb_keysym_t keysym, uint32_t codepoint);
void render(struct swaylock_surface *surface);
void damage_state(struct swaylock_state *state);
void clear_password_buffer(struct swaylock_password *pw);
void schedule_auth_idle(struct swaylock_state *state);
void start_clock(struct swaylock_state *state);
void start_rejection(struct swaylock_state *state);
void initialize_pw_backend(int argc, char **argv);
void run_pw_backend_child(void);
void clear_buffer(char *buf, size_t size);
#endif
