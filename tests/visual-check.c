/* Selected visual regressions on real surfaces and private headless outputs. */
#define RESIZE_HELPERS_ONLY
#include "resize-check.c"

static Monitor *outputs[3];
static int eligible_child, scene_calls, frame_count, x11_requests;
static struct wlr_scene_output *observed_scene;

int __real_waitid(idtype_t type, id_t id, siginfo_t *info, int options);
int
__wrap_waitid(idtype_t type, id_t id, siginfo_t *info, int options)
{
	/* Socketpair clients belong to this process. Exercise the direct-child
	 * rendering policy without changing the production process reaper. */
	if (eligible_child && type == P_PID && id == (id_t)getpid()) {
		memset(info, 0, sizeof(*info));
		return 0;
	}
	return __real_waitid(type, id, info, options);
}

bool __real_wlr_scene_output_commit(struct wlr_scene_output *output,
		const struct wlr_scene_output_state_options *options);
bool
__wrap_wlr_scene_output_commit(struct wlr_scene_output *output,
		const struct wlr_scene_output_state_options *options)
{
	if (output == observed_scene) scene_calls++;
	return __real_wlr_scene_output_commit(output, options);
}

void __real_wlr_xwayland_surface_configure(struct wlr_xwayland_surface *surface,
		int16_t x, int16_t y, uint16_t width, uint16_t height);
void
__wrap_wlr_xwayland_surface_configure(struct wlr_xwayland_surface *surface,
		int16_t x, int16_t y, uint16_t width, uint16_t height)
{
	if (surface->xwm) {
		__real_wlr_xwayland_surface_configure(surface, x, y, width, height);
		return;
	}
	/* Match XWM's immediate requested-geometry update. The associated real
	 * surface below submits buffers independently, including stale sizes. */
	surface->x = x; surface->y = y;
	surface->width = width; surface->height = height;
	x11_requests++;
}

static int same_box(struct wlr_box a, struct wlr_box b)
{
	return wlr_box_equal(&a, &b);
}

static void fullscreen_restore(void)
{
	Probe *p = &probes[0];
	struct wlr_box original = p->client->geom;
	xdg_toplevel_set_fullscreen(p->toplevel, NULL);
	pump_for(50);
	assert(p->client->isfullscreen);
	int before = p->count;
	xdg_toplevel_set_fullscreen(p->toplevel, NULL);
	pump_for(50);
	int repeated_request_answered = p->count > before;
	xdg_toplevel_unset_fullscreen(p->toplevel);
	pump_for(50);
	int restored = same_box(original, p->client->geom);
	before = p->count;
	xdg_toplevel_unset_fullscreen(p->toplevel);
	pump_for(50);
	int repeated_unset_answered = p->count > before;
	int unset_stable = same_box(original, p->client->geom);
	printf("{\"case\":\"fullscreen_repeated_requests\",\"restored\":%s,\"repeated_unset_stable\":%s,\"repeat_requests_answered\":%s,\"restored_width\":%d,\"restored_height\":%d}\n",
		restored ? "true" : "false", unset_stable ? "true" : "false",
		repeated_request_answered && repeated_unset_answered ? "true" : "false",
		p->client->geom.width, p->client->geom.height);
	if (checking) assert(restored && unset_stable);
	assert(repeated_request_answered && repeated_unset_answered);

	resize(p->client, original, 1);
	pump_for(40);
	setfullscreen(p->client, 1);
	pump_for(40);
	setmon(p->client, outputs[1], p->client->tags);
	pump_for(40);
	setfullscreen(p->client, 1);
	setfullscreen(p->client, 0);
	pump_for(60);
	int transferred = p->client->geom.width == original.width &&
		p->client->geom.height == original.height &&
		p->client->geom.x - outputs[1]->w.x == original.x - outputs[0]->w.x &&
		p->client->geom.y - outputs[1]->w.y == original.y - outputs[0]->w.y;
	printf("{\"case\":\"fullscreen_monitor_transfer\",\"restore_geometry_preserved\":%s}\n",
		transferred ? "true" : "false");
	if (checking) assert(transferred);

	/* An application's first fullscreen request can arrive before mapping. */
	p = &probes[1];
	p->manual = 1;
	xdg_toplevel_destroy(p->toplevel);
	xdg_surface_destroy(p->xdg);
	wl_surface_destroy(p->surface);
	pump_for(30);
	p->client = NULL;
	p->count = 0; p->completed = p->drawing = -1; p->acknowledged = 0;
	p->surface = wl_compositor_create_surface(p->compositor);
	p->xdg = xdg_wm_base_get_xdg_surface(p->shell, p->surface);
	xdg_surface_add_listener(p->xdg, &surface_listener, p);
	p->toplevel = xdg_surface_get_toplevel(p->xdg);
	xdg_toplevel_add_listener(p->toplevel, &top_listener, p);
	xdg_toplevel_set_title(p->toplevel, "Initially fullscreen");
	xdg_toplevel_set_min_size(p->toplevel, 400, 260);
	xdg_toplevel_set_max_size(p->toplevel, 400, 260);
	xdg_toplevel_set_fullscreen(p->toplevel, NULL);
	wl_surface_commit(p->surface);
	p->manual = 0;
	for (int i = 0; i < 500 && !p->client; i++) {
		pump(2);
		p->client = find_title("Initially fullscreen");
	}
	assert(p->client && p->client->isfullscreen);
	pump_for(40);
	xdg_toplevel_unset_fullscreen(p->toplevel);
	pump_for(60);
	int initial_restore = !p->client->isfullscreen &&
		p->client->geom.width == 402 && p->client->geom.height == 262;
	printf("{\"case\":\"initial_fullscreen\",\"initial_restore_size_preserved\":%s}\n",
		initial_restore ? "true" : "false");
	if (checking) assert(initial_restore);
}

static void unplug(void)
{
	Probe *unrelated = &probes[0], *migrating = &probes[1];
	setmon(unrelated->client, outputs[2], 1);
	resize(unrelated->client, (struct wlr_box){outputs[2]->w.x + 50,
		outputs[2]->w.y + 60, 420, 280}, 1);
	setmon(migrating->client, outputs[1], 1);
	resize(migrating->client, (struct wlr_box){outputs[1]->w.x + 30,
		outputs[1]->w.y + 40, 420, 280}, 1);
	pump_for(60);
	struct wlr_box original = unrelated->client->geom;
	selmon = outputs[1];
	wlr_output_destroy(outputs[1]->wlr_output);
	outputs[1] = NULL;
	pump_for(80);
	Monitor *destination = migrating->client->mon;
	int unchanged = same_box(original, unrelated->client->geom);
	int migrated = destination && destination->wlr_output->enabled &&
		migrating->client->geom.x == destination->w.x + 30 &&
		migrating->client->geom.y == destination->w.y + 40 &&
		migrating->client->geom.width == 420 && migrating->client->geom.height == 280;
	printf("{\"case\":\"monitor_removal\",\"unrelated_window_unchanged\":%s,\"relative_position_preserved\":%s,\"selected_output_enabled\":%s}\n",
		unchanged ? "true" : "false", migrated ? "true" : "false",
		selmon && selmon->wlr_output->enabled ? "true" : "false");
	if (checking) assert(unchanged && migrated);

	/* Removing an output must also preserve a fullscreen window's restore. */
	setmon(migrating->client, outputs[0], 1);
	resize(migrating->client, (struct wlr_box){outputs[0]->w.x + 30,
		outputs[0]->w.y + 40, 420, 280}, 1);
	pump_for(40);
	setmaximized(migrating->client, 1);
	setmon(migrating->client, outputs[2], 1);
	pump_for(40);
	setmaximized(migrating->client, 0);
	pump_for(40);
	int maximized_restore = migrating->client->geom.width == 420 &&
		migrating->client->geom.height == 280 &&
		migrating->client->geom.x == outputs[2]->w.x + 30 &&
		migrating->client->geom.y == outputs[2]->w.y + 40;
	printf("{\"case\":\"maximized_monitor_transfer\",\"restore_geometry_preserved\":%s}\n",
		maximized_restore ? "true" : "false");
	if (checking) assert(maximized_restore);
	setmon(migrating->client, outputs[0], 1);
	resize(migrating->client, (struct wlr_box){outputs[0]->w.x + 30,
		outputs[0]->w.y + 40, 420, 280}, 1);
	pump_for(40);
	setfullscreen(migrating->client, 1);
	pump_for(40);
	selmon = outputs[0];
	wlr_output_destroy(outputs[0]->wlr_output);
	outputs[0] = NULL;
	pump_for(60);
	setfullscreen(migrating->client, 0);
	pump_for(60);
	destination = migrating->client->mon;
	int restored = destination && migrating->client->geom.width == 420 &&
		migrating->client->geom.height == 280 &&
		migrating->client->geom.x == destination->w.x + 30 &&
		migrating->client->geom.y == destination->w.y + 40;
	printf("{\"case\":\"fullscreen_output_removal\",\"restored_on_remaining_output\":%s}\n",
		restored ? "true" : "false");
	if (checking) assert(restored);
}

static void size_limits(void)
{
	Probe *p = &probes[0];
	xdg_toplevel_set_min_size(p->toplevel, 300, 200);
	xdg_toplevel_set_max_size(p->toplevel, 700, 500);
	wl_surface_commit(p->surface);
	pump_for(30);
	begin(p);
	motion(p, 80, 60);
	finish();
	pump_for(60);
	int minimum = p->client->surface.xdg->toplevel->scheduled.width == 300 &&
		p->client->surface.xdg->toplevel->scheduled.height == 200;
	begin(p);
	motion(p, 1800, 1000);
	finish();
	pump_for(60);
	int maximum = p->client->surface.xdg->toplevel->scheduled.width == 700 &&
		p->client->surface.xdg->toplevel->scheduled.height == 500;
	xdg_toplevel_set_min_size(p->toplevel, 0, 240);
	xdg_toplevel_set_max_size(p->toplevel, 0, 0);
	wl_surface_commit(p->surface);
	pump_for(20);
	begin(p);
	motion(p, 20, 30);
	finish();
	pump_for(40);
	int independent_axes = p->client->surface.xdg->toplevel->scheduled.width == 18 &&
		p->client->surface.xdg->toplevel->scheduled.height == 240;
	xdg_toplevel_set_min_size(p->toplevel, 400, 300);
	xdg_toplevel_set_max_size(p->toplevel, 400, 300);
	wl_surface_commit(p->surface);
	pump_for(30);
	resize(p->client, (struct wlr_box){100, 100, 420, 320}, 1);
	pump_for(30);
	begin(p); motion(p, 900, 600); finish(); pump_for(40);
	int fixed_size = p->client->geom.width == 402 && p->client->geom.height == 302;
	setfullscreen(p->client, 1);
	pump_for(40);
	int fullscreen = same_box(p->client->geom, p->client->mon->m);
	setfullscreen(p->client, 0);
	setfloating(p->client, 0);
	pump_for(50);
	int tiled = p->client->geom.height > 302;
	printf("{\"case\":\"native_size_limits\",\"minimum\":%s,\"maximum\":%s,\"independent_axes\":%s,\"fixed_size\":%s,\"fullscreen_allocation_preserved\":%s,\"tiled_allocation_preserved\":%s}\n",
		minimum ? "true" : "false", maximum ? "true" : "false",
		independent_axes ? "true" : "false", fixed_size ? "true" : "false",
		fullscreen ? "true" : "false", tiled ? "true" : "false");
	if (checking) assert(minimum && maximum && independent_axes && fixed_size && fullscreen && tiled);
}

static void frame_presented(struct wl_listener *listener, void *data)
{
	frame_count++;
}

static void stalled_tiled(void)
{
	Probe *p = &probes[0], *other = &probes[1];
	setfloating(p->client, 0);
	pump_for(60);
	p->manual = 1;
	struct wlr_box target = p->client->geom;
	target.width -= 80;
	resize(p->client, target, 0);
	pump_for(5);
	assert(p->client->resize && client_is_rendered_on_mon(p->client, p->client->mon));
	Monitor *m = p->client->mon;
	observed_scene = m->scene_output;
	eligible_child = 1;
	scene_calls = frame_count = 0;
	struct wl_listener frames;
	LISTEN(&m->wlr_output->events.present, &frames, frame_presented);
	rendermon(&m->frame, NULL);
	int initial_wait = !scene_calls;
	/* New requests while the client stays stalled must not restart the wait. */
	for (int i = 0; i < 20; i++) {
		target.width += (i & 1) ? 3 : -3;
		resize(p->client, target, 0);
		commit_config(other, other->completed, 0);
		pump_for(10);
	}
	int ongoing_calls = scene_calls, ongoing_frames = frame_count;
	int pending = p->client->resize != 0;
	p->manual = 0;
	pump_for(100);
	assert(!p->client->resize);
	/* A later independent resize gets its original brief coordination chance. */
	p->manual = 1;
	target.width += 10;
	resize(p->client, target, 0);
	scene_calls = 0;
	rendermon(&m->frame, NULL);
	int rearmed = !scene_calls;
	setfloating(p->client, 1);
	rendermon(&m->frame, NULL);
	int floating_progress = scene_calls != 0;
	printf("{\"case\":\"stalled_tiled_output\",\"initial_coordination_chance\":%s,\"scene_calls_while_pending\":%d,\"virtual_presentations_while_pending\":%d,\"client_still_pending\":%s,\"later_wait_rearmed\":%s,\"floating_exempt\":%s}\n",
		initial_wait ? "true" : "false", ongoing_calls, ongoing_frames,
		pending ? "true" : "false", rearmed ? "true" : "false",
		floating_progress ? "true" : "false");
	if (checking) assert(initial_wait && ongoing_calls >= 3 && ongoing_frames >= 3 && pending && rearmed && floating_progress);
	wl_list_remove(&frames.link);
	eligible_child = 0;
	p->manual = 0;
	pump_for(60);
}

static void submit_x11_buffer(Probe *p, int width, int height)
{
	int index = p->count++;
	assert(index < (int)LENGTH(p->configs));
	p->configs[index] = (Configure){p->acknowledged, width, height};
	commit_config(p, index, 0);
	pump_for(15);
}

static void x11_buffers(void)
{
	Probe *p = &probes[0];
	p->manual = 1;
	Client proxy = *p->client;
	xcb_size_hints_t hints = {.min_width = 300, .min_height = 200,
		.max_width = 700, .max_height = 500,
		.flags = XCB_ICCCM_SIZE_HINT_P_MIN_SIZE | XCB_ICCCM_SIZE_HINT_P_MAX_SIZE};
	struct wlr_xwayland_surface xsurface = {
		.surface = client_surface(p->client), .size_hints = &hints,
		.width = 418, .height = 278,
	};
	proxy.type = X11;
	proxy.surface.xwayland = &xsurface;
	proxy.commit = proxy.map = proxy.unmap = (struct wl_listener){0};
	wl_list_remove(&p->client->commit.link);
	associatex11(&proxy.associate, NULL);
	Probe observed = {.client = &proxy};
	grabc = &proxy;
	cursor_mode = CurResize;
	resize(&proxy, (struct wlr_box){100, 100, 80, 60}, 1);
	int minimum = xsurface.width == 300 && xsurface.height == 200;
	int old_buffer_coherent = coherent(&observed);
	Client *hit = NULL;
	xytonode(100 + 405, 130, NULL, &hit, NULL, NULL, NULL);
	int unclipped = hit == p->client;
	resize(&proxy, (struct wlr_box){100, 100, 1800, 1000}, 1);
	int maximum = xsurface.width == 700 && xsurface.height == 500;
	resize(&proxy, (struct wlr_box){100, 100, 600, 400}, 1);
	resize(&proxy, (struct wlr_box){100, 100, 420, 280}, 1);
	cursor_mode = CurNormal;
	resize(&proxy, proxy.geom, 1);
	int requests = x11_requests;
	submit_x11_buffer(p, 598, 398); /* An older response arrives after release. */
	int stale_coherent = coherent(&observed);
	submit_x11_buffer(p, 418, 278);
	int final_coherent = coherent(&observed);
	int no_feedback = x11_requests == requests;
	hints.min_width = INT_MAX; hints.max_width = 12; /* Malformed X11 hints. */
	resize(&proxy, (struct wlr_box){100, 100, 80, 60}, 1);
	int safe_limits = proxy.geom.width - 2 * (int)proxy.bw <= UINT16_MAX &&
		proxy.geom.width > 2 * (int)proxy.bw;
	proxy.isfloating = 0;
	resize(&proxy, (struct wlr_box){100, 100, 600, 400}, 0);
	int tiled_unchanged = proxy.border[0]->width == 600 && proxy.border[2]->height == 398;
	printf("{\"case\":\"x11_committed_buffers\",\"minimum\":%s,\"maximum\":%s,\"pending_buffer_coherent\":%s,\"pending_shrink_unclipped\":%s,\"stale_commit_coherent\":%s,\"final_commit_coherent\":%s,\"no_configure_feedback\":%s,\"malformed_hints_bounded\":%s,\"tiled_allocation_preserved\":%s}\n",
		minimum ? "true" : "false", maximum ? "true" : "false",
		old_buffer_coherent ? "true" : "false", unclipped ? "true" : "false",
		stale_coherent ? "true" : "false", final_coherent ? "true" : "false",
		no_feedback ? "true" : "false", safe_limits ? "true" : "false",
		tiled_unchanged ? "true" : "false");
	if (checking) assert(minimum && maximum && old_buffer_coherent && unclipped && stale_coherent && final_coherent && no_feedback && safe_limits && tiled_unchanged);
	dissociatex11(&proxy.dissociate, NULL);
	LISTEN(&client_surface(p->client)->events.commit, &p->client->commit, commitnotify);
	grabc = NULL;
}

#include "sampling-check.h"

int main(int argc, char **argv)
{
	assert(argc == 3);
	checking = !strcmp(argv[1], "--check");
	setbuf(stdout, NULL);
	alarm(25);
	Config *loaded = read_config("config");
	assert(loaded); cfg = *loaded; free(loaded);
	setup(); assert(wlr_backend_start(backend));
	Monitor *m;
	wl_list_for_each(m, &mons, link) {
		int index = atoi(strrchr(m->wlr_output->name, '-') + 1) - 1;
		assert(index >= 0 && index < 3); outputs[index] = m;
	}
	for (int i = 0; i < 3; i++) {
		assert(outputs[i]);
		int x = i * 1280, y = 0;
		if (!strcmp(argv[2], "unplug_vertical")) {x = 0; y = i * 720;}
		if (!strcmp(argv[2], "unplug_offset")) {x = i == 1 ? 0 : -1280; y = i == 2 ? 0 : -720;}
		wlr_output_layout_add(output_layout, outputs[i]->wlr_output, x, y);
	}
	selmon = outputs[0];
	init_probe(&probes[0], "Visual A");
	init_probe(&probes[1], "Visual B");
	setfloating(probes[0].client, 1); setfloating(probes[1].client, 1);
	resize(probes[0].client, (struct wlr_box){outputs[0]->w.x + 100, outputs[0]->w.y + 100, 420, 280}, 1);
	resize(probes[1].client, (struct wlr_box){outputs[0]->w.x + 750, outputs[0]->w.y + 100, 420, 280}, 1);
	pump_for(80);
	if (!strcmp(argv[2], "fullscreen")) fullscreen_restore();
	else if (!strncmp(argv[2], "unplug_", 7)) unplug();
	else if (!strcmp(argv[2], "limits")) size_limits();
	else if (!strcmp(argv[2], "stalled")) stalled_tiled();
	else if (!strcmp(argv[2], "x11")) x11_buffers();
	else if (!strcmp(argv[2], "sampling")) sampling();
	else assert(!"unknown visual test case");
	printf("OK %s\n", argv[2]);
	return 0;
}
