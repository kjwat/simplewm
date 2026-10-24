/* Real xdg-shell clients and a private wlroots backend, with controlled redraws. */
#define main simplewm_main
#include "simplewm.c"
#undef main
#include <assert.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/mman.h>
#include <wayland-client.h>
#include "resize-client-protocol.h"

typedef struct {
	uint32_t serial;
	int width, height;
} Configure;

typedef struct {
	struct wl_display *display;
	struct wl_compositor *compositor;
	struct wl_shm *shm;
	struct xdg_wm_base *shell;
	struct wl_surface *surface;
	struct xdg_surface *xdg;
	struct xdg_toplevel *toplevel;
	Client *client;
	Configure configs[8192];
	int count, completed, drawing, width, height, delay, cell;
	int commits, duplicate_configs, manual;
	int64_t due;
	uint32_t acknowledged;
} Probe;

static Probe probes[2];
static int checking, watching, presents, mismatches, max_backlog;
static struct wl_listener presented;
static struct wl_listener app_configure, app_commit;
static int app_requests, app_commits, app_duplicates;
static Configure app_configs[4096];
static int64_t app_sent[4096], app_latencies[4096];
static int app_latency_count;
static int app_dragging, app_input_count, app_age_count;
static Configure app_inputs[4096];
static int64_t app_input_time[4096], app_target_time[4096], app_ages[4096], app_errors[4096];

static int64_t now_ms(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static void ping(void *data, struct xdg_wm_base *shell, uint32_t serial)
{
	xdg_wm_base_pong(shell, serial);
}
static const struct xdg_wm_base_listener shell_listener = {.ping = ping};

static void global(void *data, struct wl_registry *registry, uint32_t name,
		const char *interface, uint32_t version)
{
	Probe *p = data;
	if (!strcmp(interface, wl_compositor_interface.name))
		p->compositor = wl_registry_bind(registry, name, &wl_compositor_interface, MIN(version, 4));
	else if (!strcmp(interface, wl_shm_interface.name))
		p->shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
	else if (!strcmp(interface, xdg_wm_base_interface.name)) {
		p->shell = wl_registry_bind(registry, name, &xdg_wm_base_interface, MIN(version, 6));
		xdg_wm_base_add_listener(p->shell, &shell_listener, p);
	}
}
static void global_remove(void *data, struct wl_registry *registry, uint32_t name) { }
static const struct wl_registry_listener registry_listener = {global, global_remove};

static void top_configure(void *data, struct xdg_toplevel *top, int32_t width,
		int32_t height, struct wl_array *states)
{
	Probe *p = data;
	p->width = width ? width : 400;
	p->height = height ? height : 260;
}
static void top_close(void *data, struct xdg_toplevel *top) { }
static void top_bounds(void *data, struct xdg_toplevel *top, int32_t width, int32_t height) { }
static void top_caps(void *data, struct xdg_toplevel *top, struct wl_array *caps) { }
static const struct xdg_toplevel_listener top_listener = {
	.configure = top_configure, .close = top_close,
	.configure_bounds = top_bounds, .wm_capabilities = top_caps,
};

static void configured(void *data, struct xdg_surface *surface, uint32_t serial)
{
	Probe *p = data;
	assert(p->count < (int)LENGTH(p->configs));
	if (p->count && p->configs[p->count - 1].width == p->width &&
			p->configs[p->count - 1].height == p->height)
		p->duplicate_configs++;
	p->configs[p->count++] = (Configure){serial, p->width, p->height};
}
static const struct xdg_surface_listener surface_listener = {.configure = configured};

static void released(void *data, struct wl_buffer *buffer) { wl_buffer_destroy(buffer); }
static const struct wl_buffer_listener buffer_listener = {.release = released};

static void commit_config(Probe *p, int index, int acknowledge)
{
	assert(index >= 0 && index < p->count);
	Configure cfg = p->configs[index];
	int w = MAX(1, cfg.width / p->cell * p->cell);
	int h = MAX(1, cfg.height / p->cell * p->cell);
	size_t size = (size_t)w * h * 4;
	int fd = memfd_create("resize-check", MFD_CLOEXEC);
	assert(fd >= 0 && !ftruncate(fd, (off_t)size));
	uint32_t *pixels = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	assert(pixels != MAP_FAILED);
	for (size_t i = 0; i < size / 4; i++)
		pixels[i] = 0xff203040u | ((i / w % 16 < 8) ? 0x00202020u : 0);
	struct wl_shm_pool *pool = wl_shm_create_pool(p->shm, fd, (int)size);
	struct wl_buffer *buffer = wl_shm_pool_create_buffer(pool, 0, w, h, w * 4, WL_SHM_FORMAT_ARGB8888);
	wl_buffer_add_listener(buffer, &buffer_listener, NULL);
	wl_shm_pool_destroy(pool);
	munmap(pixels, size);
	close(fd);
	if (acknowledge && p->acknowledged != cfg.serial) {
		xdg_surface_ack_configure(p->xdg, cfg.serial);
		p->acknowledged = cfg.serial;
	}
	xdg_surface_set_window_geometry(p->xdg, 0, 0, w, h);
	wl_surface_attach(p->surface, buffer, 0, 0);
	wl_surface_damage_buffer(p->surface, 0, 0, w, h);
	wl_surface_commit(p->surface);
	p->completed = index;
	p->commits++;
}

static void client_dispatch(Probe *p)
{
	while (wl_display_prepare_read(p->display))
		assert(wl_display_dispatch_pending(p->display) >= 0);
	assert(wl_display_flush(p->display) >= 0 || errno == EAGAIN);
	struct pollfd fd = {.fd = wl_display_get_fd(p->display), .events = POLLIN};
	assert(poll(&fd, 1, 0) >= 0);
	if (fd.revents & POLLIN)
		assert(wl_display_read_events(p->display) >= 0);
	else
		wl_display_cancel_read(p->display);
	assert(wl_display_dispatch_pending(p->display) >= 0);
}

static void pump(int ms)
{
	for (size_t i = 0; i < LENGTH(probes); i++)
		if (probes[i].display) client_dispatch(&probes[i]);
	assert(wl_event_loop_dispatch(event_loop, ms) >= 0);
	wl_display_flush_clients(dpy);
	for (size_t i = 0; i < LENGTH(probes); i++) {
		Probe *p = &probes[i];
		if (!p->display) continue;
		client_dispatch(p);
		if (watching && i == 0)
			max_backlog = MAX(max_backlog, p->count - p->completed - 1);
		if (p->manual) continue;
		if (p->drawing < 0 && p->count - 1 > p->completed) {
			p->drawing = p->count - 1;
			p->due = now_ms() + p->delay;
		}
		if (p->drawing >= 0 && now_ms() >= p->due) {
			commit_config(p, p->drawing, 1);
			p->drawing = -1;
		}
	}
}

static void pump_for(int ms)
{
	int64_t end = now_ms() + ms;
	do pump(1); while (now_ms() < end);
}

static int coherent(Probe *p)
{
	struct wlr_box actual;
	if (client_is_x11(p->client)) {
		/* XWM geometry is updated when requesting a size, before its buffer. */
		actual.width = client_surface(p->client)->current.width;
		actual.height = client_surface(p->client)->current.height;
	} else {
		client_get_geometry(p->client, &actual);
	}
	return p->client->border[0]->width == actual.width + 2 * (int)p->client->bw &&
		p->client->border[1]->width == actual.width + 2 * (int)p->client->bw &&
		p->client->border[1]->node.y == actual.height + (int)p->client->bw &&
		p->client->border[2]->height == actual.height &&
		p->client->border[3]->height == actual.height &&
		p->client->border[3]->node.x == actual.width + (int)p->client->bw;
}

static void present(struct wl_listener *listener, void *data)
{
	if (watching) {
		presents++;
		if (!coherent(&probes[0])) mismatches++;
		if (app_dragging && app_age_count < (int)LENGTH(app_ages)) {
			Client *c = probes[0].client;
			uint32_t serial = c->surface.xdg->current.configure_serial;
			for (int i = app_requests - 1; i >= 0; i--) {
				if (app_configs[i].serial != serial || app_target_time[i] < 0) continue;
				app_ages[app_age_count] = now_ms() - app_target_time[i];
				app_errors[app_age_count++] = abs(app_configs[i].width - (c->geom.width - 2 * (int)c->bw)) +
					abs(app_configs[i].height - (c->geom.height - 2 * (int)c->bw));
				break;
			}
		}
	}
}

static void init_probe(Probe *p, const char *title)
{
	int fds[2];
	assert(!socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, fds));
	assert(wl_client_create(dpy, fds[0]));
	p->display = wl_display_connect_to_fd(fds[1]);
	assert(p->display);
	p->completed = p->drawing = -1;
	p->cell = 1;
	struct wl_registry *registry = wl_display_get_registry(p->display);
	wl_registry_add_listener(registry, &registry_listener, p);
	for (int i = 0; i < 100 && !p->shell; i++) pump(1);
	assert(p->compositor && p->shm && p->shell);
	p->surface = wl_compositor_create_surface(p->compositor);
	p->xdg = xdg_wm_base_get_xdg_surface(p->shell, p->surface);
	xdg_surface_add_listener(p->xdg, &surface_listener, p);
	p->toplevel = xdg_surface_get_toplevel(p->xdg);
	xdg_toplevel_add_listener(p->toplevel, &top_listener, p);
	xdg_toplevel_set_title(p->toplevel, title);
	xdg_toplevel_set_app_id(p->toplevel, "resize-fixture");
	wl_surface_commit(p->surface);
	for (int i = 0; i < 500 && !p->client; i++) {
		pump(1);
		Client *c;
		wl_list_for_each(c, &clients, link)
			if (!strcmp(client_get_title(c), title)) p->client = c;
	}
	assert(p->client);
	wl_registry_destroy(registry);
}

static void place(Probe *p)
{
	p->manual = p->delay = 0;
	p->cell = 1;
	cursor_mode = CurNormal;
	setfloating(p->client, 1);
	resize(p->client, (struct wlr_box){100, 100, 420, 280}, 1);
	pump_for(100);
	assert(!p->client->resize);
}

static void begin(Probe *p)
{
	wlr_cursor_warp_closest(cursor, NULL, p->client->geom.x + 20, p->client->geom.y + 20);
	moveresize(&(Arg){.ui = CurResize});
	assert(grabc == p->client && cursor_mode == CurResize);
}

static void motion(Probe *p, int width, int height)
{
	motionnotify((uint32_t)now_ms(), NULL,
		p->client->geom.x + width - cursor->x,
		p->client->geom.y + height - cursor->y, 0, 0);
}

static void finish(void)
{
	struct wlr_pointer_button_event event = {.button = BTN_RIGHT,
		.state = WL_POINTER_BUTTON_STATE_RELEASED, .time_msec = (uint32_t)now_ms()};
	buttonpress(NULL, &event);
	assert(cursor_mode == CurNormal);
}

static void tracking(void)
{
	Probe *p = &probes[0];
	place(p);
	p->manual = 1;
	int w = p->client->geom.width - 2 * p->client->bw;
	int h = p->client->geom.height - 2 * p->client->bw;
	p->client->resize = client_set_size(p->client, w + 100, h);
	pump_for(5);
	uint32_t serial = p->client->resize;
	int before = p->count;
	p->client->resize = client_set_size(p->client, w + 100, h);
	pump_for(5);
	int duplicate = p->count - before;
	int preserved = p->client->resize == serial;
	p->client->resize = client_set_size(p->client, w, h);
	pump_for(5);
	int reversed = p->configs[p->count - 1].width == w;
	printf("{\"case\":\"pending_tracking\",\"duplicate_configures\":%d,\"pending_serial_preserved\":%s,\"reversal_sent\":%s}\n",
		duplicate, preserved ? "true" : "false", reversed ? "true" : "false");
	if (checking) assert(!duplicate && preserved && reversed);
	p->manual = 0;
	pump_for(100);
}

static void drive(int delay)
{
	Probe *p = &probes[0];
	place(p);
	begin(p);
	pump_for(50);
	p->delay = delay;
	int before = p->count, duplicate = p->duplicate_configs, commits = p->commits;
	presents = mismatches = max_backlog = 0;
	watching = 1;
	int64_t start = now_ms();
	int inputs = 400;
	for (int i = 0; i < inputs; i++) {
		int phase = i % 120;
		int distance = phase <= 60 ? phase : 120 - phase;
		motion(p, 420 + distance * 3, 280 + distance);
		pump(0);
		while (now_ms() < start + i + 1) pump(1);
	}
	motion(p, 530, 350);
	finish();
	int64_t released_at = now_ms();
	for (int i = 0; i < 1000; i++) {
		pump(1);
		struct wlr_box actual;
		client_get_geometry(p->client, &actual);
		if (actual.width == 530 - 2 * (int)p->client->bw &&
				actual.height == 350 - 2 * (int)p->client->bw && !p->client->resize) break;
	}
	int64_t final_ms = now_ms() - released_at;
	pump_for(30);
	watching = 0;
	printf("{\"case\":\"resize_%dms_client\",\"inputs\":%d,\"configures\":%d,\"duplicate_configures\":%d,\"client_commits\":%d,\"presentations\":%d,\"mismatched_presentations\":%d,\"max_uncommitted_configures\":%d,\"final_settle_ms\":%lld}\n",
		delay, inputs, p->count - before, p->duplicate_configs - duplicate,
		p->commits - commits, presents, mismatches, max_backlog, (long long)final_ms);
	assert(final_ms < 1000);
	if (checking) assert(!mismatches && p->duplicate_configs == duplicate && p->count - before <= inputs + 1);
	p->delay = 0;
}

static void acknowledgements(void)
{
	Probe *p = &probes[0];
	place(p);
	begin(p);
	pump_for(30);
	p->manual = 1;
	int before = p->count;
	motion(p, 520, 320);
	pump_for(5);
	int first = p->count - 1;
	uint32_t first_serial = p->configs[first].serial;
	xdg_surface_ack_configure(p->xdg, first_serial);
	p->acknowledged = first_serial;
	pump_for(10);
	int waits_for_commit = p->client->resize != 0;
	for (int i = 0; i < 20; i++) {
		motion(p, 540 + i, 330 + i);
		pump(1);
	}
	pump_for(30);
	int before_release = p->count - before;
	motion(p, 420, 280); /* Reverse to the still-committed original size. */
	finish();
	pump_for(5);
	int final_sent = p->configs[p->count - 1].width == 420 - 2 * (int)p->client->bw;
	int final_index = p->count - 1;
	commit_config(p, first, 0); /* Commit the already-acknowledged older buffer. */
	pump_for(10);
	int old_commit_keeps_pending = p->client->resize != 0;
	int old_coherent = coherent(p);
	if (!final_sent) final_index = p->count - 1;
	commit_config(p, final_index, 1);
	pump_for(10);
	printf("{\"case\":\"acknowledgement_and_release\",\"waits_for_surface_commit\":%s,\"configures_before_release\":%d,\"final_reversal_sent_on_release\":%s,\"older_commit_keeps_pending\":%s,\"older_buffer_coherent\":%s}\n",
		waits_for_commit ? "true" : "false", before_release,
		final_sent ? "true" : "false", old_commit_keeps_pending ? "true" : "false",
		old_coherent ? "true" : "false");
	if (checking) assert(waits_for_commit && final_sent &&
		old_commit_keeps_pending && old_coherent && !p->client->resize && coherent(p));
	p->manual = 0;
	pump_for(30);
}

static void unsent_and_minimum(void)
{
	Probe *p = &probes[0];
	place(p);
	begin(p);
	pump_for(30);
	p->manual = 1;
	int before = p->count;
	motion(p, 540, 340);
	uint32_t serial = p->client->resize;
	motion(p, 420, 280);
	int retained = serial == p->client->resize && serial != 0;
	pump_for(5);
	int reversed = p->configs[p->count - 1].width == 418;
	printf("{\"case\":\"unsent_reversal\",\"one_configure\":%s,\"serial_preserved\":%s,\"reversal_sent\":%s}\n",
		p->count - before == 1 ? "true" : "false", retained ? "true" : "false",
		reversed ? "true" : "false");
	if (checking) assert(p->count - before == 1 && retained && reversed);
	finish();
	p->manual = 0;
	pump_for(80);
	place(p);
	begin(p);
	pump_for(20);
	motion(p, 1, 1);
	finish();
	pump_for(80);
	struct wlr_box actual;
	client_get_geometry(p->client, &actual);
	assert(actual.width == 1 && actual.height == 1 && !p->client->resize);
	if (checking) assert(coherent(p));
	puts("OK minimum interactive size without invalid configure dimensions");
}

static void stalled(void)
{
	Probe *p = &probes[0], *other = &probes[1];
	place(p);
	begin(p);
	pump_for(30);
	p->manual = 1;
	int before = p->count, other_before = other->commits;
	motion(p, 320, 220);
	pump_for(5);
	Client *hit = NULL;
	xytonode(p->client->geom.x + 405, p->client->geom.y + 30,
		NULL, &hit, NULL, NULL, NULL);
	int old_contents_unclipped = hit == p->client;
	presents = mismatches = 0;
	watching = 1;
	for (int i = 0; i < 60; i++) {
		motion(p, 450 + i, 300 + i);
		if (!(i % 4)) commit_config(other, other->completed, 0);
		pump_for(2);
	}
	finish();
	pump_for(10);
	watching = 0;
	printf("{\"case\":\"stalled_client\",\"configures\":%d,\"other_client_commits\":%d,\"presentations\":%d,\"old_contents_not_prematurely_clipped\":%s}\n",
		p->count - before, other->commits - other_before, presents,
		old_contents_unclipped ? "true" : "false");
	if (checking) assert(p->count - before == 61 && other->commits - other_before >= 15 &&
		presents >= 3 && old_contents_unclipped && coherent(p));
	p->manual = 0;
	pump_for(100);
}

static void constrained_and_tiled(void)
{
	Probe *p = &probes[0];
	place(p);
	p->cell = 8;
	begin(p);
	pump_for(30);
	motion(p, 537, 359);
	finish();
	pump_for(100);
	struct wlr_box actual;
	client_get_geometry(p->client, &actual);
	int cell_coherent = coherent(p);
	printf("{\"case\":\"cell_sized_client\",\"border_matches_committed_geometry\":%s,\"actual_width\":%d,\"actual_height\":%d}\n",
		cell_coherent ? "true" : "false", actual.width, actual.height);
	if (checking) assert(cell_coherent && p->client->geom.width == actual.width + 2 * (int)p->client->bw);
	p->cell = 1;
	for (size_t i = 0; i < LENGTH(probes); i++) setfloating(probes[i].client, 0);
	selmon = p->client->mon;
	setlayout(&(Arg){.v = &layouts[1]});
	setmfact(&(Arg){.f = 0.1f});
	pump_for(120);
	for (size_t i = 0; i < LENGTH(probes); i++) {
		assert(!probes[i].client->resize && !probes[i].client->isfloating);
		assert(coherent(&probes[i]));
	}
	probes[1].delay = 50;
	setmfact(&(Arg){.f = -0.05f});
	pump_for(180);
	for (size_t i = 0; i < LENGTH(probes); i++)
		assert(!probes[i].client->resize && coherent(&probes[i]));
	probes[1].delay = 0;
	puts("OK tiled resizing, two clients, slow tiled client and cell-sized floating buffers");
}

static void independent_clients(void)
{
	Probe *a = &probes[0], *b = &probes[1];
	place(a);
	begin(a);
	pump_for(30);
	a->manual = 1;
	motion(a, 520, 320);
	finish();
	pump_for(5);
	setfloating(b->client, 1);
	resize(b->client, (struct wlr_box){750, 100, 420, 280}, 1);
	pump_for(80);
	begin(b);
	pump_for(20);
	b->manual = 1;
	motion(b, 560, 360);
	pump_for(5);
	uint32_t b_serial = b->client->resize;
	commit_config(a, a->count - 1, 1);
	pump_for(10);
	assert(cursor_mode == CurResize && grabc == b->client && b->client->resize == b_serial);
	if (checking) assert(!a->client->resize && coherent(a) && coherent(b));
	finish();
	a->manual = b->manual = 0;
	pump_for(80);
	assert(!a->client->resize && !b->client->resize);
	puts("OK late commits from one window do not disturb another interactive resize");
}

static void lifecycle(void)
{
	Probe *p = &probes[0];
	place(p);
	begin(p);
	pump_for(30);
	p->manual = 1;
	motion(p, 580, 380);
	pump_for(5);
	wl_surface_attach(p->surface, NULL, 0, 0);
	wl_surface_commit(p->surface);
	pump_for(10);
	assert(cursor_mode == CurNormal && !grabc && !client_surface(p->client)->mapped);
	if (checking) assert(!p->client->resize);
	p->completed = p->count - 1;
	p->drawing = -1;
	p->acknowledged = 0;
	wl_surface_commit(p->surface);
	pump_for(10);
	p->manual = 0;
	pump_for(100);
	assert(client_surface(p->client)->mapped && !p->client->resize);
	place(p);
	begin(p);
	pump_for(20);
	p->manual = 1;
	motion(p, 600, 400);
	pump_for(5);
	xdg_toplevel_destroy(p->toplevel);
	xdg_surface_destroy(p->xdg);
	wl_surface_destroy(p->surface);
	pump_for(30);
	p->client = NULL;
	assert(cursor_mode == CurNormal && !grabc && wl_list_length(&clients) == 1);
	puts("OK unmap/remap and destruction during a pending interactive resize");
}

static Client *find_title(const char *title)
{
	Client *c;
	wl_list_for_each(c, &clients, link)
		if (strstr(client_get_title(c) ? client_get_title(c) : "", title)) return c;
	return NULL;
}

static void app_configured(struct wl_listener *listener, void *data)
{
	struct wlr_xdg_surface_configure *event = data;
	struct wlr_xdg_toplevel_configure *cfg = event->toplevel_configure;
	assert(app_requests < (int)LENGTH(app_configs));
	if (app_requests && app_configs[app_requests - 1].width == cfg->width &&
			app_configs[app_requests - 1].height == cfg->height) app_duplicates++;
	app_configs[app_requests] = (Configure){event->serial, cfg->width, cfg->height};
	app_target_time[app_requests] = -1;
	for (int i = app_input_count - 1; i >= 0; i--)
		if (app_inputs[i].width == cfg->width && app_inputs[i].height == cfg->height) {
			app_target_time[app_requests] = app_input_time[i];
			break;
		}
	app_sent[app_requests++] = now_ms();
}

static void app_committed(struct wl_listener *listener, void *data)
{
	Client *c = probes[0].client;
	if (!watching || !client_surface(c)->mapped) return;
	app_commits++;
	uint32_t serial = c->surface.xdg->current.configure_serial;
	for (int i = app_requests - 1; i >= 0; i--) {
		if (app_configs[i].serial != serial) continue;
		if (app_sent[i] >= 0 && app_latency_count < (int)LENGTH(app_latencies)) {
			app_latencies[app_latency_count++] = now_ms() - app_sent[i];
			app_sent[i] = -1;
		}
		break;
	}
}

static int compare_latency(const void *a, const void *b)
{
	int64_t x = *(const int64_t *)a, y = *(const int64_t *)b;
	return (x > y) - (x < y);
}

static void launch_application(const char *kind, const char *probe_path, int background)
{
	pid_t pid = fork();
	assert(pid >= 0);
	if (pid) return;
	if (background || !strcmp(kind, "gtk") || !strcmp(kind, "x11")) {
		setenv("GDK_BACKEND", !background && !strcmp(kind, "x11") ? "x11" : "wayland", 1);
		execlp("python3", "python3", probe_path, background ? "Resize background" : "Resize GTK", (char *)NULL);
	} else if (!strcmp(kind, "simpleterm")) {
		execlp("simpleterm", "simpleterm", "--title", "Resize terminal", "--", "/bin/sh", "-c",
			"i=0; while [ $i -lt 1000 ]; do printf 'Resize history %s: a paragraph of terminal text to reflow across changing columns.\\n' \"$i\"; i=$((i+1)); done; exec cat",
			(char *)NULL);
	} else {
		execlp("firefox-esr", "firefox-esr", "--no-remote", "--profile", getenv("SIMPLEWM_RESIZE_TEST_PROFILE"),
			"--new-window", getenv("SIMPLEWM_RESIZE_TEST_DOCUMENT"),
			(char *)NULL);
	}
	_exit(127);
}

static void applications(const char *kind, const char *probe_path)
{
	const char *display = wl_display_add_socket_auto(dpy);
	assert(display && !setenv("WAYLAND_DISPLAY", display, 1));
	launch_application(kind, probe_path, 1);
	Client *background = NULL;
	for (int i = 0; i < 3000 && !background; i++) {
		pump(2);
		background = find_title("Resize background");
	}
	assert(background);
	launch_application(kind, probe_path, 0);
	const char *title = !strcmp(kind, "simpleterm") ? "Resize terminal" :
		!strcmp(kind, "firefox") ? "Resize browser" : "Resize GTK";
	Client *c = NULL;
	for (int i = 0; i < 10000 && !c; i++) {
		pump(2);
		c = find_title(title);
		if (!c && !strcmp(kind, "firefox")) {
			Client *candidate;
			wl_list_for_each(candidate, &clients, link)
				if (client_get_appid(candidate) && strcasestr(client_get_appid(candidate), "firefox"))
					c = candidate;
		}
	}
	if (!c) {
		Client *candidate;
		wl_list_for_each(candidate, &clients, link)
			fprintf(stderr, "mapped application: %s / %s\n", client_get_appid(candidate), client_get_title(candidate));
	}
	assert(c);
	if (!strcmp(kind, "firefox")) {
		for (int i = 0; i < 3000 && !find_title(title); i++) pump(1);
		Client *document = find_title(title);
		assert(document && "local browser document did not load");
		c = document;
	}
	probes[0].client = c;
	setmaximized(c, 0);
	setfullscreen(c, 0);
	setfloating(background, 1);
	resize(background, (struct wlr_box){1050, 80, 220, 500}, 1);
	setfloating(c, 1);
	resize(c, (struct wlr_box){80, 80, 800, 500}, 1);
	focusclient(c, 1);
	pump_for(500);
	assert(!c->resize);
	int native = !client_is_x11(c);
	if (native) {
		LISTEN(&c->surface.xdg->events.configure, &app_configure, app_configured);
		LISTEN(&client_surface(c)->events.commit, &app_commit, app_committed);
	}
	LISTEN(&c->mon->wlr_output->events.present, &presented, present);
	begin(&probes[0]);
	pump_for(100);
	app_requests = app_commits = app_duplicates = app_latency_count = 0;
	app_input_count = app_age_count = 0;
	presents = mismatches = 0;
	watching = 1;
	app_dragging = native;
	int64_t start = now_ms();
	for (int i = 0; i < 400; i++) {
		int phase = i % 160;
		int distance = phase <= 80 ? phase : 160 - phase;
		app_inputs[app_input_count] = (Configure){0, 798 + distance * 3, 498 + distance};
		app_input_time[app_input_count++] = now_ms();
		motion(&probes[0], 800 + distance * 3, 500 + distance);
		pump(0);
		while (now_ms() < start + i + 1) pump(1);
	}
	app_dragging = 0;
	motion(&probes[0], 900, 540);
	finish();
	int64_t released_at = now_ms();
	int settled = 0;
	for (int i = 0; i < 3000; i++) {
		pump(1);
		struct wlr_box actual;
		client_get_geometry(c, &actual);
		if (native ? !c->resize && c->surface.xdg->toplevel->current.width == 898 &&
				c->surface.xdg->toplevel->current.height == 538 &&
				actual.width == 898 && actual.height == 538 :
				client_surface(c)->current.width == 898 && client_surface(c)->current.height == 538) {
			settled = 1;
			break;
		}
	}
	int64_t settle_ms = now_ms() - released_at;
	pump_for(30);
	watching = 0;
	qsort(app_latencies, app_latency_count, sizeof(app_latencies[0]), compare_latency);
	qsort(app_ages, app_age_count, sizeof(app_ages[0]), compare_latency);
	qsort(app_errors, app_age_count, sizeof(app_errors[0]), compare_latency);
	printf("{\"case\":\"application_%s\",\"inputs\":400,\"configures\":%d,\"duplicate_configures\":%d,\"surface_commits\":%d,\"presentations\":%d,\"mismatched_presentations\":%d,\"settled\":%s,\"final_settle_ms\":%lld,\"configure_commit_samples\":%d,\"median_configure_commit_ms\":%lld,\"drag_present_samples\":%d,\"median_target_age_ms\":%lld,\"median_target_error_px\":%lld}\n",
		kind, native ? app_requests : -1, native ? app_duplicates : -1,
		native ? app_commits : -1, presents, mismatches,
		settled ? "true" : "false", (long long)settle_ms, app_latency_count,
		(long long)(app_latency_count ? app_latencies[app_latency_count / 2] : -1), app_age_count,
		(long long)(app_age_count ? app_ages[app_age_count / 2] : -1),
		(long long)(app_age_count ? app_errors[app_age_count / 2] : -1));
	assert(settled);
	if (checking) assert(!mismatches && coherent(&probes[0]));
	if (native) {
		wl_list_remove(&app_configure.link);
		wl_list_remove(&app_commit.link);
	}
	wl_list_remove(&presented.link);
	setfloating(c, 0);
	setfloating(background, 0);
	selmon = c->mon;
	setlayout(&(Arg){.v = &layouts[1]});
	setmfact(&(Arg){.f = -0.1f});
	pump_for(500);
	assert(!c->resize && !background->resize);
	puts("OK real application floating resize, repeated reversals and two-application tiled layout");
	cleanup();
}

#ifndef RESIZE_HELPERS_ONLY
int main(int argc, char **argv)
{
	checking = argc > 1 && !strcmp(argv[1], "--check");
	setbuf(stdout, NULL);
	alarm(50);
	Config *loaded = read_config("config");
	assert(loaded);
	cfg = *loaded;
	free(loaded);
	setup();
	assert(wlr_backend_start(backend));
	Monitor *output = wl_container_of(mons.next, output, link);
	struct wlr_output_state mode;
	wlr_output_state_init(&mode);
	wlr_output_state_set_custom_mode(&mode, 1920, 1200, 60000);
	assert(wlr_output_commit_state(output->wlr_output, &mode));
	wlr_output_state_finish(&mode);
	updatemons(NULL, NULL);
	printf("{\"case\":\"environment\",\"renderer\":\"%s\",\"width\":%d,\"height\":%d,\"refresh_mhz\":%d}\n",
		getenv("WLR_RENDERER"), output->wlr_output->width, output->wlr_output->height,
		output->wlr_output->refresh);
	if (argc > 3) {
		applications(argv[2], argv[3]);
		return 0;
	}
	init_probe(&probes[0], "Resize A");
	init_probe(&probes[1], "Resize B");
	place(&probes[0]);
	setfloating(probes[1].client, 1);
	resize(probes[1].client, (struct wlr_box){750, 100, 420, 280}, 1);
	pump_for(100);
	LISTEN(&probes[0].client->mon->wlr_output->events.present, &presented, present);
	tracking();
	drive(0);
	drive(8);
	drive(50);
	acknowledgements();
	unsent_and_minimum();
	stalled();
	independent_clients();
	constrained_and_tiled();
	lifecycle();
	puts("OK protocol clients, rapid interactive resizing, reversals and controlled redraw delays");
	return 0;
}
#endif
