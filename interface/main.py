"""Ponto de entrada da GUI Linux GTK."""

from .gui import ChatWindow, require_gtk


def main() -> None:
    require_gtk()
    from gi.repository import Gtk

    window = ChatWindow()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
