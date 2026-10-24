/* Committed surfaces, independent child commits and composed pixel checks. */
#include <drm_fourcc.h>
#include <wlr/render/wlr_texture.h>
#include <wlr/types/wlr_subcompositor.h>
#include "sampling-viewport-client-protocol.h"

static struct wl_subcompositor *sampling_subcompositor;
static struct wp_viewporter *sampling_viewporter;

static void sampling_global(void *data, struct wl_registry *registry, uint32_t name,
		const char *interface, uint32_t version)
{
	if (!strcmp(interface, wl_subcompositor_interface.name))
		sampling_subcompositor = wl_registry_bind(registry, name, &wl_subcompositor_interface, 1);
	else if (!strcmp(interface, wp_viewporter_interface.name))
		sampling_viewporter = wl_registry_bind(registry, name, &wp_viewporter_interface, 1);
}

static struct wlr_scene_buffer *sampling_buffer_for(struct wlr_scene_node *node,
		struct wlr_surface *surface)
{
	if (node->type == WLR_SCENE_NODE_BUFFER) {
		struct wlr_scene_buffer *buffer = wlr_scene_buffer_from_node(node);
		struct wlr_scene_surface *item = wlr_scene_surface_try_from_buffer(buffer);
		return item && item->surface == surface ? buffer : NULL;
	}
	if (node->type == WLR_SCENE_NODE_TREE) {
		struct wlr_scene_tree *tree = wlr_scene_tree_from_node(node);
		struct wlr_scene_node *child;
		wl_list_for_each(child, &tree->children, link) {
			struct wlr_scene_buffer *buffer = sampling_buffer_for(child, surface);
			if (buffer) return buffer;
		}
	}
	return NULL;
}

static void sampling_submit(Probe *p, struct wl_surface *surface, int width, int height,
		int scale, int transform)
{
	int w = width * scale, h = height * scale;
	size_t size = (size_t)w * h * 4;
	int fd = memfd_create("sampling-check", MFD_CLOEXEC);
	assert(fd >= 0 && !ftruncate(fd, (off_t)size));
	uint32_t *pixels = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	assert(pixels != MAP_FAILED);
	for (int y = 0; y < h; y++)
		for (int x = 0; x < w; x++)
			pixels[y * w + x] = ((x ^ y) & 1) ? 0xffffffffu : 0xff000000u;
	struct wl_shm_pool *pool = wl_shm_create_pool(p->shm, fd, (int)size);
	struct wl_buffer *buffer = wl_shm_pool_create_buffer(pool, 0, w, h, w * 4, WL_SHM_FORMAT_ARGB8888);
	wl_buffer_add_listener(buffer, &buffer_listener, NULL);
	wl_shm_pool_destroy(pool); munmap(pixels, size); close(fd);
	if (surface == p->surface) {
		int index = p->count - 1;
		if (p->acknowledged != p->configs[index].serial) {
			xdg_surface_ack_configure(p->xdg, p->configs[index].serial);
			p->acknowledged = p->configs[index].serial;
		}
		p->completed = index;
		xdg_surface_set_window_geometry(p->xdg, 0, 0, width, height);
	}
	wl_surface_set_buffer_scale(surface, scale);
	wl_surface_set_buffer_transform(surface, transform);
	wl_surface_attach(surface, buffer, 0, 0);
	wl_surface_damage_buffer(surface, 0, 0, w, h);
	wl_surface_commit(surface);
	pump_for(35);
}

static void sampling_scale(Monitor *m, float scale)
{
	struct wlr_output_state state;
	wlr_output_state_init(&state);
	wlr_output_state_set_scale(&state, scale);
	assert(wlr_output_commit_state(m->wlr_output, &state));
	wlr_output_state_finish(&state);
	updatemons(NULL, NULL);
	pump_for(25);
}

static void sampling(void)
{
	Probe *p = &probes[0];
	p->manual = 1;
	struct wlr_surface *surface = client_surface(p->client);
	struct wlr_scene_buffer *root = sampling_buffer_for(&p->client->scene->node, surface);
	assert(root);
	int width = surface->current.width, height = surface->current.height;
	sampling_submit(p, p->surface, width, height, 1, WL_OUTPUT_TRANSFORM_NORMAL);
	int unscaled = root->filter_mode == WLR_SCALE_FILTER_NEAREST;

	/* Read actual composed pixels, rather than only checking a filter flag. */
	struct wlr_output_state capture;
	wlr_output_state_init(&capture);
	wlr_damage_ring_add_whole(&outputs[0]->scene_output->damage_ring);
	assert(wlr_scene_output_build_state(outputs[0]->scene_output, &capture, NULL));
	assert(capture.buffer);
	struct wlr_texture *texture = wlr_texture_from_buffer(drw, capture.buffer);
	assert(texture);
	int x, y;
	assert(wlr_scene_node_coords(&root->node, &x, &y));
	uint32_t pixels[64 * 64];
	assert(wlr_texture_read_pixels(texture, &(struct wlr_texture_read_pixels_options){
		.data = pixels, .format = DRM_FORMAT_ARGB8888, .stride = 64 * 4,
		.src_box = {x + 20, y + 20, 64, 64},
	}));
	int changed = 0;
	for (int j = 0; j < 64; j++)
		for (int i = 0; i < 64; i++)
			changed += (pixels[j * 64 + i] & 0xffffffu) != (((i ^ j) & 1) ? 0xffffffu : 0);
	wlr_texture_destroy(texture);
	wlr_output_state_finish(&capture);
	assert(!changed);

	sampling_scale(outputs[0], 2);
	int scaled = root->filter_mode == WLR_SCALE_FILTER_BILINEAR;
	sampling_submit(p, p->surface, width, height, 2, WL_OUTPUT_TRANSFORM_NORMAL);
	int hidpi = root->filter_mode == WLR_SCALE_FILTER_NEAREST;
	sampling_scale(outputs[0], 1.5f);
	int fractional = root->filter_mode == WLR_SCALE_FILTER_BILINEAR;
	sampling_scale(outputs[0], 1);
	sampling_submit(p, p->surface, width, height, 1, WL_OUTPUT_TRANSFORM_180);
	int transformed = root->filter_mode == WLR_SCALE_FILTER_BILINEAR;
	sampling_submit(p, p->surface, width, height, 1, WL_OUTPUT_TRANSFORM_NORMAL);
	int restored = root->filter_mode == WLR_SCALE_FILTER_NEAREST;

	struct wl_registry *registry = wl_display_get_registry(p->display);
	const struct wl_registry_listener registry_callbacks = {sampling_global, global_remove};
	wl_registry_add_listener(registry, &registry_callbacks, NULL);
	pump_for(15);
	assert(sampling_subcompositor && sampling_viewporter);
	struct wl_surface *child = wl_compositor_create_surface(p->compositor);
	struct wl_subsurface *sub = wl_subcompositor_get_subsurface(sampling_subcompositor, child, p->surface);
	wl_subsurface_set_position(sub, 150, 150);
	wl_subsurface_set_desync(sub);
	wl_surface_commit(p->surface); pump_for(25);
	sampling_submit(p, child, 24, 24, 1, WL_OUTPUT_TRANSFORM_NORMAL);
	struct wlr_subsurface *subsurface = wl_container_of(surface->current.subsurfaces_above.next, subsurface, current.link);
	struct wlr_scene_buffer *child_buffer = sampling_buffer_for(&p->client->scene->node, subsurface->surface);
	assert(child_buffer);
	int child_unscaled = child_buffer->filter_mode == WLR_SCALE_FILTER_NEAREST;
	sampling_submit(p, child, 24, 24, 2, WL_OUTPUT_TRANSFORM_NORMAL);
	int child_scaled = child_buffer->filter_mode == WLR_SCALE_FILTER_BILINEAR;
	sampling_submit(p, child, 24, 24, 1, WL_OUTPUT_TRANSFORM_NORMAL);
	struct wp_viewport *viewport = wp_viewporter_get_viewport(sampling_viewporter, child);
	wp_viewport_set_source(viewport, wl_fixed_from_double(0.5), wl_fixed_from_double(0.5),
		wl_fixed_from_int(20), wl_fixed_from_int(20));
	wp_viewport_set_destination(viewport, 20, 20);
	wl_surface_commit(child); pump_for(25);
	int fractional_source = child_buffer->filter_mode == WLR_SCALE_FILTER_BILINEAR;
	wp_viewport_set_source(viewport, 0, 0, wl_fixed_from_int(20), wl_fixed_from_int(20));
	wl_surface_commit(child); pump_for(25);
	int integer_source = child_buffer->filter_mode == WLR_SCALE_FILTER_NEAREST;
	wp_viewport_set_destination(viewport, 40, 40);
	wl_surface_commit(child); pump_for(25);
	int viewport_scaled = child_buffer->filter_mode == WLR_SCALE_FILTER_BILINEAR;
	wp_viewport_destroy(viewport); wl_subsurface_destroy(sub); wl_surface_destroy(child);
	pump_for(25);
	wl_registry_destroy(registry);

	sampling_scale(outputs[1], 2);
	resize(p->client, (struct wlr_box){outputs[0]->m.x + outputs[0]->m.width - 200, 100,
		width + 2 * p->client->bw, height + 2 * p->client->bw}, 1);
	pump_for(25);
	int mixed_outputs = root->filter_mode == WLR_SCALE_FILTER_BILINEAR;
	resize(p->client, (struct wlr_box){100, 100, width + 2 * p->client->bw, height + 2 * p->client->bw}, 1);
	pump_for(25);
	int returned = root->filter_mode == WLR_SCALE_FILTER_NEAREST;
	printf("{\"case\":\"surface_sampling\",\"unscaled_nearest\":%d,\"changed_checkerboard_pixels\":%d,\"scaled_bilinear\":%d,\"hidpi_nearest\":%d,\"fractional_bilinear\":%d,\"transformed_bilinear\":%d,\"restored_nearest\":%d,\"independent_child_nearest\":%d,\"independent_child_scaled_bilinear\":%d,\"fractional_source_bilinear\":%d,\"integer_source_nearest\":%d,\"viewport_scaled_bilinear\":%d,\"mixed_outputs_bilinear\":%d,\"return_nearest\":%d}\n",
		unscaled, changed, scaled, hidpi, fractional, transformed, restored, child_unscaled,
		child_scaled, fractional_source, integer_source, viewport_scaled, mixed_outputs, returned);
	if (checking) assert(unscaled && scaled && hidpi && fractional && transformed && restored &&
		child_unscaled && child_scaled && fractional_source && integer_source && viewport_scaled && mixed_outputs && returned);
}
