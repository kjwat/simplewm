#!/usr/bin/python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import sys

title = sys.argv[1]
window = Gtk.Window(title=title)
window.set_default_size(640, 480)
text = Gtk.TextView()
text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
text.get_buffer().set_text('A quiet desk for prose.\nTyping, selecting, and pasting must feel ordinary.\n')
window.add(text)
if len(sys.argv) > 2:
    def record(widget, event):
        with open(sys.argv[2], 'a') as out:
            out.write(f'{event.keyval} {event.state}\n')
        return False
    window.connect('key-press-event', record)
window.connect('destroy', Gtk.main_quit)
window.show_all()
Gtk.main()
