/* Strict, bounded text configuration. Included by simplewm.c. */
typedef struct { char name[64], value[CFG_TEXT]; } ConfigVar;
typedef struct { Config *out; ConfigVar vars[32]; int nvars, depth; } ConfigReader;
static char config_error[CFG_TEXT];

static int cfg_error(const char *file, int line, const char *why)
{
 snprintf(config_error, sizeof(config_error), "%.700s:%d: %.250s", file, line, why);
 return 0;
}
static int cfg_bool(const char *s, int *v)
{
 if (!strcmp(s,"yes") || !strcmp(s,"true") || !strcmp(s,"1")) *v=1;
 else if (!strcmp(s,"no") || !strcmp(s,"false") || !strcmp(s,"0")) *v=0;
 else return 0;
 return 1;
}
static int cfg_num(const char *s, double min, double max, double *v)
{
 char *end;
 errno=0;
 *v=strtod(s,&end);
 return !errno && end!=s && !*end && isfinite(*v) && *v>=min && *v<=max;
}
static int cfg_int(const char *s, int min, int max, int *v)
{
 double n;
 if (!cfg_num(s,min,max,&n) || floor(n)!=n) return 0;
 *v=(int)n; return 1;
}
static int cfg_color(const char *s, float col[4])
{
 char *end; unsigned long n; size_t len;
 if (*s=='#') s++;
 len=strlen(s);
 if (len!=6 && len!=8) return 0;
 for (size_t i=0;i<len;i++) if (!isxdigit((unsigned char)s[i])) return 0;
 n=strtoul(s,&end,16); if (*end) return 0;
 if (len==6) n=(n<<8)|255;
 for (int i=0;i<4;i++) col[i]=((n>>((3-i)*8))&255)/255.0f;
 return 1;
}
static int cfg_copy(char *to, size_t cap, const char *from)
{
 if (strlen(from)>=cap) return 0;
 strcpy(to,from); return 1;
}
static int cfg_expand(ConfigReader *r, const char *in, char *out, size_t cap)
{
 size_t used=0;
 while (*in) {
  int found=-1;
  if (*in=='$') for (int i=r->nvars-1;i>=0;i--) {
   size_t n=strlen(r->vars[i].name);
   if (!strncmp(in,r->vars[i].name,n) && !(isalnum((unsigned char)in[n]) || in[n]=='_')) { found=i; break; }
  }
  if (found>=0) {
   size_t n=strlen(r->vars[found].value);
   if (used+n>=cap) return 0;
   memcpy(out+used,r->vars[found].value,n); used+=n;
   in+=strlen(r->vars[found].name);
  } else {
   if (used+1>=cap) return 0;
   out[used++]=*in++;
  }
 }
 out[used]=0; return 1;
}
static int cfg_tokens(char *line, char words[64][CFG_TEXT], const char *start[64])
{
 char *p=line; int count=0;
 while (*p) {
  size_t n=0; char quote=0;
  while (isspace((unsigned char)*p)) p++;
  if (!*p || (*p=='#' && (!p[1] || isspace((unsigned char)p[1])))) { *p=0; break; }
  if (count==64) return -1;
  start[count]=p;
  while (*p && (quote || !isspace((unsigned char)*p))) {
   if (*p=='"' || *p=='\'') {
    if (!quote) { quote=*p++; continue; }
    if (quote==*p) { quote=0; p++; continue; }
   }
   if (*p=='\\' && p[1] && quote!='\'') p++;
   if (n+1>=CFG_TEXT) return -1;
   words[count][n++]=*p++;
  }
  if (quote) return -1;
  words[count++][n]=0;
 }
 return count;
}
static int cfg_layout(const char *s)
{
 for (int i=0;i<(int)LENGTH(layouts);i++) if (!strcmp(s,layouts[i].symbol)) return i;
 return -1;
}
static int cfg_key(const char *s, Binding *b)
{
 char value[256], *save, *part, *last;
 if (!cfg_copy(value,sizeof(value),s)) return 0;
 b->mod=0;
 part=strtok_r(value,"+",&save);
 if (!part) return 0;
 while ((last=strtok_r(NULL,"+",&save))) {
  if (!strcasecmp(part,"super") || !strcasecmp(part,"mod4")) b->mod|=WLR_MODIFIER_LOGO;
  else if (!strcasecmp(part,"ctrl") || !strcasecmp(part,"control")) b->mod|=WLR_MODIFIER_CTRL;
  else if (!strcasecmp(part,"alt") || !strcasecmp(part,"mod1")) b->mod|=WLR_MODIFIER_ALT;
  else if (!strcasecmp(part,"shift")) b->mod|=WLR_MODIFIER_SHIFT;
  else return 0;
  part=last;
 }
 b->sym=xkb_keysym_from_name(part,XKB_KEYSYM_CASE_INSENSITIVE);
 if (b->sym==XKB_KEY_NoSymbol) return 0;
 b->sym=xkb_keysym_to_lower(b->sym); return 1;
}
static int cfg_action(const char *s, const char *arg, Binding *b)
{
 static const struct { const char *name; enum Action action; } actions[]={
  {"exec",A_EXEC},{"close",A_CLOSE},{"maximize",A_MAXIMIZE},{"restore",A_RESTORE},
  {"fullscreen",A_FULLSCREEN},{"floating",A_FLOAT},{"focus",A_FOCUS},{"swap",A_SWAP},
  {"workspace",A_WORKSPACE},{"send",A_SEND},{"layout",A_LAYOUT},{"ratio",A_RATIO},
  {"monitor",A_MONITOR},{"send_monitor",A_SENDMON},{"reload",A_RELOAD},{"exit",A_EXIT},{"promote",A_ZOOM}
 };
 int i, n; double number;
 for (i=0;i<(int)LENGTH(actions);i++) if (!strcmp(s,actions[i].name)) break;
 if (i==(int)LENGTH(actions) || !cfg_copy(b->arg,sizeof(b->arg),arg)) return 0;
 b->action=actions[i].action;
 switch (b->action) {
 case A_EXEC: return !!*arg;
 case A_FOCUS: case A_SWAP:
  return !strcmp(arg,"next") || !strcmp(arg,"prev") || !strcmp(arg,"left") || !strcmp(arg,"right") || !strcmp(arg,"up") || !strcmp(arg,"down");
 case A_WORKSPACE:
  if (!strcmp(arg,"next") || !strcmp(arg,"prev") || !strcmp(arg,"previous")) return 1;
  return cfg_int(arg,1,TAGCOUNT,&n);
 case A_SEND: return cfg_int(arg,1,TAGCOUNT,&n);
 case A_LAYOUT: return cfg_layout(arg)>=0;
 case A_RATIO: return cfg_num(arg,-0.9,0.9,&number);
 case A_MONITOR: case A_SENDMON:
  return !strcmp(arg,"left") || !strcmp(arg,"right") || !strcmp(arg,"up") || !strcmp(arg,"down");
 default: return !*arg;
 }
}
static int cfg_read(ConfigReader *r, const char *path);
static int cfg_path(const char *value, const char *base, char *out, size_t cap)
{
 int n;
 if (value[0]=='~' && value[1]=='/') n=snprintf(out,cap,"%s/%s",getenv("HOME")?getenv("HOME"):"",value+2);
 else if (value[0]=='/') n=snprintf(out,cap,"%s",value);
 else {
  char parent[PATH_MAX], *slash;
  if (!cfg_copy(parent,sizeof(parent),base)) return 0;
  slash=strrchr(parent,'/'); if (slash) *slash=0; else strcpy(parent,".");
  n=snprintf(out,cap,"%s/%s",parent,value);
 }
 return n>=0 && (size_t)n<cap;
}
static int cfg_line(ConfigReader *r, char *line, const char *file, int lineno)
{
 char expanded[8192], words[64][CFG_TEXT], path[PATH_MAX];
 const char *start[64]; int n, value; double number; Config *c=r->out;
 while (isspace((unsigned char)*line)) line++;
 if (!*line || *line=='#') return 1;
 /* A variable's name must remain literal when it is redefined in an include. */
 if (!strncmp(line,"set",3) && isspace((unsigned char)line[3])) {
  if (!cfg_copy(expanded,sizeof(expanded),line)) return cfg_error(file,lineno,"line is too long");
 } else if (!cfg_expand(r,line,expanded,sizeof(expanded))) return cfg_error(file,lineno,"expanded line is too long");
 n=cfg_tokens(expanded,words,start);
 if (n<0) return cfg_error(file,lineno,"too many tokens, long token, or unclosed quote");
 if (!n) return 1;
#define IS(s) (!strcmp(words[0],s))
#define FAIL(s) return cfg_error(file,lineno,s)
#define COPY(field, index) do { if (!cfg_copy(c->field,sizeof(c->field),words[index])) { FAIL("value is too long"); } } while (0)
 if (IS("set")) {
  char replacement[CFG_TEXT];
  if (n<3 || words[1][0]!='$' || strlen(words[1])<2) { FAIL("expected: set $name value"); }
  for (const char *p=words[1]+1;*p;p++) if (!(isalnum((unsigned char)*p) || *p=='_')) { FAIL("invalid variable name"); }
  if (!cfg_expand(r,start[2],replacement,sizeof(replacement))) { FAIL("variable is too long"); }
  for (value=0;value<r->nvars;value++) if (!strcmp(r->vars[value].name,words[1])) break;
  if (value==32) { FAIL("too many variables"); }
  if (value==r->nvars) r->nvars++;
  if (!cfg_copy(r->vars[value].name,sizeof(r->vars[value].name),words[1]) ||
      !cfg_copy(r->vars[value].value,sizeof(r->vars[value].value),replacement)) { FAIL("variable is too long"); }
 } else if (IS("include")) {
  glob_t matches={0}; int result;
  if (n!=2 || !cfg_path(words[1],file,path,sizeof(path))) { FAIL("expected: include path"); }
  result=glob(path,0,NULL,&matches);
  if (result==GLOB_NOMATCH && strpbrk(path,"*?[")) { globfree(&matches); return 1; }
  if (result) { globfree(&matches); FAIL("include matched no readable files"); }
  for (size_t i=0;i<matches.gl_pathc;i++) if (!cfg_read(r,matches.gl_pathv[i])) { globfree(&matches); return 0; }
  globfree(&matches);
 } else if (IS("bindsym")) {
  Binding b={0};
  if (n<3 || !cfg_key(words[1],&b) || !cfg_action(words[2],n>3?start[3]:"",&b)) { FAIL("invalid binding, action, or action argument"); }
  for (value=0;value<c->nbindings;value++) if (c->bindings[value].mod==b.mod && c->bindings[value].sym==b.sym) break;
  if (value==CFG_BINDINGS) { FAIL("too many bindings"); }
  if (value==c->nbindings) c->nbindings++;
  c->bindings[value]=b;
 } else if (IS("exec")) {
  if (n<2 || c->nstartups==CFG_STARTUPS || !cfg_copy(c->startups[c->nstartups++],CFG_TEXT,start[1])) { FAIL("invalid startup command"); }
 } else if (IS("layout")) {
  if (n!=2 || (value=cfg_layout(words[1]))<0) { FAIL("layout must be columns, stack, paper, or float"); }
  c->layout=value;
 } else if (IS("border") || IS("cursor_size") || IS("repeat_rate") || IS("repeat_delay")) {
  int min=IS("cursor_size")?8:0, max=IS("repeat_delay")?5000:IS("repeat_rate")?100:IS("border")?16:128;
  if (n!=2 || !cfg_int(words[1],min,max,&value)) { FAIL("integer out of range"); }
  if (IS("border")) c->border=value; else if (IS("cursor_size")) c->cursor_size=value;
  else if (IS("repeat_rate")) c->repeat_rate=value; else c->repeat_delay=value;
 } else if (IS("gaps")) {
  if (n!=3 || !cfg_int(words[2],0,256,&value)) { FAIL("expected: gaps inner|outer 0..256"); }
  if (!strcmp(words[1],"inner")) c->gap=value;
  else if (!strcmp(words[1],"outer")) c->outer_gap=value;
  else { FAIL("gap must be inner or outer"); }
 } else if (IS("smart_gaps") || IS("focus_follows_mouse")) {
  if (n!=2 || !cfg_bool(words[1],&value)) { FAIL("expected yes or no"); }
  if (IS("smart_gaps")) c->smart_gaps=value; else c->focus_follows_mouse=value;
 } else if (IS("master_ratio")) {
  if (n!=2 || !cfg_num(words[1],0.1,0.9,&number)) { FAIL("master_ratio must be 0.1..0.9"); }
  c->ratio=(float)number;
 } else if (IS("color")) {
  float *col=NULL;
  if (n!=3) { FAIL("expected: color background|inactive|focused|urgent #RRGGBB"); }
  if (!strcmp(words[1],"background")) col=c->background_color;
  if (!strcmp(words[1],"inactive")) col=c->border_color;
  if (!strcmp(words[1],"focused")) col=c->focus_color;
  if (!strcmp(words[1],"urgent")) col=c->urgent_color;
  if (!col || !cfg_color(words[2],col)) { FAIL("invalid color"); }
 } else if (IS("background")) {
  if (n!=2 && n!=3) { FAIL("expected: background path [fit|fill|center|stretch|tile]"); }
  if (!strcmp(words[1],"none")) c->background[0]=0;
  else if (!cfg_path(words[1],file,c->background,sizeof(c->background))) { FAIL("background path is too long"); }
  if (n==3) {
   if (strcmp(words[2],"fit") && strcmp(words[2],"fill") && strcmp(words[2],"center") && strcmp(words[2],"stretch") && strcmp(words[2],"tile")) { FAIL("invalid background mode"); }
   COPY(background_mode,2);
  }
 } else if (IS("font") || IS("monospace_font") || IS("gtk_theme") || IS("cursor_theme") || IS("keyboard_layout") || IS("keyboard_variant") || IS("keyboard_options") || IS("font_hinting") || IS("font_rgba")) {
  if (n!=2) { FAIL("expected one quoted value"); }
  if (IS("font")) { COPY(font,1); } else if (IS("monospace_font")) { COPY(mono_font,1); }
  else if (IS("gtk_theme")) { COPY(theme,1); } else if (IS("cursor_theme")) { COPY(cursor_theme,1); }
  else if (IS("keyboard_layout")) { COPY(kb_layout,1); } else if (IS("keyboard_variant")) { COPY(kb_variant,1); }
  else if (IS("keyboard_options")) { COPY(kb_options,1); }
  else if (IS("font_hinting")) {
   if (strcmp(words[1],"none") && strcmp(words[1],"slight") && strcmp(words[1],"medium") && strcmp(words[1],"full")) { FAIL("invalid font hinting"); }
   COPY(hinting,1);
  } else {
   if (strcmp(words[1],"none") && strcmp(words[1],"rgb") && strcmp(words[1],"bgr") && strcmp(words[1],"vrgb") && strcmp(words[1],"vbgr")) { FAIL("invalid subpixel order"); }
   COPY(rgba,1);
  }
 } else if (IS("rule")) {
  AppRule *rule;
  if (n<2 || c->nrules==CFG_RULES) { FAIL("invalid application rule"); }
  rule=&c->rules[c->nrules++]; rule->floating=-1; rule->monitor=-1;
  strcpy(rule->app,"*"); strcpy(rule->title,"*");
  for (int i=1;i<n;i++) {
   char *eq=strchr(words[i],'='); if (!eq) { FAIL("rule options use key=value"); } *eq++=0;
   if (!strcmp(words[i],"app_id")) { if (!cfg_copy(rule->app,sizeof(rule->app),eq)) { FAIL("app_id is too long"); } }
   else if (!strcmp(words[i],"title")) { if (!cfg_copy(rule->title,sizeof(rule->title),eq)) { FAIL("title is too long"); } }
   else if (!strcmp(words[i],"workspace")) { if (!cfg_int(eq,1,TAGCOUNT,&rule->workspace)) { FAIL("invalid workspace"); } }
   else if (!strcmp(words[i],"floating")) { if (!cfg_bool(eq,&rule->floating)) { FAIL("invalid floating value"); } }
   else if (!strcmp(words[i],"monitor")) { if (!cfg_int(eq,0,31,&rule->monitor)) { FAIL("invalid monitor index"); } }
   else { FAIL("unknown rule option"); }
  }
 } else if (IS("input")) {
  InputRule *in;
  if (n<3 || c->ninputs==CFG_INPUTS) { FAIL("expected: input name key=value ..."); }
  in=&c->inputs[c->ninputs++];
  in->natural=in->tap=in->drag=in->draglock=in->dwt=in->left=in->middle=-1;
  in->profile=in->click=in->scroll=-1; in->speed=NAN;
  if (!cfg_copy(in->name,sizeof(in->name),words[1])) { FAIL("input name is too long"); }
  for (int i=2;i<n;i++) {
   char *eq=strchr(words[i],'='); int *boolean=NULL;
   if (!eq) { FAIL("input options use key=value"); } *eq++=0;
   if (!strcmp(words[i],"natural_scroll")) boolean=&in->natural;
   else if (!strcmp(words[i],"tap")) boolean=&in->tap;
   else if (!strcmp(words[i],"tap_drag")) boolean=&in->drag;
   else if (!strcmp(words[i],"drag_lock")) boolean=&in->draglock;
   else if (!strcmp(words[i],"disable_while_typing")) boolean=&in->dwt;
   else if (!strcmp(words[i],"left_handed")) boolean=&in->left;
   else if (!strcmp(words[i],"middle_emulation")) boolean=&in->middle;
   if (boolean) { if (!cfg_bool(eq,boolean)) { FAIL("invalid input boolean"); } }
   else if (!strcmp(words[i],"accel_speed")) { if (!cfg_num(eq,-1,1,&in->speed)) { FAIL("accel_speed must be -1..1"); } }
   else if (!strcmp(words[i],"accel_profile")) {
    if (!strcmp(eq,"default")) in->profile=0;
    else if (!strcmp(eq,"flat")) in->profile=LIBINPUT_CONFIG_ACCEL_PROFILE_FLAT;
    else if (!strcmp(eq,"adaptive")) in->profile=LIBINPUT_CONFIG_ACCEL_PROFILE_ADAPTIVE;
    else { FAIL("invalid acceleration profile"); }
   } else if (!strcmp(words[i],"click")) {
    if (!strcmp(eq,"default")) in->click=0;
    else if (!strcmp(eq,"button_areas")) in->click=LIBINPUT_CONFIG_CLICK_METHOD_BUTTON_AREAS;
    else if (!strcmp(eq,"clickfinger")) in->click=LIBINPUT_CONFIG_CLICK_METHOD_CLICKFINGER;
    else { FAIL("invalid click method"); }
   } else if (!strcmp(words[i],"scroll")) {
    if (!strcmp(eq,"default")) in->scroll=0;
    else if (!strcmp(eq,"two_finger")) in->scroll=LIBINPUT_CONFIG_SCROLL_2FG;
    else if (!strcmp(eq,"edge")) in->scroll=LIBINPUT_CONFIG_SCROLL_EDGE;
    else if (!strcmp(eq,"button")) in->scroll=LIBINPUT_CONFIG_SCROLL_ON_BUTTON_DOWN;
    else { FAIL("invalid scrolling method"); }
   } else { FAIL("unknown input option"); }
  }
 } else if (IS("output")) {
  OutputRule *o;
  if (n<3 || c->noutputs==CFG_OUTPUTS) { FAIL("expected: output name key=value ..."); }
  o=&c->outputs[c->noutputs++]; o->scale=-1; o->x=o->y=INT_MIN;
  o->width=o->height=o->refresh=o->transform=o->adaptive=o->enabled=-1;
  if (!cfg_copy(o->name,sizeof(o->name),words[1])) { FAIL("output name is too long"); }
  for (int i=2;i<n;i++) {
   char *eq=strchr(words[i],'='); if (!eq) { FAIL("output options use key=value"); } *eq++=0;
   if (!strcmp(words[i],"scale")) { if (!cfg_num(eq,0.5,4,&number)) { FAIL("scale must be 0.5..4"); } o->scale=number; }
   else if (!strcmp(words[i],"enabled")) { if (!cfg_bool(eq,&o->enabled)) { FAIL("invalid output enabled value"); } }
   else if (!strcmp(words[i],"adaptive_sync")) { if (!cfg_bool(eq,&o->adaptive)) { FAIL("invalid adaptive_sync value"); } }
   else if (!strcmp(words[i],"position")) {
    char tail; if (!strcmp(eq,"auto")) o->x=o->y=-1;
    else if (sscanf(eq,"%d,%d%c",&o->x,&o->y,&tail)!=2 || o->x<0 || o->y<0 || o->x>32768 || o->y>32768) { FAIL("position must be auto or nonnegative x,y"); }
   } else if (!strcmp(words[i],"mode")) {
    char tail; int w=0,h=0,hz=0;
    if (!strcmp(eq,"preferred")) o->width=o->height=o->refresh=0;
    else {
     int ok=sscanf(eq,"%dx%d@%d%c",&w,&h,&hz,&tail)==3;
     if (!ok) ok=sscanf(eq,"%dx%d%c",&w,&h,&tail)==2;
     if (!ok || w<320 || h<200 || w>16384 || h>16384 || hz<0 || hz>1000) { FAIL("mode must be preferred or WIDTHxHEIGHT[@HZ]"); }
     o->width=w; o->height=h; o->refresh=hz*1000;
    }
   } else if (!strcmp(words[i],"transform")) {
    static const char *names[]={"normal","90","180","270","flipped","flipped-90","flipped-180","flipped-270"};
    for (value=0;value<8;value++) if (!strcmp(eq,names[value])) break;
    if (value==8) { FAIL("invalid output transform"); } o->transform=value;
   } else { FAIL("unknown output option"); }
  }
 } else { FAIL("unknown configuration directive"); }
#undef IS
#undef FAIL
#undef COPY
 return 1;
}
static int cfg_read(ConfigReader *r, const char *path)
{
 FILE *file; char *line=NULL; size_t cap=0; ssize_t len; int lineno=0,ok=1;
 if (++r->depth>8) { r->depth--; return cfg_error(path,0,"include nesting exceeds 8 (possible cycle)"); }
 file=fopen(path,"r");
 if (!file) { r->depth--; return cfg_error(path,0,strerror(errno)); }
 while ((len=getline(&line,&cap,file))>=0) {
  lineno++;
  if (len>8191 || memchr(line,0,(size_t)len)) { ok=cfg_error(path,lineno,"line too long or contains NUL"); break; }
  while (len>0 && (line[len-1]=='\n' || line[len-1]=='\r')) line[--len]=0;
  if (!(ok=cfg_line(r,line,path,lineno))) break;
 }
 if (ferror(file)) ok=cfg_error(path,lineno,"error reading file");
 free(line); fclose(file); r->depth--; return ok;
}
static Config *read_config(const char *path)
{
 Config *c=ecalloc(1,sizeof(*c)); ConfigReader r={.out=c};
 struct xkb_context *ctx; struct xkb_keymap *map;
 struct xkb_rule_names names={0};
 c->border=1; c->gap=8; c->outer_gap=12; c->smart_gaps=1; c->cursor_size=24;
 c->repeat_rate=33; c->repeat_delay=500; c->ratio=0.55f;
 strcpy(c->font,"Ubuntu Sans 11"); strcpy(c->mono_font,"Ubuntu Sans Mono 12");
 strcpy(c->theme,"Yaru-red-dark"); strcpy(c->cursor_theme,"Yaru");
 strcpy(c->hinting,"slight"); strcpy(c->rgba,"rgb"); strcpy(c->kb_layout,"us"); strcpy(c->background_mode,"fit");
 cfg_color("101313",c->background_color); cfg_color("343d3b",c->border_color);
 cfg_color("92a58e",c->focus_color); cfg_color("d3a175",c->urgent_color);
 if (!cfg_read(&r,path)) { free(c); return NULL; }
 names.layout=c->kb_layout; names.variant=c->kb_variant; names.options=c->kb_options;
 ctx=xkb_context_new(XKB_CONTEXT_NO_FLAGS);
 map=ctx?xkb_keymap_new_from_names(ctx,&names,XKB_KEYMAP_COMPILE_NO_FLAGS):NULL;
 if (!map) { cfg_error(path,0,"invalid keyboard layout, variant, or options"); if (ctx) xkb_context_unref(ctx); free(c); return NULL; }
 xkb_keymap_unref(map); xkb_context_unref(ctx);
 return c;
}
