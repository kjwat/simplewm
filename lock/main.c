/* Session-lock lifecycle adapted from swaylock 1.8.2; see LICENSE.swaylock. */
#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include "background-image.h"
#include "cairo.h"
#include "comm.h"
#include "log.h"
#include "loop.h"
#include "password-buffer.h"
#include "pool-buffer.h"
#include "seat.h"
#include "swaylock.h"
#include "ext-session-lock-v1-client-protocol.h"

int lenient_strcmp(char *a, char *b) {
	if (a == b) {
		return 0;
	} else if (!a) {
		return -1;
	} else if (!b) {
		return 1;
	} else {
		return strcmp(a, b);
	}
}

static void daemonize(void) {
	int fds[2];
	if (pipe(fds) != 0) {
		swaylock_log(LOG_ERROR, "Failed to pipe");
		exit(1);
	}
	if (fork() == 0) {
		setsid();
		close(fds[0]);
		int devnull = open("/dev/null", O_RDWR);
		if (devnull < 0) exit(1);
		dup2(devnull, STDIN_FILENO);
		dup2(devnull, STDOUT_FILENO);
		dup2(devnull, STDERR_FILENO);
		close(devnull);
		uint8_t success = 0;
		if (chdir("/") != 0) {
			write(fds[1], &success, 1);
			exit(1);
		}
		success = 1;
		if (write(fds[1], &success, 1) != 1) {
			exit(1);
		}
		close(fds[1]);
	} else {
		close(fds[1]);
		uint8_t success;
		if (read(fds[0], &success, 1) != 1 || !success) {
			swaylock_log(LOG_ERROR, "Failed to daemonize");
			exit(1);
		}
		close(fds[0]);
		exit(0);
	}
}

static void destroy_surface(struct swaylock_surface *surface) {
	wl_list_remove(&surface->link);
	if (surface->ext_session_lock_surface_v1 != NULL) {
		ext_session_lock_surface_v1_destroy(surface->ext_session_lock_surface_v1);
	}
	if (surface->subsurface) {
		wl_subsurface_destroy(surface->subsurface);
	}
	if (surface->child) {
		wl_surface_destroy(surface->child);
	}
	if (surface->surface != NULL) {
		wl_surface_destroy(surface->surface);
	}
	if (surface->frame) wl_callback_destroy(surface->frame);
	destroy_buffer(&surface->indicator_buffers[0]);
	destroy_buffer(&surface->indicator_buffers[1]);
	wl_output_release(surface->output);
	free(surface->output_name);
	free(surface);
}

static const struct ext_session_lock_surface_v1_listener ext_session_lock_surface_v1_listener;

static cairo_surface_t *select_image(struct swaylock_state *state,
		struct swaylock_surface *surface);

static bool surface_is_opaque(struct swaylock_surface *surface) {
	if (surface->image) {
		return cairo_surface_get_content(surface->image) == CAIRO_CONTENT_COLOR;
	}
	return (surface->state->args.colors.background & 0xff) == 0xff;
}

static void create_surface(struct swaylock_surface *surface) {
	struct swaylock_state *state = surface->state;

	surface->image = select_image(state, surface);

	surface->surface = wl_compositor_create_surface(state->compositor);
	assert(surface->surface);

	surface->child = wl_compositor_create_surface(state->compositor);
	assert(surface->child);
	surface->subsurface = wl_subcompositor_get_subsurface(state->subcompositor, surface->child, surface->surface);
	assert(surface->subsurface);
	wl_subsurface_set_sync(surface->subsurface);

	surface->ext_session_lock_surface_v1 = ext_session_lock_v1_get_lock_surface(
		state->ext_session_lock_v1, surface->surface, surface->output);
	ext_session_lock_surface_v1_add_listener(surface->ext_session_lock_surface_v1,
		&ext_session_lock_surface_v1_listener, surface);

	if (surface_is_opaque(surface) &&
			surface->state->args.mode != BACKGROUND_MODE_CENTER &&
			surface->state->args.mode != BACKGROUND_MODE_FIT) {
		struct wl_region *region =
			wl_compositor_create_region(surface->state->compositor);
		wl_region_add(region, 0, 0, INT32_MAX, INT32_MAX);
		wl_surface_set_opaque_region(surface->surface, region);
		wl_region_destroy(region);
	}

	surface->created = true;
}

static void ext_session_lock_surface_v1_handle_configure(void *data,
		struct ext_session_lock_surface_v1 *lock_surface, uint32_t serial,
		uint32_t width, uint32_t height) {
	struct swaylock_surface *surface = data;
	surface->width = width;
	surface->height = height;
	ext_session_lock_surface_v1_ack_configure(lock_surface, serial);
	surface->dirty = true;
	render(surface);
}

static const struct ext_session_lock_surface_v1_listener ext_session_lock_surface_v1_listener = {
	.configure = ext_session_lock_surface_v1_handle_configure,
};

void damage_state(struct swaylock_state *state) {
	struct swaylock_surface *surface;
	wl_list_for_each(surface, &state->surfaces, link) {
		surface->dirty = true;
		render(surface);
	}
}

static void handle_wl_output_geometry(void *data, struct wl_output *wl_output,
		int32_t x, int32_t y, int32_t width_mm, int32_t height_mm,
		int32_t subpixel, const char *make, const char *model,
		int32_t transform) {
	struct swaylock_surface *surface = data;
	surface->subpixel = subpixel;
	if (surface->state->run_display) {
		surface->dirty = true;
		render(surface);
	}
}

static void handle_wl_output_mode(void *data, struct wl_output *output,
		uint32_t flags, int32_t width, int32_t height, int32_t refresh) {
	// Who cares
}

static void handle_wl_output_done(void *data, struct wl_output *output) {
	struct swaylock_surface *surface = data;
	if (!surface->created && surface->state->run_display) {
		create_surface(surface);
	}
}

static void handle_wl_output_scale(void *data, struct wl_output *output,
		int32_t factor) {
	struct swaylock_surface *surface = data;
	surface->scale = factor;
	if (surface->state->run_display) {
		surface->dirty = true;
		render(surface);
	}
}

static void handle_wl_output_name(void *data, struct wl_output *output,
		const char *name) {
	struct swaylock_surface *surface = data;
	surface->output_name = strdup(name);
}

static void handle_wl_output_description(void *data, struct wl_output *output,
		const char *description) {
	// Who cares
}

struct wl_output_listener _wl_output_listener = {
	.geometry = handle_wl_output_geometry,
	.mode = handle_wl_output_mode,
	.done = handle_wl_output_done,
	.scale = handle_wl_output_scale,
	.name = handle_wl_output_name,
	.description = handle_wl_output_description,
};

static void ext_session_lock_v1_handle_locked(void *data, struct ext_session_lock_v1 *lock) {
	struct swaylock_state *state = data;
	state->locked = true;
}

static void ext_session_lock_v1_handle_finished(void *data, struct ext_session_lock_v1 *lock) {
	swaylock_log(LOG_ERROR, "Failed to lock session -- "
			"is another lockscreen running?");
	exit(2);
}

static const struct ext_session_lock_v1_listener ext_session_lock_v1_listener = {
	.locked = ext_session_lock_v1_handle_locked,
	.finished = ext_session_lock_v1_handle_finished,
};

static void handle_global(void *data, struct wl_registry *registry,
		uint32_t name, const char *interface, uint32_t version) {
	struct swaylock_state *state = data;
	if (strcmp(interface, wl_compositor_interface.name) == 0) {
		state->compositor = wl_registry_bind(registry, name,
				&wl_compositor_interface, 4);
	} else if (strcmp(interface, wl_subcompositor_interface.name) == 0) {
		state->subcompositor = wl_registry_bind(registry, name,
				&wl_subcompositor_interface, 1);
	} else if (strcmp(interface, wl_shm_interface.name) == 0) {
		state->shm = wl_registry_bind(registry, name,
				&wl_shm_interface, 1);
	} else if (strcmp(interface, wl_seat_interface.name) == 0) {
		struct wl_seat *seat = wl_registry_bind(
				registry, name, &wl_seat_interface, 4);
		struct swaylock_seat *swaylock_seat =
			calloc(1, sizeof(struct swaylock_seat));
		swaylock_seat->state = state;
		wl_seat_add_listener(seat, &seat_listener, swaylock_seat);
	} else if (strcmp(interface, wl_output_interface.name) == 0) {
		struct swaylock_surface *surface =
			calloc(1, sizeof(struct swaylock_surface));
		surface->state = state;
		surface->scale = 1;
		surface->output = wl_registry_bind(registry, name,
				&wl_output_interface, 4);
		surface->output_global_name = name;
		wl_output_add_listener(surface->output, &_wl_output_listener, surface);
		wl_list_insert(&state->surfaces, &surface->link);
	} else if (strcmp(interface, ext_session_lock_manager_v1_interface.name) == 0) {
		state->ext_session_lock_manager_v1 = wl_registry_bind(registry, name,
				&ext_session_lock_manager_v1_interface, 1);
	}
}

static void handle_global_remove(void *data, struct wl_registry *registry,
		uint32_t name) {
	struct swaylock_state *state = data;
	struct swaylock_surface *surface;
	wl_list_for_each(surface, &state->surfaces, link) {
		if (surface->output_global_name == name) {
			destroy_surface(surface);
			break;
		}
	}
}

static const struct wl_registry_listener registry_listener = {
	.global = handle_global,
	.global_remove = handle_global_remove,
};

static cairo_surface_t *select_image(struct swaylock_state *state,
		struct swaylock_surface *surface) {
	struct swaylock_image *image;
	cairo_surface_t *default_image = NULL;
	wl_list_for_each(image, &state->images, link) {
		if (lenient_strcmp(image->output_name, surface->output_name) == 0) {
			return image->cairo_surface;
		} else if (!image->output_name) {
			default_image = image->cairo_surface;
		}
	}
	return default_image;
}

static struct swaylock_state state;

static uint32_t color_arg(const char *value) {
	const char *p = value[0] == '#' ? value + 1 : value;
	if (strlen(p) != 6) { fprintf(stderr, "Expected an RGB color: %s\n", value); exit(1); }
	for (const char *s = p; *s; s++) if (!isxdigit((unsigned char)*s)) exit(1);
	return ((uint32_t)strtoul(p, NULL, 16) << 8) | 0xff;
}

static void load_image(const char *path) {
	struct swaylock_image *image = calloc(1, sizeof(*image));
	if (!image) exit(EXIT_FAILURE);
	image->path = strdup(path);
	/* Paths are literal: wallpaper names must never undergo shell expansion. */
	image->cairo_surface = load_background_image(path);
	if (!image->cairo_surface) { free(image->path); free(image); return; }
	wl_list_insert(&state.images, &image->link);
}

static void display_in(int fd, short mask, void *data) {
	if (wl_display_dispatch(state.display) == -1) state.run_display = false;
}

static void comm_in(int fd, short mask, void *data) {
	if (mask & POLLIN) {
		bool success = false;
		if (!read_comm_reply(&success)) exit(EXIT_FAILURE);
		if (success) {
			state.authenticated = true;
			state.run_display = false;
		} else {
			state.auth_state = AUTH_STATE_INVALID;
			start_rejection(&state);
			schedule_auth_idle(&state);
			++state.failed_attempts;
			damage_state(&state);
		}
	} else if (mask & (POLLHUP | POLLERR)) {
		swaylock_log(LOG_ERROR, "Password checking process exited");
		exit(EXIT_FAILURE);
	}
}

int main(int argc, char **argv) {
	state.args = (struct swaylock_args){
		.mode = BACKGROUND_MODE_FILL, .font = strdup("monospace"),
		.ignore_empty = true, .ready_fd = -1,
		.colors = { .background = 0x101313ff, .foreground = 0xffffffff,
			.surface = 0x181b1bff, .accent = 0x92a58eff,
			.muted = 0xa3aba3ff, .error = 0xeaa08aff },
	};
	wl_list_init(&state.images);
	wl_list_init(&state.surfaces);
	swaylock_log_init(LOG_ERROR);
	enum { FONT = 256, FOREGROUND, SURFACE, ACCENT, MUTED, ERROR };
	static const struct option options[] = {
		{"daemonize", no_argument, NULL, 'f'}, {"ready-fd", required_argument, NULL, 'R'},
		{"image", required_argument, NULL, 'i'}, {"scaling", required_argument, NULL, 's'},
		{"color", required_argument, NULL, 'c'}, {"font", required_argument, NULL, FONT},
		{"foreground", required_argument, NULL, FOREGROUND}, {"surface", required_argument, NULL, SURFACE},
		{"accent", required_argument, NULL, ACCENT}, {"muted", required_argument, NULL, MUTED},
		{"error", required_argument, NULL, ERROR}, {"debug", no_argument, NULL, 'd'},
		{"help", no_argument, NULL, 'h'}, {"version", no_argument, NULL, 'v'}, {0},
	};
	int option;
	while ((option = getopt_long(argc, argv, "fR:i:s:c:dhv", options, NULL)) != -1) {
		switch (option) {
		case 'f': state.args.daemonize = true; break;
		case 'R': {
			char *end; long fd = strtol(optarg, &end, 10);
			if (!*optarg || *end || fd < 0 || fd > INT32_MAX) return 1;
			state.args.ready_fd = fd; break;
		}
		case 'i': load_image(optarg); break;
		case 's': state.args.mode = parse_background_mode(optarg);
			if (state.args.mode == BACKGROUND_MODE_INVALID) return 1;
			break;
		case 'c': state.args.colors.background = color_arg(optarg); break;
		case FONT: free(state.args.font); state.args.font = strdup(optarg); break;
		case FOREGROUND: state.args.colors.foreground = color_arg(optarg); break;
		case SURFACE: state.args.colors.surface = color_arg(optarg); break;
		case ACCENT: state.args.colors.accent = color_arg(optarg); break;
		case MUTED: state.args.colors.muted = color_arg(optarg); break;
		case ERROR: state.args.colors.error = color_arg(optarg); break;
		case 'd': swaylock_log_init(LOG_DEBUG); break;
		case 'v': puts("simplewm-lock 1.0 (swaylock 1.8.2 core)"); return 0;
		case 'h': puts("Usage: simplewm-lock-client [--daemonize] [--ready-fd FD] [--image PNG]\n"
			"  --scaling fill|fit|center|stretch|tile|solid_color\n"
			"  --font FAMILY --color RGB --foreground RGB --surface RGB\n"
			"  --accent RGB --muted RGB --error RGB"); return 0;
		default: return 1;
		}
	}
	if (optind != argc) return 1;
	initialize_pw_backend(argc, argv);
	state.password.buffer_len = 1024;
	state.password.buffer = password_buffer_create(state.password.buffer_len);
	if (!state.password.buffer) return EXIT_FAILURE;
	state.password.buffer[0] = 0;
	state.xkb.context = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
	state.display = wl_display_connect(NULL);
	if (!state.display) { swaylock_log(LOG_ERROR, "Cannot connect to Wayland"); return 1; }
	state.eventloop = loop_create();
	if (!state.eventloop) return 1;
	struct wl_registry *registry = wl_display_get_registry(state.display);
	wl_registry_add_listener(registry, &registry_listener, &state);
	if (wl_display_roundtrip(state.display) == -1) return 1;
	if (!state.compositor || !state.subcompositor || !state.shm || !state.ext_session_lock_manager_v1) {
		swaylock_log(LOG_ERROR, "Compositor lacks the secure session-lock protocol"); return 1;
	}
	state.ext_session_lock_v1 = ext_session_lock_manager_v1_lock(state.ext_session_lock_manager_v1);
	ext_session_lock_v1_add_listener(state.ext_session_lock_v1, &ext_session_lock_v1_listener, &state);
	if (wl_display_roundtrip(state.display) == -1) return 1;
	struct swaylock_surface *surface;
	wl_list_for_each(surface, &state.surfaces, link) create_surface(surface);
	while (!state.locked) if (wl_display_dispatch(state.display) < 0) return 2;
	/* Receive output configurations and render the first clock before signaling
	 * readiness. A second roundtrip commits the buffers and keyboard focus. */
	if (wl_display_roundtrip(state.display) < 0 || wl_display_roundtrip(state.display) < 0) return 2;
	if (state.args.ready_fd >= 0) {
		if (write(state.args.ready_fd, "\n", 1) != 1) return 2;
		close(state.args.ready_fd); state.args.ready_fd = -1;
	}
	if (state.args.daemonize) daemonize();
	loop_add_fd(state.eventloop, wl_display_get_fd(state.display), POLLIN, display_in, NULL);
	loop_add_fd(state.eventloop, get_comm_reply_fd(), POLLIN, comm_in, NULL);
	state.run_display = true;
	start_clock(&state);
	while (state.run_display) {
		if (wl_display_flush(state.display) == -1 && errno != EAGAIN) break;
		loop_poll(state.eventloop);
	}
	/* Transport failure, a signal, or a crash must never request an unlock. */
	if (!state.authenticated) return EXIT_FAILURE;
	ext_session_lock_v1_unlock_and_destroy(state.ext_session_lock_v1);
	wl_display_roundtrip(state.display);
	password_buffer_destroy(state.password.buffer, state.password.buffer_len);
	free(state.args.font);
	return 0;
}

