"""Centered JARVIS HUD overlay.

Runs as its own process so its animation keeps moving while JARVIS blocks on the
microphone or on speech. The assistant name to draw is the first command-line argument
(default JARVIS). It reads one command per line from stdin:

    show <STATUS TEXT>   show the HUD with that status, e.g. "show LISTENING"
    caption <text>       show what was heard or is being said, under the orb
    hide                 fade the HUD out
    quit                 exit

It exits by itself when stdin closes, so it never outlives JARVIS.
"""
import queue
import sys
import threading
import time
import tkinter as tk

from hud_orb import OrbRenderer

SIZE = 440
FRAME_MS = 33  # 30 frames a second: smooth, and leaves the CPU to speech recognition and the voice


class Hud:
    def __init__(self, title: str) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.x = (self.root.winfo_screenwidth() - SIZE) // 2
        self.y = (self.root.winfo_screenheight() - SIZE) // 2
        self.root.geometry(f'{SIZE}x{SIZE}+{self.x}+{self.y}')
        # Hidden before it becomes a layered window: Windows rejects UpdateLayeredWindow
        # (error 87) on a window that was already shown and painted normally.
        self.root.withdraw()

        self.renderer = OrbRenderer(SIZE, title)
        self.layered = None
        if sys.platform == 'win32':
            from hud_orb import LayeredWindow
            self.layered = LayeredWindow(self.root, SIZE, self.x, self.y)
            self.root.configure(bg='black')
        else:
            # macOS draws the RGBA frames on a transparent window background.
            self.root.attributes('-transparent', True)
            self.root.configure(bg='systemTransparent')
            self.canvas = tk.Canvas(self.root, width=SIZE, height=SIZE, bg='systemTransparent',
                                    highlightthickness=0)
            self.canvas.pack()

        self.mapped = False
        self.last = time.perf_counter()
        self.commands: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read_stdin, daemon=True).start()
        self.root.after(FRAME_MS, self._frame)

    def _read_stdin(self) -> None:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')  # helpers.hud() sends UTF-8
        for line in sys.stdin:
            self.commands.put(line.strip())
        self.commands.put('quit')

    def _handle(self, command: str) -> None:
        if command.startswith('show'):
            self.renderer.set_status(command[4:].strip().upper())
            if not self.mapped:
                self.root.deiconify()
                self.root.attributes('-topmost', True)
                if self.layered:
                    self.layered.apply_style()
                self.mapped = True
        elif command.startswith('caption'):
            self.renderer.set_caption(command[7:].strip())
        elif command == 'hide':
            self.renderer.hide()  # fades out; the window is withdrawn once invisible
        elif command == 'quit':
            self.root.destroy()

    def _frame(self) -> None:
        try:
            while not self.commands.empty():
                self._handle(self.commands.get())
            now = time.perf_counter()
            dt, self.last = now - self.last, now
            if self.mapped:
                frame = self.renderer.frame(dt)
                if self.layered:
                    self.layered.present(frame)
                else:
                    from PIL import ImageTk
                    self._photo = ImageTk.PhotoImage(frame)
                    self.canvas.delete('all')
                    self.canvas.create_image(0, 0, image=self._photo, anchor='nw')
                if self.renderer.fully_hidden:
                    self.root.withdraw()
                    self.mapped = False
        except tk.TclError:
            return  # window was destroyed by "quit"
        except Exception:
            import traceback
            traceback.print_exc()  # one bad frame shouldn't freeze the orb on screen for good
        try:
            self.root.after(FRAME_MS, self._frame)
        except tk.TclError:
            pass  # window was destroyed by "quit"

    def run(self) -> None:
        self.root.mainloop()


if __name__ == '__main__':
    Hud(sys.argv[1] if len(sys.argv) > 1 else 'JARVIS').run()
