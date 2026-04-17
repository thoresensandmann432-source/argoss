"""
kivy_1gui.py — ARGOS v1.33 Kivy Mobile GUI (опционально)
Требует: pip install kivy
"""
try:
    from kivy.app import App
    from kivy.uix.floatlayout import FloatLayout
    from kivy.lang import Builder
    from kivy.clock import Clock
    from kivy.graphics import Color, Rectangle, Line
    from kivy.core.window import Window
    from kivy.properties import StringProperty
    _KIVY_AVAILABLE = True
except ImportError:
    _KIVY_AVAILABLE = False

if _KIVY_AVAILABLE:
    Builder.load_string("""
<ArgosRoot>:
    canvas.before:
        Color:
            rgba: 0, 0.02, 0.04, 1
        Rectangle:
            pos: self.pos
            size: self.size
""")

    class ArgosRoot(FloatLayout):
        status_text = StringProperty("ARGOS READY")

        def __init__(self, core=None, **kw):
            super().__init__(**kw)
            self.core = core

    class ArgosApp(App):
        def __init__(self, core=None, **kw):
            super().__init__(**kw)
            self.core = core

        def build(self):
            Window.clearcolor = (0, 0.02, 0.04, 1)
            return ArgosRoot(core=self.core)

    def launch(core=None):
        ArgosApp(core=core).run()

else:
    class ArgosApp:
        def __init__(self, *a, **kw): pass
        def run(self): print("kivy не установлен — мобильный GUI недоступен")

    def launch(core=None):
        print("kivy не установлен — установи: pip install kivy")
