/* SimpleWM configuration is read from a text file, never compiled in. */
#define TAGCOUNT 9
#define CFG_BINDINGS 160
#define CFG_RULES 64
#define CFG_OUTPUTS 32
#define CFG_INPUTS 32
#define CFG_STARTUPS 32
#define CFG_TEXT 1024

enum Action {
 A_EXEC, A_CLOSE, A_MAXIMIZE, A_RESTORE, A_FULLSCREEN, A_FLOAT,
 A_FOCUS, A_SWAP, A_WORKSPACE, A_SEND, A_PREVIOUS, A_LAYOUT,
 A_RATIO, A_MONITOR, A_SENDMON, A_RELOAD, A_EXIT, A_ZOOM
};
typedef struct {
 uint32_t mod;
 xkb_keysym_t sym;
 enum Action action;
 char arg[CFG_TEXT];
} Binding;
typedef struct {
 char app[256], title[256];
 int workspace, floating, monitor;
} AppRule;
typedef struct {
 char name[128];
 float scale;
 int x, y, width, height, refresh, transform, adaptive, enabled;
} OutputRule;
typedef struct {
 char name[256];
 int touchpad, natural, tap, drag, draglock, dwt, left, middle;
 int profile, click, scroll;
 double speed;
} InputRule;
typedef struct {
 unsigned int border, gap, outer_gap, cursor_size;
 int smart_gaps, focus_follows_mouse, repeat_rate, repeat_delay, layout;
 float ratio, background_color[4], border_color[4], focus_color[4], urgent_color[4];
 char background[CFG_TEXT], background_mode[32], font[128], mono_font[128];
 char theme[128], cursor_theme[128], hinting[32], rgba[32];
 char kb_layout[128], kb_variant[128], kb_options[256];
 Binding bindings[CFG_BINDINGS];
 AppRule rules[CFG_RULES];
 OutputRule outputs[CFG_OUTPUTS];
 InputRule inputs[CFG_INPUTS];
 char startups[CFG_STARTUPS][CFG_TEXT];
 int nbindings, nrules, noutputs, ninputs, nstartups;
} Config;
static Config cfg;
static char config_path[PATH_MAX];
static int log_level = WLR_ERROR;
static const int bypass_surface_visibility = 0;
static const float fullscreen_bg[4] = {0.035f, 0.04f, 0.04f, 1.0f};
#define sloppyfocus (cfg.focus_follows_mouse)
#define borderpx (cfg.border)
#define rootcolor (cfg.background_color)
#define bordercolor (cfg.border_color)
#define focuscolor (cfg.focus_color)
#define urgentcolor (cfg.urgent_color)
#define MODKEY WLR_MODIFIER_LOGO
static const Layout layouts[] = {
 { "columns", columns }, { "stack", tile }, { "paper", monocle }, { "float", NULL }
};
static const Button buttons[] = {
 { MODKEY, BTN_LEFT, moveresize, {.ui = CurMove} },
 { MODKEY, BTN_RIGHT, moveresize, {.ui = CurResize} },
 { MODKEY, BTN_MIDDLE, togglefloating, {0} }
};
