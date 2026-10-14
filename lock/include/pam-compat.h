/* Linux-PAM's stable application ABI, from pam_appl.h and _pam_types.h.
 * Copyright Theodore Ts'o, 1996. All rights reserved.
 * Copyright (c) Andrew G. Morgan <morgan@linux.kernel.org>, 1996-8.
 * See LICENSE.pam for the complete permission and warranty notices.
 *
 * The original ISO updater does not install libpam0g-dev. These declarations
 * let it build against the system's existing libpam.so.0, without fetching
 * dependencies during make or changing the distro's authentication policy.
 */
#ifndef SIMPLEWM_PAM_COMPAT_H
#define SIMPLEWM_PAM_COMPAT_H
typedef struct pam_handle pam_handle_t;
#define PAM_SUCCESS 0
#define PAM_AUTH_ERR 7
#define PAM_CRED_INSUFFICIENT 8
#define PAM_AUTHINFO_UNAVAIL 9
#define PAM_MAXTRIES 11
#define PAM_ABORT 26
#define PAM_REFRESH_CRED 0x0010U
#define PAM_PROMPT_ECHO_OFF 1
#define PAM_PROMPT_ECHO_ON 2
#define PAM_ERROR_MSG 3
#define PAM_TEXT_INFO 4
struct pam_message { int msg_style; const char *msg; };
struct pam_response { char *resp; int resp_retcode; };
struct pam_conv {
	int (*conv)(int num_msg, const struct pam_message **msg,
		struct pam_response **resp, void *appdata_ptr);
	void *appdata_ptr;
};
extern int pam_start(const char *service_name, const char *user,
	const struct pam_conv *pam_conversation, pam_handle_t **pamh);
extern int pam_end(pam_handle_t *pamh, int pam_status);
extern int pam_authenticate(pam_handle_t *pamh, int flags);
extern int pam_setcred(pam_handle_t *pamh, int flags);
#endif
