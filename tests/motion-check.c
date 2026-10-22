/* Exercise motionnotify with real wlroots cursors, scene nodes and GTK surfaces. */
#define main simplewm_main
#include "simplewm.c"
#undef main
#include <assert.h>
#include <wlr/interfaces/wlr_pointer.h>

static struct wlr_pointer pointer;
static struct {
	unsigned motion, relative, idle, defaults, activated;
	struct wlr_surface *surface;
	uint32_t time;
	uint64_t relative_time;
	double sx, sy, dx, dy, ux, uy;
} sent;

void __real_wlr_seat_pointer_notify_enter(struct wlr_seat *, struct wlr_surface *, double, double);
void
__wrap_wlr_seat_pointer_notify_enter(struct wlr_seat *s, struct wlr_surface *surface,
		double sx, double sy)
{
	sent.surface = surface;
	__real_wlr_seat_pointer_notify_enter(s, surface, sx, sy);
}

void __real_wlr_seat_pointer_notify_motion(struct wlr_seat *, uint32_t, double, double);
void
__wrap_wlr_seat_pointer_notify_motion(struct wlr_seat *s, uint32_t time, double sx, double sy)
{
	sent.motion++;
	sent.time = time;
	sent.sx = sx;
	sent.sy = sy;
	__real_wlr_seat_pointer_notify_motion(s, time, sx, sy);
}

void __real_wlr_relative_pointer_manager_v1_send_relative_motion(
		struct wlr_relative_pointer_manager_v1 *, struct wlr_seat *, uint64_t,
		double, double, double, double);
void
__wrap_wlr_relative_pointer_manager_v1_send_relative_motion(
		struct wlr_relative_pointer_manager_v1 *manager, struct wlr_seat *s, uint64_t time,
		double dx, double dy, double ux, double uy)
{
	sent.relative++;
	sent.relative_time = time;
	sent.dx = dx;
	sent.dy = dy;
	sent.ux = ux;
	sent.uy = uy;
	__real_wlr_relative_pointer_manager_v1_send_relative_motion(manager, s, time, dx, dy, ux, uy);
}

void __real_wlr_idle_notifier_v1_notify_activity(struct wlr_idle_notifier_v1 *, struct wlr_seat *);
void
__wrap_wlr_idle_notifier_v1_notify_activity(struct wlr_idle_notifier_v1 *notifier,
		struct wlr_seat *s)
{
	sent.idle++;
	__real_wlr_idle_notifier_v1_notify_activity(notifier, s);
}

void __real_wlr_cursor_set_xcursor(struct wlr_cursor *, struct wlr_xcursor_manager *, const char *);
void
__wrap_wlr_cursor_set_xcursor(struct wlr_cursor *cur, struct wlr_xcursor_manager *manager,
		const char *name)
{
	if (!strcmp(name, "default"))
		sent.defaults++;
	__real_wlr_cursor_set_xcursor(cur, manager, name);
}

/* Constraints use real mapped surfaces and region math; only the protocol
 * activation message is replaced, since these fixtures have no wl_resource. */
void
__wrap_wlr_pointer_constraint_v1_send_activated(struct wlr_pointer_constraint_v1 *constraint)
{
	assert(constraint->surface && !constraint->resource);
	sent.activated++;
}

static void
near(double actual, double expected)
{
	if (fabs(actual - expected) > 0.000001) {
		fprintf(stderr, "coordinate: got %.9f, expected %.9f\n", actual, expected);
		abort();
	}
}

static void
pump(void)
{
	wl_display_flush_clients(dpy);
	assert(wl_event_loop_dispatch(event_loop, 10) >= 0);
}

static Client *
findclient(const char *title)
{
	Client *c;
	wl_list_for_each(c, &clients, link)
		if (!strcmp(client_get_title(c), title))
			return c;
	return NULL;
}

static void
place(Client *c, struct wlr_box box)
{
	setfloating(c, 1);
	c->bw = 4;
	resize(c, box, 1);
	for (int i = 0; i < 1000; i++) {
		pump();
		if (client_surface(c)->current.width == box.width - 2 * (int)c->bw &&
				client_surface(c)->current.height == box.height - 2 * (int)c->bw)
			return;
	}
	assert(!"client did not resize");
}

static void
warp(double x, double y)
{
	wlr_cursor_warp_closest(cursor, NULL, x, y);
	motionnotify(0, NULL, 0, 0, 0, 0);
	memset(&sent, 0, sizeof(sent));
}

static void
relative(uint32_t time, double dx, double dy)
{
	struct wlr_pointer_motion_event event = {
		.pointer = &pointer, .time_msec = time, .delta_x = dx, .delta_y = dy,
		.unaccel_dx = dx / 2, .unaccel_dy = dy / 2,
	};
	wl_signal_emit_mutable(&pointer.events.motion, &event);
	wl_signal_emit_mutable(&pointer.events.frame, NULL);
}

static void
absolute(uint32_t time, double x, double y)
{
	struct wlr_pointer_motion_absolute_event event = {
		.pointer = &pointer, .time_msec = time,
		.x = (x - sgeom.x) / sgeom.width, .y = (y - sgeom.y) / sgeom.height,
	};
	wl_signal_emit_mutable(&pointer.events.motion_absolute, &event);
	wl_signal_emit_mutable(&pointer.events.frame, NULL);
}

static void
button(enum wl_pointer_button_state state)
{
	struct wlr_pointer_button_event event = {
		.pointer = &pointer, .time_msec = 100, .button = BTN_LEFT, .state = state,
	};
	wl_signal_emit_mutable(&pointer.events.button, &event);
}

static void
delivered(Client *c, double sx, double sy)
{
	assert(sent.motion && sent.surface == client_surface(c));
	assert(seat->pointer_state.focused_surface == client_surface(c));
	near(sent.sx, sx);
	near(sent.sy, sy);
	near(seat->pointer_state.sx, sx);
	near(seat->pointer_state.sy, sy);
	assert(drag_icon->node.x == (int)round(cursor->x));
	assert(drag_icon->node.y == (int)round(cursor->y));
}

static void
current(Client *c)
{
	delivered(c, cursor->x - c->geom.x - c->bw, cursor->y - c->geom.y - c->bw);
}

int
main(int argc, char **argv)
{
	assert(argc == 2);
	setbuf(stdout, NULL);
	alarm(45);
	Config *loaded = read_config("config");
	assert(loaded);
	cfg = *loaded;
	free(loaded);
	setup();
	const char *display = wl_display_add_socket_auto(dpy);
	assert(display && !setenv("WAYLAND_DISPLAY", display, 1));
	assert(wlr_backend_start(backend));
	assert(wl_list_length(&mons) == 2);
	static const struct wlr_pointer_impl impl = {.name = "motion-check"};
	wlr_pointer_init(&pointer, &impl, "motion-check");
	inputdevice(NULL, &pointer.base);
	for (int i = 0; i < 2; i++) {
		pid_t child = fork();
		assert(child >= 0);
		if (!child) {
			execlp("python3", "python3", argv[1], i ? "Motion B" : "Motion A", NULL);
			_exit(127);
		}
	}
	Client *a = NULL, *b = NULL;
	for (int i = 0; i < 2000 && (!a || !b); i++) {
		pump();
		a = findclient("Motion A");
		b = findclient("Motion B");
	}
	assert(a && b && a->mon == b->mon);
	Monitor *first = a->mon;
	place(a, (struct wlr_box){100, 100, 300, 200});
	place(b, (struct wlr_box){450, 100, 300, 200});
	sloppyfocus = 0;

	/* Fractional, consecutive, negative and zero deltas, including timestamps
 * near uint32 wrap. The first event must report the new local position. */
	warp(130.25, 140.75);
	relative(0xfffffff0u, 3.25, -2.5);
	near(cursor->x, 133.5);
	near(cursor->y, 138.25);
	delivered(a, 29.5, 34.25);
	assert(sent.time == 0xfffffff0u && sent.relative_time == (uint64_t)0xfffffff0u * 1000);
	assert(sent.relative == 1 && sent.idle == 1 && sent.defaults == 0);
	near(sent.dx, 3.25); near(sent.dy, -2.5);
	near(sent.ux, 1.625); near(sent.uy, -1.25);
	relative(2, -10.5, 12.25);
	delivered(a, 19, 46.5);
	relative(3, 0, 0);
	delivered(a, 19, 46.5);
	puts("OK relative coordinates, fractional/negative/zero deltas, timestamps and raw relative payloads");

	absolute(4, 500.25, 150.5);
	near(cursor->x, 500.25); near(cursor->y, 150.5);
	delivered(b, 46.25, 46.5);
	memset(&sent, 0, sizeof(sent));
	absolute(0, 140.5, 160.25); /* Virtual-pointer zero-time warp. */
	delivered(a, 36.5, 56.25);
	assert(!sent.relative && !sent.idle && sent.time);
	puts("OK absolute coordinates and zero-time virtual-pointer warp");

	/* Hit-testing must reflect the destination on this very event. */
	relative(5, 350, 0);
	current(b);
	memset(&sent, 0, sizeof(sent));
	relative(6, 300, 0);
	assert(!seat->pointer_state.focused_surface && !sent.motion && sent.defaults == 1);
	relative(7, -300, 0);
	current(b);
	absolute(8, b->geom.x + 2, b->geom.y + 30); /* Border, not surface. */
	assert(!seat->pointer_state.focused_surface);
	puts("OK same-event surface crossings, background and borders");

	/* Device clipping changes the applied delta; adding the raw delta to old
 * local coordinates would still be wrong. */
	struct wlr_box region = {120, 120, 100, 100};
	wlr_cursor_map_input_to_region(cursor, &pointer.base, &region);
	warp(150, 150);
	relative(9, 1000, 1000);
	assert(cursor->x >= 120 && cursor->x < 220 && cursor->y >= 120 && cursor->y < 220);
	current(a);
	near(sent.dx, 1000); near(sent.dy, 1000);
	wlr_cursor_map_input_to_region(cursor, &pointer.base, NULL);
	warp(150, 150);
	relative(10, -10000, -10000);
	assert(cursor->x >= sgeom.x && cursor->x < 1 && cursor->y >= sgeom.y && cursor->y < 1);
	assert(!seat->pointer_state.focused_surface);
	puts("OK device-region and output-layout clipping");

	focusclient(a, 0);
	warp(150, 150);
	relative(11, 350, 0);
	current(b);
	assert(seat->keyboard_state.focused_surface == client_surface(a));
	sloppyfocus = 1;
	relative(12, -350, 0);
	relative(13, 350, 0);
	current(b);
	assert(seat->keyboard_state.focused_surface == client_surface(b));
	warp(150, 150); /* Internal refresh must not change keyboard focus. */
	assert(seat->keyboard_state.focused_surface == client_surface(b));
	memset(&sent, 0, sizeof(sent));
	motionnotify(0, NULL, 100, 100, 100, 100);
	current(a);
	near(cursor->x, 150); near(cursor->y, 150);
	assert(!sent.relative && !sent.idle);
	assert(seat->keyboard_state.focused_surface == client_surface(b));
	puts("OK click/sloppy keyboard focus and internal zero-time refresh");

	button(WL_POINTER_BUTTON_STATE_PRESSED);
	assert(cursor_mode == CurPressed && seat->pointer_state.button_count == 1);
	relative(14, 10, 5);
	current(a);
	relative(15, 340, 0);
	/* Preserve the existing toplevel-origin convention for a held grab. */
	delivered(a, cursor->x - a->geom.x, cursor->y - a->geom.y);
	assert(seat->keyboard_state.focused_surface == client_surface(a));
	relative(16, 300, 0);
	delivered(a, cursor->x - a->geom.x, cursor->y - a->geom.y);
	button(WL_POINTER_BUTTON_STATE_RELEASED);
	assert(cursor_mode == CurNormal && !seat->pointer_state.button_count);
	relative(17, -300, 0);
	current(b);
	puts("OK pressed-pointer grab within/across/outside surfaces and release");

	/* The drag flag must continue to bypass the pressed-pointer override. */
	struct wlr_drag drag = {0};
	warp(150, 150);
	seat->drag = &drag;
	cursor_mode = CurPressed;
	relative(18, 350, 0);
	current(b);
	memset(&sent, 0, sizeof(sent));
	relative(19, 300, 0);
	assert(!sent.defaults && !seat->pointer_state.focused_surface);
	seat->drag = NULL;
	cursor_mode = CurNormal;
	puts("OK drag target hit-testing and cursor-image behavior");

	sloppyfocus = 0;
	warp(134, 144);
	struct wlr_pointer_constraint_v1 constraint = {
		.surface = client_surface(a), .seat = seat, .type = WLR_POINTER_CONSTRAINT_V1_CONFINED,
	};
	pixman_region32_init_rect(&constraint.region, 20, 25, 70, 60);
	wl_list_insert(&pointer_constraints->constraints, &constraint.link);
	relative(20, 10, 5);
	assert(active_constraint == &constraint && sent.activated == 1);
	delivered(a, 40, 45);
	relative(21, 200, 0);
	assert(cursor->x - a->geom.x - a->bw < 90);
	assert(cursor->x - a->geom.x - a->bw >= 89);
	current(a);
	near(sent.dx, 200);
	constraint.type = WLR_POINTER_CONSTRAINT_V1_LOCKED;
	double x = cursor->x, y = cursor->y;
	memset(&sent, 0, sizeof(sent));
	relative(22, 10, 15);
	near(cursor->x, x); near(cursor->y, y);
	assert(sent.relative == 1 && !sent.motion && !sent.idle);
	memset(&sent, 0, sizeof(sent));
	motionnotify(0, NULL, 10, 15, 10, 15);
	current(a);
	assert(!sent.relative && !sent.idle);
	warp(500, 150);
	relative(23, 10, 5); /* A constraint on another surface must not lock B. */
	delivered(b, 56, 51);
	puts("OK confinement, relative payload before confinement, pointer lock and unfocused constraint");

	/* Move/resize still move the cursor and update geometry while a lock exists,
 * return before pointer delivery, and update the drag icon/selected output. */
	warp(150, 150);
	moveresize(&(Arg){.ui = CurMove});
	assert(cursor_mode == CurMove && grabc == a);
	memset(&sent, 0, sizeof(sent));
	relative(24, 1300.25, 20.5);
	assert(a->geom.x == (int)round(cursor->x) - grabcx);
	assert(a->geom.y == (int)round(cursor->y) - grabcy);
	assert(a->geom.width == 300 && a->geom.height == 200);
	assert(drag_icon->node.x == (int)round(cursor->x));
	assert(drag_icon->node.y == (int)round(cursor->y));
	assert(!sent.motion && sent.relative == 1 && sent.idle == 1);
	/* With sloppy focus enabled, even interactive movement selects an output. */
	sloppyfocus = 1;
	relative(25, 1, 0);
	assert(selmon != first && selmon == xytomon(cursor->x, cursor->y));
	button(WL_POINTER_BUTTON_STATE_RELEASED);
	assert(cursor_mode == CurNormal && a->mon == selmon && a->mon != first);
	setmon(a, first, 0);
	place(a, (struct wlr_box){100, 100, 300, 200});
	warp(150, 150);
	moveresize(&(Arg){.ui = CurResize});
	assert(cursor_mode == CurResize && grabc == a);
	near(cursor->x, 400); near(cursor->y, 300);
	memset(&sent, 0, sizeof(sent));
	relative(26, 51.25, 33.75);
	assert(a->geom.x == 100 && a->geom.y == 100);
	assert(a->geom.width == 351 && a->geom.height == 234);
	assert(!sent.motion && sent.relative == 1 && sent.idle == 1);
	assert(drag_icon->node.x == (int)round(cursor->x));
	assert(drag_icon->node.y == (int)round(cursor->y));
	button(WL_POINTER_BUTTON_STATE_RELEASED);
	assert(cursor_mode == CurNormal);
	active_constraint = NULL;
	wl_list_remove(&constraint.link);
	pixman_region32_fini(&constraint.region);
	puts("OK interactive move/resize, locked-constraint bypass, drag icon and monitor selection");
	return 0;
}
