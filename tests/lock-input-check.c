#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "loop.h"
#include "swaylock.h"

static int requests;
static size_t submitted;
void damage_state(struct swaylock_state *state) { }
void start_rejection(struct swaylock_state *state) { state->retry_visible = true; }
bool write_comm_request(struct swaylock_password *pw) {
	++requests;
	submitted = pw->characters;
	clear_password_buffer(pw);
	return true;
}

int main(void) {
	char bytes[1024] = {0};
	struct swaylock_state state = { .eventloop = loop_create(), .args.ignore_empty = true,
		.password = { .buffer = bytes, .buffer_len = sizeof(bytes) } };
	swaylock_handle_key(&state, XKB_KEY_Return, 0);
	assert(state.entry_visible && requests == 0);
	swaylock_handle_key(&state, XKB_KEY_Escape, 0);
	assert(!state.entry_visible);
	swaylock_handle_key(&state, XKB_KEY_x, 'x');
	assert(state.entry_visible && state.password.characters == 1 && !strcmp(bytes, "x"));
	swaylock_handle_key(&state, XKB_KEY_eacute, 0xe9);
	swaylock_handle_key(&state, XKB_KEY_NoSymbol, 0x1f642);
	assert(state.password.characters == 3 && state.password.len == 7);
	swaylock_handle_key(&state, XKB_KEY_BackSpace, 0);
	assert(state.password.characters == 2 && state.password.len == 3);
	swaylock_handle_key(&state, XKB_KEY_BackSpace, 0);
	assert(state.password.characters == 1 && !strcmp(bytes, "x"));
	state.auth_state = AUTH_STATE_INVALID;
	state.retry_visible = true;
	schedule_auth_idle(&state);
	swaylock_handle_key(&state, XKB_KEY_a, 'a');
	assert(!state.retry_visible && state.auth_state == AUTH_STATE_IDLE);
	swaylock_handle_key(&state, XKB_KEY_Return, 0);
	assert(requests == 1 && submitted == 2 && state.submitted_characters == 2);
	assert(state.auth_state == AUTH_STATE_VALIDATING && !state.auth_idle_timer);
	assert(state.password.len == 0 && state.password.characters == 0);
	for (size_t i = 0; i < sizeof(bytes); i++) assert(bytes[i] == 0);
	swaylock_handle_key(&state, XKB_KEY_a, 'a');
	swaylock_handle_key(&state, XKB_KEY_Return, 0);
	swaylock_handle_key(&state, XKB_KEY_Escape, 0);
	assert(requests == 1 && state.password.len == 0 && state.entry_visible);
	state.auth_state = AUTH_STATE_IDLE;
	swaylock_handle_key(&state, XKB_KEY_a, 'a');
	state.xkb.control = true;
	swaylock_handle_key(&state, XKB_KEY_u, 'u');
	assert(state.password.len == 0 && state.entry_visible);
	state.xkb.control = false;
	for (int i = 0; i < 1400; i++) swaylock_handle_key(&state, XKB_KEY_x, 'x');
	assert(state.password.len < sizeof(bytes) && state.password.characters == state.password.len);
	swaylock_handle_key(&state, XKB_KEY_Escape, 0);
	assert(!state.entry_visible && !state.retry_visible && state.password.characters == 0);
	loop_destroy(state.eventloop);
	puts("OK first key, UTF-8 masks/editing, empty Enter, retry, in-flight input, full clearing, and bounded passwords");
	return 0;
}
