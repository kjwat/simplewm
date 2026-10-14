/* Linked only into a temporary test binary, never into the installed locker. */
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "comm.h"
#include "password-buffer.h"
#include "swaylock.h"

void initialize_pw_backend(int argc, char **argv) {
	if (!spawn_comm_child()) exit(1);
}

void run_pw_backend_child(void) {
	for (;;) {
		char *password = NULL;
		ssize_t size = read_comm_request(&password);
		if (size <= 0) exit(size < 0);
		bool success = strcmp(password, "headless-caf\xc3\xa9") == 0;
		password_buffer_destroy(password, size);
		struct timespec delay = { .tv_nsec = 350000000 };
		nanosleep(&delay, NULL);
		if (!write_comm_reply(success)) exit(1);
		if (success) exit(0);
	}
}
