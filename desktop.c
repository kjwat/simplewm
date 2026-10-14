/* SimpleWM policy, reload, and on-demand IPC. Included by simplewm.c. */
typedef struct {
 struct wl_list link;
 struct wlr_pointer *pointer;
 struct wl_listener destroy;
} PointerDevice;
static struct wl_list pointer_devices;
static pid_t wallpaper_pid=-1, style_pid=-1, services_pid=-1;
static int ipc_fd=-1;
static char ipc_path[sizeof(((struct sockaddr_un *)0)->sun_path)];
static struct wl_event_source *ipc_source;
static struct wl_event_source *reload_source;

static void forget_pointer(struct wl_listener *listener, void *data)
{
 PointerDevice *p=wl_container_of(listener,p,destroy);
 wl_list_remove(&p->destroy.link); wl_list_remove(&p->link); free(p);
}
static void remember_pointer(struct wlr_pointer *pointer)
{
 PointerDevice *p=ecalloc(1,sizeof(*p)); p->pointer=pointer;
 wl_list_insert(&pointer_devices,&p->link);
 LISTEN(&pointer->base.events.destroy,&p->destroy,forget_pointer);
}
static void configure_pointer(struct wlr_pointer *pointer)
{
 struct libinput_device *d;
 if (!wlr_input_device_is_libinput(&pointer->base) || !(d=wlr_libinput_get_device_handle(&pointer->base))) return;
 int pad=libinput_device_config_tap_get_finger_count(d)>0;
 for (int i=0;i<cfg.ninputs;i++) {
  InputRule *in=&cfg.inputs[i];
  if (!strcmp(in->name,"touchpad")) { if (!pad) continue; }
  else if (!strcmp(in->name,"pointer")) { if (pad) continue; }
  else if (fnmatch(in->name,pointer->base.name,0)) continue;
  if (pad) {
   if (in->tap>=0) libinput_device_config_tap_set_enabled(d,in->tap);
   if (in->drag>=0) libinput_device_config_tap_set_drag_enabled(d,in->drag);
   if (in->draglock>=0) libinput_device_config_tap_set_drag_lock_enabled(d,in->draglock);
  }
  if (in->natural>=0) libinput_device_config_scroll_set_natural_scroll_enabled(d,in->natural);
  if (in->dwt>=0 && libinput_device_config_dwt_is_available(d)) libinput_device_config_dwt_set_enabled(d,in->dwt);
  if (in->left>=0) libinput_device_config_left_handed_set(d,in->left);
  if (in->middle>=0) libinput_device_config_middle_emulation_set_enabled(d,in->middle);
  if (in->profile>=0 && libinput_device_config_accel_is_available(d)) {
   enum libinput_config_accel_profile profile=in->profile?(enum libinput_config_accel_profile)in->profile:libinput_device_config_accel_get_default_profile(d);
   libinput_device_config_accel_set_profile(d,profile);
  }
  if (isfinite(in->speed)) libinput_device_config_accel_set_speed(d,in->speed);
  if (in->click>=0) libinput_device_config_click_set_method(d,in->click?(enum libinput_config_click_method)in->click:libinput_device_config_click_get_default_method(d));
  if (in->scroll>=0) libinput_device_config_scroll_set_method(d,in->scroll?(enum libinput_config_scroll_method)in->scroll:libinput_device_config_scroll_get_default_method(d));
 }
}
static void configure_output(const Config *c, Monitor *m, struct wlr_output_state *state, int position)
{
 struct wlr_output *out=m->wlr_output;
 wlr_output_state_set_enabled(state,1);
 for (int i=0;i<c->noutputs;i++) {
  const OutputRule *o=&c->outputs[i];
  if (fnmatch(o->name,out->name,0)) continue;
  if (o->scale>0) wlr_output_state_set_scale(state,o->scale);
  if (o->transform>=0) wlr_output_state_set_transform(state,o->transform);
  if (o->enabled>=0) wlr_output_state_set_enabled(state,o->enabled);
  if (o->adaptive>=0) wlr_output_state_set_adaptive_sync_enabled(state,o->adaptive);
  if (position && o->x!=INT_MIN) { m->m.x=o->x; m->m.y=o->y; }
  if (o->width==0) {
   struct wlr_output_mode *mode=wlr_output_preferred_mode(out);
   if (mode) wlr_output_state_set_mode(state,mode);
  } else if (o->width>0) {
   struct wlr_output_mode *mode, *match=NULL;
   wl_list_for_each(mode,&out->modes,link) if (mode->width==o->width && mode->height==o->height && (!o->refresh || mode->refresh==o->refresh)) { match=mode; break; }
   if (match) wlr_output_state_set_mode(state,match);
   else wlr_output_state_set_custom_mode(state,o->width,o->height,o->refresh?o->refresh:60000);
  }
 }
}
static int tiled_client(Client *c, Monitor *m)
{
 return VISIBLEON(c,m) && !c->isfloating && !c->isfullscreen && !c->ismaximized;
}
static void columns(Monitor *m)
{
 Client *c; int n=0,index=0;
 wl_list_for_each(c,&clients,link) if (tiled_client(c,m)) n++;
 if (!n) return;
 int cols=n<3?n:(int)ceil(sqrt((double)n));
 if (m->w.width<900 && n>2) cols=2;
 int outer=(cfg.smart_gaps && n==1)?0:(int)cfg.outer_gap;
 outer=MIN(outer,MIN(m->w.width,m->w.height)/8);
 int gap=MIN((int)cfg.gap,MIN(m->w.width,m->w.height)/16);
 int width=m->w.width-2*outer, height=m->w.height-2*outer;
 wl_list_for_each(c,&clients,link) {
  if (!tiled_client(c,m)) continue;
  int column=index%cols, row=index/cols, rows=(n+cols-1-column)/cols;
  int x0=(width+gap)*column/cols, x1=(width+gap)*(column+1)/cols-gap;
  int y0=(height+gap)*row/rows, y1=(height+gap)*(row+1)/rows-gap;
  resize(c,(struct wlr_box){m->w.x+outer+x0,m->w.y+outer+y0,MAX(1,x1-x0),MAX(1,y1-y0)},0);
  index++;
 }
}
static void setmaximized(Client *c, int on)
{
 if (!c || !c->mon || !client_surface(c)->mapped || on==c->ismaximized) return;
 if (on) {
  if (c->isfullscreen) setfullscreen(c,0);
  c->restore_geom=c->geom; c->restore_floating=c->isfloating;
  c->ismaximized=1;
  wlr_scene_node_reparent(&c->scene->node,layers[c->isfloating?LyrFloat:LyrTile]);
 } else {
  c->ismaximized=0; c->isfloating=c->restore_floating;
  wlr_scene_node_reparent(&c->scene->node,layers[c->isfloating?LyrFloat:LyrTile]);
 }
 if (!client_is_x11(c)) wlr_xdg_toplevel_set_maximized(c->surface.xdg->toplevel,on);
#ifdef XWAYLAND
 else wlr_xwayland_surface_set_maximized(c->surface.xwayland,on);
#endif
 if (!on && c->isfloating) resize(c,c->restore_geom,1);
 arrange(c->mon);
 focusclient(c,1);
}
static void run_shell(const char *command)
{
 if (fork()==0) {
  setsid(); dup2(STDERR_FILENO,STDOUT_FILENO);
  execl("/bin/sh","sh","-c",command,(char *)NULL); _exit(127);
 }
}
static void stop_child(pid_t *pid)
{
 if (*pid>0) {
  /* A reaped child PID can be reused. Only signal if it is still our child. */
  int status; pid_t result=waitpid(*pid,&status,WNOHANG);
  if (!result) { kill(-*pid,SIGTERM); waitpid(*pid,NULL,0); }
 }
 *pid=-1;
}
static void start_wallpaper(void)
{
 stop_child(&wallpaper_pid);
 if (!*cfg.background || access(cfg.background,R_OK)) return;
 wallpaper_pid=fork();
 if (!wallpaper_pid) {
  setsid();
  execlp("swaybg","swaybg","-i",cfg.background,"-m",cfg.background_mode,(char *)NULL);
  _exit(127);
 }
}
static void start_style(void)
{
 stop_child(&style_pid);
 setenv("SIMPLEWM_FONT",cfg.font,1); setenv("SIMPLEWM_MONO_FONT",cfg.mono_font,1);
 setenv("SIMPLEWM_GTK_THEME",cfg.theme,1); unsetenv("GTK_THEME"); setenv("SIMPLEWM_FONT_HINTING",cfg.hinting,1);
 setenv("SIMPLEWM_FONT_RGBA",cfg.rgba,1); setenv("XCURSOR_THEME",cfg.cursor_theme,1);
 char size[32]; snprintf(size,sizeof(size),"%u",cfg.cursor_size); setenv("XCURSOR_SIZE",size,1);
 style_pid=fork();
 if (!style_pid) { setsid(); execlp("simplewm-style","simplewm-style",(char *)NULL); _exit(127); }
}
static int reload_config(void)
{
 Config *next=read_config(config_path); Monitor *m; Client *c; PointerDevice *p;
 if (!next) { fprintf(stderr,"SimpleWM reload: %s\n",config_error); return 0; }
 int active=0;
 wl_list_for_each(m,&mons,link) {
  struct wlr_output_state state; wlr_output_state_init(&state);
  configure_output(next,m,&state,0);
  int ok=wlr_output_test_state(m->wlr_output,&state);
  if (state.enabled) active++;
  wlr_output_state_finish(&state);
  if (!ok) { cfg_error(config_path,0,"output configuration rejected by hardware"); free(next); return 0; }
 }
 if (!active) { cfg_error(config_path,0,"configuration would disable every output"); free(next); return 0; }
 cfg=*next; free(next);
 struct xkb_context *ctx=xkb_context_new(XKB_CONTEXT_NO_FLAGS);
 struct xkb_rule_names names={.layout=cfg.kb_layout,.variant=cfg.kb_variant,.options=cfg.kb_options};
 struct xkb_keymap *keymap=xkb_keymap_new_from_names(ctx,&names,XKB_KEYMAP_COMPILE_NO_FLAGS);
 wlr_keyboard_set_keymap(&kb_group->wlr_group->keyboard,keymap);
 wlr_keyboard_set_repeat_info(&kb_group->wlr_group->keyboard,cfg.repeat_rate,cfg.repeat_delay);
 kb_group->nsyms=0; wl_event_source_timer_update(kb_group->key_repeat_source,0);
 xkb_keymap_unref(keymap); xkb_context_unref(ctx);
 wl_list_for_each(p,&pointer_devices,link) configure_pointer(p->pointer);
 wlr_xcursor_manager_destroy(cursor_mgr);
 cursor_mgr=wlr_xcursor_manager_create(cfg.cursor_theme,cfg.cursor_size);
 wl_list_for_each(m,&mons,link) {
  struct wlr_output_state state; wlr_output_state_init(&state);
  configure_output(&cfg,m,&state,1);
  if (!wlr_output_commit_state(m->wlr_output,&state)) fprintf(stderr,"SimpleWM: output commit failed for %s\n",m->wlr_output->name);
  wlr_output_state_finish(&state);
  m->mfact=cfg.ratio; m->lt[m->sellt]=&layouts[cfg.layout];
  if (m->wlr_output->enabled) {
   if (m->m.x==-1 && m->m.y==-1) wlr_output_layout_add_auto(output_layout,m->wlr_output);
   else wlr_output_layout_add(output_layout,m->wlr_output,m->m.x,m->m.y);
  }
 }
 wlr_scene_rect_set_color(root_bg,cfg.background_color);
 wl_list_for_each(c,&clients,link) {
  if (!c->isfullscreen) c->bw=cfg.border;
  client_set_border_color(c,c==focustop(c->mon)?cfg.focus_color:c->isurgent?cfg.urgent_color:cfg.border_color);
  resize(c,c->geom,c->isfloating);
 }
 updatemons(NULL,NULL);
 wl_list_for_each(m,&mons,link) arrange(m);
 start_wallpaper(); start_style();
 fprintf(stderr,"SimpleWM: reloaded %s\n",config_path); return 1;
}
static int reload_signal(int signal, void *data) { reload_config(); return 0; }
static Client *direction_client(Client *from, const char *direction)
{
 Client *c,*best=NULL; double score=HUGE_VAL;
 if (!from) return NULL;
 double x=from->geom.x+from->geom.width/2.0,y=from->geom.y+from->geom.height/2.0;
 wl_list_for_each(c,&clients,link) {
  if (c==from || !VISIBLEON(c,from->mon)) continue;
  double dx=c->geom.x+c->geom.width/2.0-x,dy=c->geom.y+c->geom.height/2.0-y;
  double along=!strcmp(direction,"left")?-dx:!strcmp(direction,"right")?dx:!strcmp(direction,"up")?-dy:dy;
  double across=(!strcmp(direction,"left") || !strcmp(direction,"right"))?fabs(dy):fabs(dx);
  if (along>0 && along+across*2<score) { best=c; score=along+across*2; }
 }
 return best;
}
static void swap_clients(Client *a, Client *b)
{
 if (!a || !b || a==b) return;
 struct wl_list *ap=a->link.prev,*bp=b->link.prev;
 if (a->link.next==&b->link) { wl_list_remove(&b->link); wl_list_insert(ap,&b->link); }
 else if (b->link.next==&a->link) { wl_list_remove(&a->link); wl_list_insert(bp,&a->link); }
 else { wl_list_remove(&a->link); wl_list_remove(&b->link); wl_list_insert(ap,&b->link); wl_list_insert(bp,&a->link); }
 arrange(a->mon);
}
static int dispatch(const Binding *b)
{
 Client *c=selmon?focustop(selmon):NULL; Arg arg={0};
 if (locked) return 0;
 switch (b->action) {
 case A_EXEC: run_shell(b->arg); break;
 case A_CLOSE: killclient(NULL); break;
 case A_MAXIMIZE: setmaximized(c,1); break;
 case A_RESTORE:
  if (c && c->isfullscreen) setfullscreen(c,0);
  if (c && c->ismaximized) setmaximized(c,0);
  break;
 case A_FULLSCREEN:
  if (c && !c->isfullscreen && c->ismaximized) setmaximized(c,0);
  togglefullscreen(NULL); break;
 case A_FLOAT:
  if (c && c->ismaximized) setmaximized(c,0);
  togglefloating(NULL); break;
 case A_FOCUS:
  if (!strcmp(b->arg,"next") || !strcmp(b->arg,"prev")) focusstack(&(Arg){.i=!strcmp(b->arg,"next")?1:-1});
  else { Client *next=direction_client(c,b->arg); if (next) focusclient(next,1); }
  break;
 case A_SWAP:
  if (!strcmp(b->arg,"next") || !strcmp(b->arg,"prev")) {
   Client *next=NULL,*candidate;
   if (c) wl_list_for_each(candidate,&clients,link) if (candidate!=c && VISIBLEON(candidate,selmon)) { next=candidate; break; }
   swap_clients(c,next);
  } else swap_clients(c,direction_client(c,b->arg));
  break;
 case A_WORKSPACE:
  if (!selmon) break;
  if (!strcmp(b->arg,"previous")) { view(&(Arg){0}); break; }
  if (!strcmp(b->arg,"next") || !strcmp(b->arg,"prev")) {
   int current=__builtin_ctz(selmon->tagset[selmon->seltags]);
   current+=!strcmp(b->arg,"next")?1:-1;
   if (current<0 || current>=TAGCOUNT) break;
   arg.ui=1u<<current;
  } else arg.ui=1u<<(atoi(b->arg)-1);
  view(&arg);
  break;
 case A_SEND: tag(&(Arg){.ui=1u<<(atoi(b->arg)-1)}); break;
 case A_LAYOUT: setlayout(&(Arg){.v=&layouts[cfg_layout(b->arg)]}); break;
 case A_RATIO: setmfact(&(Arg){.f=(float)atof(b->arg)}); break;
 case A_MONITOR: case A_SENDMON:
  arg.i=!strcmp(b->arg,"left")?WLR_DIRECTION_LEFT:!strcmp(b->arg,"right")?WLR_DIRECTION_RIGHT:!strcmp(b->arg,"up")?WLR_DIRECTION_UP:WLR_DIRECTION_DOWN;
  if (b->action==A_MONITOR) focusmon(&arg); else tagmon(&arg); break;
 case A_RELOAD: return reload_config();
 case A_EXIT: quit(NULL); break;
 case A_ZOOM: zoom(NULL); break;
 default: return 0;
 }
 return 1;
}
static void json_string(FILE *out, const char *s)
{
 fputc('"',out);
 if (s) for (int i=0;s[i] && i<256;i++) {
  unsigned char ch=s[i];
  if (ch=='"' || ch=='\\') { fputc('\\',out); fputc(ch,out); }
  else if (ch<32) fprintf(out,"\\u%04x",ch); else fputc(ch,out);
 }
 fputc('"',out);
}
static void status_json(FILE *out)
{
 Monitor *m; Client *c; int first=1;
 fprintf(out,"{\"ok\":true,\"locked\":%s,\"lock_client\":%s,\"config\":",locked?"true":"false",cur_lock?"true":"false"); json_string(out,config_path);
 fputs(",\"appearance\":{\"image\":",out); json_string(out,cfg.background);
 fputs(",\"mode\":",out); json_string(out,cfg.background_mode);
 fputs(",\"font\":",out); json_string(out,cfg.mono_font);
 fprintf(out,",\"background\":\"#%02x%02x%02x\",\"accent\":\"#%02x%02x%02x\",\"error\":\"#%02x%02x%02x\"}",
   (unsigned)lroundf(cfg.background_color[0]*255),(unsigned)lroundf(cfg.background_color[1]*255),(unsigned)lroundf(cfg.background_color[2]*255),
   (unsigned)lroundf(cfg.focus_color[0]*255),(unsigned)lroundf(cfg.focus_color[1]*255),(unsigned)lroundf(cfg.focus_color[2]*255),
   (unsigned)lroundf(cfg.urgent_color[0]*255),(unsigned)lroundf(cfg.urgent_color[1]*255),(unsigned)lroundf(cfg.urgent_color[2]*255));
 fputs(",\"outputs\":[",out);
 wl_list_for_each(m,&mons,link) {
  if (!first) fputc(',',out);
  first=0;
  fputs("{\"name\":",out); json_string(out,m->wlr_output->name);
  fprintf(out,",\"active\":%s,\"workspace\":%d,\"layout\":",m==selmon?"true":"false",__builtin_ctz(m->tagset[m->seltags])+1);
  json_string(out,m->lt[m->sellt]->symbol);
  fprintf(out,",\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d,\"scale\":%.3f}",m->w.x,m->w.y,m->w.width,m->w.height,m->wlr_output->scale);
 }
 fputs("],\"clients\":[",out); first=1;
 wl_list_for_each(c,&clients,link) {
  if (!first) fputc(',',out);
  first=0;
  fputs("{\"app_id\":",out); json_string(out,client_get_appid(c)); fputs(",\"title\":",out); json_string(out,client_get_title(c));
  fprintf(out,",\"id\":%lu,\"workspace\":%d,\"active\":%s,\"visible\":%s,\"floating\":%s,\"maximized\":%s,\"fullscreen\":%s,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}",
    (unsigned long)c,c->tags?__builtin_ctz(c->tags)+1:0,c==focustop(selmon)?"true":"false",c->mon && VISIBLEON(c,c->mon)?"true":"false",
    c->isfloating?"true":"false",c->ismaximized?"true":"false",c->isfullscreen?"true":"false",c->geom.x,c->geom.y,c->geom.width,c->geom.height);
 }
 fputs("]}\n",out);
}
typedef struct { int fd; struct wl_event_source *source, *timeout; char buf[8192]; size_t used; } IpcPeer;
static void ipc_close(IpcPeer *p)
{
 wl_event_source_remove(p->source); wl_event_source_remove(p->timeout); close(p->fd); free(p);
}
static int ipc_timeout(void *data) { ipc_close(data); return 0; }
static int ipc_read(int fd, uint32_t mask, void *data)
{
 IpcPeer *p=data; ssize_t n=recv(fd,p->buf+p->used,sizeof(p->buf)-p->used-1,0);
 if (n<0 && (errno==EAGAIN || errno==EINTR)) return 0;
 if (n<=0 || (mask & WL_EVENT_ERROR)) { ipc_close(p); return 0; }
 p->used+=n; p->buf[p->used]=0;
 char *end=strchr(p->buf,'\n');
 if (!end && p->used<sizeof(p->buf)-1) return 0;
 if (end) *end=0;
 char *result=NULL; size_t len=0; FILE *out=open_memstream(&result,&len);
 if (out) {
  if (!strcmp(p->buf,"status")) status_json(out);
  else if (locked) fputs("{\"ok\":false,\"error\":\"session is locked\"}\n",out);
  else {
   char *space=strchr(p->buf,' '); if (space) *space++=0;
   Binding b={0};
   if (!cfg_action(p->buf,space?space:"",&b)) fputs("{\"ok\":false,\"error\":\"invalid command\"}\n",out);
   else if (dispatch(&b)) fputs("{\"ok\":true}\n",out);
   else { fputs("{\"ok\":false,\"error\":",out); json_string(out,config_error); fputs("}\n",out); }
  }
  fclose(out); send(fd,result,len,MSG_NOSIGNAL); free(result);
 }
 ipc_close(p); return 0;
}
static int ipc_accept(int fd, uint32_t mask, void *data)
{
 int peer=accept4(fd,NULL,NULL,SOCK_NONBLOCK|SOCK_CLOEXEC);
 if (peer<0) return 0;
 struct ucred cred; socklen_t length=sizeof(cred);
 if (getsockopt(peer,SOL_SOCKET,SO_PEERCRED,&cred,&length) || cred.uid!=getuid()) { close(peer); return 0; }
 IpcPeer *p=ecalloc(1,sizeof(*p)); p->fd=peer;
 p->source=wl_event_loop_add_fd(event_loop,peer,WL_EVENT_READABLE,ipc_read,p);
 p->timeout=wl_event_loop_add_timer(event_loop,ipc_timeout,p); wl_event_source_timer_update(p->timeout,2000);
 return 0;
}
static void desktop_start(void)
{
 struct sockaddr_un addr={.sun_family=AF_UNIX};
 int n=snprintf(ipc_path,sizeof(ipc_path),"%s/simplewm-%s.ctl",getenv("XDG_RUNTIME_DIR"),getenv("WAYLAND_DISPLAY"));
 if (n<0 || n>=(int)sizeof(ipc_path)) die("IPC socket path too long");
 strcpy(addr.sun_path,ipc_path);
 ipc_fd=socket(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
 if (ipc_fd<0 || bind(ipc_fd,(struct sockaddr *)&addr,sizeof(addr)) || chmod(ipc_path,0600) || listen(ipc_fd,16)) die("cannot create SimpleWM control socket:");
 setenv("SIMPLEWM_SOCKET",ipc_path,1);
 ipc_source=wl_event_loop_add_fd(event_loop,ipc_fd,WL_EVENT_READABLE,ipc_accept,NULL);
 reload_source=wl_event_loop_add_signal(event_loop,SIGHUP,reload_signal,NULL);
 start_style(); start_wallpaper();
 for (int i=0;i<cfg.nstartups;i++) {
  if (strstr(cfg.startups[i],"simplewm-services")) {
   services_pid=fork();
   if (!services_pid) { setsid(); execl("/bin/sh","sh","-c",cfg.startups[i],(char *)NULL); _exit(127); }
  } else run_shell(cfg.startups[i]);
 }
}
static void desktop_cleanup(void)
{
 stop_child(&wallpaper_pid); stop_child(&style_pid); stop_child(&services_pid);
 if (ipc_source) wl_event_source_remove(ipc_source);
 if (reload_source) wl_event_source_remove(reload_source);
 if (ipc_fd>=0) { close(ipc_fd); unlink(ipc_path); }
}
