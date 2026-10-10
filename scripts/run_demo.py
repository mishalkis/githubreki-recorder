"""Запись демо: python run_demo.py demos/<slug>.json
Запускает ffmpeg, программу, выполняет шаги, пишет out/timeline.json."""
import atexit, ctypes, glob, json, os, re, subprocess, sys, time
from ctypes import wintypes as W
from PIL import ImageGrab
from pywinauto import Desktop, keyboard

sys.stdout.reconfigure(encoding='utf-8')
ctypes.windll.user32.SetProcessDPIAware()
U = ctypes.windll.user32
OUT = 'out'
demo = json.load(open(sys.argv[1], encoding='utf-8'))
t0 = time.time()


def log(m):
    line = f'{time.strftime("%H:%M:%S")} {m}'
    print(line, flush=True)


def now():
    return round(time.time() - t0, 2)


# ---------- окна ----------
def windows():
    res = []
    cb = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)(lambda h, _: res.append(h) or True)
    U.EnumWindows(cb, 0)
    return [h for h in res if U.IsWindowVisible(h)]


def title(h):
    b = ctypes.create_unicode_buffer(256)
    U.GetWindowTextW(h, b, 256)
    return b.value


def rect(h):
    r = W.RECT()  # видимая рамка без невидимых теней
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(r), 16) != 0:
        U.GetWindowRect(h, ctypes.byref(r))
    return [r.left, r.top, r.right, r.bottom]


def area(h):
    r = rect(h)
    return (r[2] - r[0]) * (r[3] - r[1])


def find_main(baseline, pattern):
    cap = lambda h: U.GetWindowLongW(h, -16) & 0xC00000 == 0xC00000  # есть заголовок: заставки не подходят
    c = [h for h in windows() if h not in baseline and title(h) and cap(h) and area(h) > 400 * 300
         and (not pattern or re.search(pattern, title(h)))]
    return max(c, key=area) if c else None


def hide_others(keep):
    for h in windows():
        cls = ctypes.create_unicode_buffer(64)
        U.GetClassNameW(h, cls, 64)
        if h != keep and cls.value not in ('Progman', 'WorkerW') and not cls.value.startswith('Shell_'):
            U.ShowWindowAsync(h, 6)  # SW_MINIMIZE


def hide_taskbar():
    full = W.RECT(0, 0, 1920, 1080)
    U.SystemParametersInfoW(0x2F, 0, ctypes.byref(full), 2)  # рабочая область = весь экран
    for cls in ('Shell_TrayWnd', 'Shell_SecondaryTrayWnd'):
        h = U.FindWindowW(cls, None)
        if h:
            U.ShowWindow(h, 0)


# ---------- мышь и клавиатура ----------
def pos():
    p = W.POINT(); U.GetCursorPos(ctypes.byref(p)); return p.x, p.y


def move(x, y, ms=500):
    x0, y0 = pos(); n = max(2, ms // 15)
    for i in range(1, n + 1):
        k = i / n; k = k * k * (3 - 2 * k)  # плавный разгон и торможение
        U.SetCursorPos(int(x0 + (x - x0) * k), int(y0 + (y - y0) * k))
        time.sleep(ms / 1000 / n)


def btn(down):
    U.mouse_event(2 if down else 4, 0, 0, 0, 0)


def click(x, y):
    move(x, y); time.sleep(0.15); btn(1); time.sleep(0.08); btn(0); time.sleep(0.3)


def send_keys(spec):
    *mods, key = spec.lower().split('+')
    pre = ''.join({'ctrl': '^', 'alt': '%', 'shift': '+'}[m] for m in mods)
    k = key if len(key) == 1 else '{' + key.upper() + '}'
    keyboard.send_keys(pre + k, pause=0.05)


def rel(h, x, y):
    r = rect(h)
    return r[0] + x, r[1] + y


# ---------- шаги ----------
def click_text(h, text):
    low = text.lower()
    best, cands = None, []
    for hw in dict.fromkeys([U.GetForegroundWindow(), h]):  # сначала активное окно (диалог)
        if not hw:
            continue
        for c in Desktop(backend='uia').window(handle=hw).descendants():
            try:
                n = c.window_text().strip().lower()
                r = c.rectangle()
                if not n or r.width() <= 0:
                    continue
                k = (n != low, r.width() * r.height())  # точное имя, затем самый маленький элемент
                if n == low or low in n:
                    cands.append((k, r))
            except Exception:
                pass
        if cands:
            best = min(cands, key=lambda c: c[0])[1]
            break
    if not best:
        log(f'click_text: "{text}" не найден'); return
    x, y = (best.left + best.right) // 2, (best.top + best.bottom) // 2
    log(f'click_text "{text}" -> {x},{y}'); click(x, y)


def run_step(h, s, marks):
    d = s['do']
    if d == 'wait': time.sleep(s['s'])
    elif d == 'hotkey': send_keys(s['keys'])
    elif d == 'type': keyboard.send_keys(re.sub(r'([{}()+^%~])', r'{\1}', s['text']), with_spaces=True, pause=0.04)
    elif d == 'click': click(*rel(h, s['x'], s['y']))
    elif d == 'click_text': click_text(h, s['text'])
    elif d == 'drag':
        pts = [rel(h, *p) for p in s['path']]
        move(*pts[0], 400); btn(1); time.sleep(0.1)
        seg = max(30, s.get('ms', 800) // max(1, len(pts) - 1))
        for p in pts[1:]: move(*p, seg)
        btn(0)
    elif d == 'mark': marks.append({'name': s['name'], 't': now()})
    else: log(f'неизвестный шаг {d}')


# ---------- основной ход ----------
os.makedirs(OUT, exist_ok=True)
import faulthandler
faulthandler.dump_traceback_later(100, repeat=True, file=open(f'{OUT}/trace.txt', 'w'))
hide_taskbar()
subprocess.run(['powershell', '-NoProfile', '-c', '(New-Object -ComObject Shell.Application).MinimizeAll()'])
hide_others(0)
baseline = set(windows())

# запуск
launch = os.path.expandvars(demo['launch'])
if not re.search(r'[\\/]|\.exe$', launch):
    lnks = glob.glob(os.path.expandvars(r'%ProgramData%\Microsoft\Windows\Start Menu\**\*.lnk'), recursive=True) + \
           glob.glob(os.path.expandvars(r'%APPDATA%\Microsoft\Windows\Start Menu\**\*.lnk'), recursive=True)
    launch = next((l for l in lnks if launch.lower() in os.path.basename(l).lower()), launch)
log(f'запуск {launch}')
os.startfile(launch)

h = None; deadline = time.time() + 240
while time.time() < deadline:
    time.sleep(1.5)
    h = find_main(baseline, demo.get('title'))
    if h:
        U.ShowWindowAsync(h, 3); U.SetForegroundWindow(h); time.sleep(1)
        if U.IsZoomed(h):
            break
log(f'окно: {title(h) if h else None} {rect(h) if h else None}')
if h:
    hide_others(h); U.ShowWindowAsync(h, 3); U.SetForegroundWindow(h); time.sleep(1)
    U.SetWindowPos(h, 0, 0, 0, 1920, 1080, 4)  # на весь экран, поверх скрытой панели задач
    log(f'окно после SetWindowPos {rect(h)} zoomed={U.IsZoomed(h)}')
time.sleep(demo.get('settle', 3))

ff = subprocess.Popen(['ffmpeg', '-y', '-f', 'gdigrab', '-framerate', '30', '-draw_mouse', '1', '-i', 'desktop',
                       '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', f'{OUT}/demo.mp4'],
                      stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=open(f'{OUT}/ffmpeg.log', 'w'))
atexit.register(lambda: ff.poll() is None and ff.kill())
while not (os.path.exists(f'{OUT}/demo.mp4') and os.path.getsize(f'{OUT}/demo.mp4') > 0):
    time.sleep(0.05)
t0 = time.time(); started = time.strftime('%Y-%m-%dT%H:%M:%S%z')
log('запись пошла')
move(960, 540, 10)


steps_out, marks = [], []
for i, s in enumerate(demo['steps'], 1):
    ts = now()
    r0 = rect(h) if h else None
    try:
        run_step(h, s, marks)
    except Exception as e:
        log(f'шаг {i} {s} упал: {e!r}')
    ImageGrab.grab(all_screens=True).save(f'{OUT}/step_{i:02d}.png')
    steps_out.append({'n': i, 'step': s, 'start': ts, 'end': now(), 'window_start': r0,
                      'window': rect(h) if h else None, 'screenshot': f'step_{i:02d}.png'})
    log(f'шаг {i} {s["do"]} {ts}-{now()}')
time.sleep(1)

ff.stdin.write(b'q'); ff.stdin.flush()
try: ff.wait(30)
except Exception: ff.kill()
json.dump({'recording_started': started, 'duration': now(), 'screen': [1920, 1080], 'window_title': title(h) if h else None,
           'steps': steps_out, 'marks': marks}, open(f'{OUT}/timeline.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
log(f'готово, ffmpeg exit {ff.returncode}')
