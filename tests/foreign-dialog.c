#include <gtk/gtk.h>
#include <gdk/gdkwayland.h>
#include <stdio.h>
#include <string.h>
static const char *path;
static void exported(GdkWindow *window, const char *handle, gpointer data) {
 FILE *out=fopen(path,"w"); if (!out) return;
 fprintf(out,"%s",handle); fclose(out);
}
int main(int argc,char **argv) {
 gtk_init(&argc,&argv);
 if (argc!=3) return 2;
 path=argv[2];
 GtkWidget *window=gtk_window_new(GTK_WINDOW_TOPLEVEL);
 gtk_window_set_title(GTK_WINDOW(window),!strcmp(argv[1],"parent")?"Portal Parent":"Portal Dialog");
 gtk_window_set_default_size(GTK_WINDOW(window),400,260);
 g_signal_connect(window,"destroy",G_CALLBACK(gtk_main_quit),NULL);
 gtk_widget_realize(window);
 gtk_widget_show_all(window);
 GdkWindow *native=gtk_widget_get_window(window);
 if (!strcmp(argv[1],"parent")) {
  if (!gdk_wayland_window_export_handle(native,exported,NULL,NULL)) return 3;
 } else {
  char handle[128]={0}; FILE *in=fopen(path,"r"); if(!in)return 4;
  fgets(handle,sizeof(handle),in); fclose(in);
  if (!gdk_wayland_window_set_transient_for_exported(native,handle))return 5;
 }
 gtk_widget_show_all(window);
 gtk_main();
 return 0;
}
