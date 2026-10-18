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


def find_main(baseline, pattern, nocap=False):
    cap = lambda h: nocap or U.GetWindowLongW(h, -16) & 0xC00000 == 0xC00000  # есть заголовок: заставки не подходят
    c = [h for h in windows() if h not in baseline and title(h) and cap(h) and area(h) > 400 * 300
         and (not pattern or re.search(pattern, title(h)))]
    return max(c, key=area) if c else None


def place(h, final=False):
    """Окно на весь экран, либо (demo.win=[w,h]) окно заданного размера по центру экрана."""
    if demo.get('win') and final:  # размер окна только после setup (диалоги первого запуска нужны большими)
        ww, wh = demo['win']
        U.ShowWindow(h, 9); time.sleep(0.5)
        U.SetWindowPos(h, 0, (1920 - ww) // 2, (1080 - wh) // 2, ww, wh, 4)
    else:
        U.SetWindowPos(h, 0, 0, 0, 1920, 1080, 4)  # на весь экран, поверх скрытой панели задач


def hide_others(keep):
    for h in windows():
        cls = ctypes.create_unicode_buffer(64)
        U.GetClassNameW(h, cls, 64)
        if h != keep and cls.value not in ('Progman', 'WorkerW') and not cls.value.startswith('Shell_'):
            U.ShowWindowAsync(h, 6)  # SW_MINIMIZE


def hide_taskbar():
    full = W.RECT(0, 0, 1920, 1080)
    ok = U.SystemParametersInfoW(0x2F, 0, ctypes.byref(full), 3)  # рабочая область = весь экран
    chk = W.RECT(); U.SystemParametersInfoW(0x30, 0, ctypes.byref(chk), 0)
    log(f'workarea set={ok} now={chk.left},{chk.top},{chk.right},{chk.bottom}')
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


VK = {'win': 0x5B, 'ctrl': 0x11, 'alt': 0x12, 'shift': 0x10, '`': 0xC0, 'space': 0x20, 'enter': 0x0D, 'tab': 0x09,
      'esc': 0x1B, 'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28, 'delete': 0x2E, 'home': 0x24, 'end': 0x23,
      '.': 0xBE, 'pgup': 0x21, 'pgdn': 0x22, 'backspace': 0x08}
for _i in range(1, 13): VK[f'f{_i}'] = 0x6F + _i


def vk_of(k):
    if k in VK: return VK[k]
    return ord(k.upper()) if len(k) == 1 else None


def send_vk(mods, key):
    seq = [VK[m] for m in mods] + [vk_of(key)]
    for v in seq: U.keybd_event(v, 0, 0, 0); time.sleep(0.05)
    time.sleep(0.1)
    for v in reversed(seq): U.keybd_event(v, 0, 2, 0); time.sleep(0.05)


def send_keys(spec):
    *mods, key = spec.lower().split('+')
    if 'win' in mods or key in ('`', 'space'):
        return send_vk(mods, key)
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


def uia_dump(h, name, _=True):  # отладка: имена и рамки элементов UIA активного окна и главного окна
    lines = []
    for hw in dict.fromkeys([U.GetForegroundWindow(), h]):
        if not hw: continue
        lines.append(f'== window {title(hw)!r} {rect(hw)}')
        try:
            for c in Desktop(backend='uia').window(handle=hw).descendants():
                try:
                    n = c.window_text().strip(); r = c.rectangle()
                    if n and r.width() > 0: lines.append(f'{c.element_info.control_type}\t{n[:60]}\t{r.left},{r.top},{r.right},{r.bottom}')
                except Exception: pass
        except Exception as e:
            lines.append(f'err {e!r}')
    open(f'{OUT}/{name}.txt', 'w', encoding='utf-8').write('\n'.join(lines))
    log(f'uia_dump {name}: {len(lines)} строк')


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
    elif d == 'scroll':  # колесо мыши: clicks<0 вниз; курсор в точке x,y окна (по умолчанию центр)
        move(*rel(h, s.get('x', 960), s.get('y', 500)), 300)
        for _ in range(abs(s['clicks'])):
            U.mouse_event(0x800, 0, 0, -120 if s['clicks'] < 0 else 120, 0); time.sleep(0.08)
    elif d == 'rclick':
        x, y = rel(h, s['x'], s['y']); move(x, y); time.sleep(0.15)
        U.mouse_event(8, 0, 0, 0, 0); time.sleep(0.08); U.mouse_event(16, 0, 0, 0, 0); time.sleep(0.3)
    elif d == 'dblclick':
        x, y = rel(h, s['x'], s['y']); move(x, y); time.sleep(0.15)
        for _ in range(2): btn(1); time.sleep(0.05); btn(0); time.sleep(0.08)
        time.sleep(0.3)
    elif d == 'move': move(*rel(h, s['x'], s['y']), s.get('ms', 500))
    elif d == 'uia_dump': uia_dump(h, s.get('name', 'uia'), s.get('depth_all', True))
    elif d == 'keys': keyboard.send_keys(s['keys'], with_spaces=True, pause=0.05)  # сырой синтаксис pywinauto: {TAB}, {ENTER}, ^a
    elif d == 'restore':  # вернуть свёрнутое окно (например модальный диалог, свёрнутый hide_others)
        for hw in windows():
            if re.search(s['title'], title(hw)):
                U.ShowWindow(hw, 9); U.SetForegroundWindow(hw); log(f'restore {title(hw)!r}'); time.sleep(0.5)
    elif d == 'fit':  # окно по заголовку на весь экран и на передний план
        for hw in windows():
            if re.search(s['title'], title(hw)):
                U.ShowWindow(hw, 9); U.SetWindowPos(hw, 0, 0, 0, 1920, 1032, 4); U.SetForegroundWindow(hw)
                log(f'fit {title(hw)!r} {rect(hw)}'); time.sleep(0.8)
    elif d == 'winlist':
        for hw in windows():
            r = rect(hw)
            if title(hw) or (r[2] - r[0]) > 200:
                ck = ctypes.c_int(0); ctypes.windll.dwmapi.DwmGetWindowAttribute(hw, 14, ctypes.byref(ck), 4)
                log(f'win {title(hw)!r} {r} iconic={bool(U.IsIconic(hw))} cloaked={ck.value} exstyle={U.GetWindowLongW(hw, -20):#x} fg={U.GetForegroundWindow() == hw}')
    elif d == 'launch':
        t = resolve(s['target']); log(f'launch {t}')
        if s.get('args'): os.startfile(t, arguments=s['args'])
        else: os.startfile(t)
    elif d == 'setenv': os.environ[s['name']] = s['value']  # для программ, запущенных дальше (например QT_SCALE_FACTOR)
    elif d == 'kill': subprocess.run(['taskkill', '/F', '/T', '/IM', s['image']], capture_output=True)
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
def resolve(name):
    name = os.path.expandvars(name)
    if not re.search(r'[\\/]|\.exe$', name):
        lnks = glob.glob(os.path.expandvars(r'%ProgramData%\Microsoft\Windows\Start Menu\**\*.lnk'), recursive=True) + \
               glob.glob(os.path.expandvars(r'%APPDATA%\Microsoft\Windows\Start Menu\**\*.lnk'), recursive=True)
        name = next((l for l in lnks if name.lower() in os.path.basename(l).lower()), name)
    return name


launch = resolve(demo['launch'])
if demo.get('args') and launch.lower().endswith('.lnk'):  # ярлык -> exe, чтобы передать аргументы (например файл)
    tgt = subprocess.run(['powershell', '-NoProfile', '-c', f"(New-Object -ComObject WScript.Shell).CreateShortcut('{launch}').TargetPath"],
                         capture_output=True, text=True).stdout.strip()
    log(f'ярлык -> {tgt}')
    launch = tgt or launch
log(f'запуск {launch} {demo.get("args", "")}')
if demo.get('args'): os.startfile(launch, arguments=os.path.expandvars(demo['args']))
else: os.startfile(launch)

h = None; deadline = time.time() + 240
while time.time() < deadline:
    time.sleep(1.5)
    h = find_main(baseline, demo.get('title'), bool(demo.get('dialog_first')))
    if h:
        if demo.get('dialog_first'):  # первое окно - диалог/приветствие: не разворачиваем, setup работает в нём
            U.SetForegroundWindow(h); time.sleep(1); break
        U.ShowWindowAsync(h, 3); U.SetForegroundWindow(h); time.sleep(1)
        if U.IsZoomed(h):
            break
log(f'окно: {title(h) if h else None} {rect(h) if h else None}')
if h and not demo.get('dialog_first'):
    hide_others(h); U.ShowWindowAsync(h, 3); U.SetForegroundWindow(h); time.sleep(1)
    place(h)
    log(f'окно после SetWindowPos {rect(h)} zoomed={U.IsZoomed(h)}')
time.sleep(demo.get('settle', 3))
if demo.get('setup'):  # подготовка до записи: закрыть приветствия, сменить язык и т.п.
    for i, st in enumerate(demo['setup'], 1):
        try: run_step(h, st, [])
        except Exception as e: log(f'setup {i} {st} упал: {e!r}')
        log(f'setup {i} {st["do"]}')
    ImageGrab.grab(all_screens=True).save(f'{OUT}/setup_end.png')
    if demo.get('refind', True):  # окно могло пересоздаться (перезапуск программы)
        time.sleep(1)
        h2 = find_main(set(), demo.get('title'))
        if h2:
            h = h2; hide_others(h); U.ShowWindowAsync(h, 3); U.SetForegroundWindow(h); time.sleep(1)
            place(h, True); time.sleep(1)
            log(f'окно после setup: {title(h)} {rect(h)}')

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

for pat in demo.get('dump', []):  # отладка: вывести в лог файлы настроек программы
    for f in glob.glob(os.path.expandvars(pat), recursive=True):
        if f.endswith('.json') and os.path.getsize(f) < 20000:  # только короткие значения: в файлах бывают ключи
            d = json.load(open(f, encoding='utf-8'))
            def flat(x, pre=''):  # только короткие скаляры, вложенные ключи через точку
                for k, v in x.items():
                    if isinstance(v, dict): yield from flat(v, pre + k + '.')
                    elif not isinstance(v, (list, dict)) and len(str(v)) < 30: yield pre + k, v
            log(f'dump {f}: ' + json.dumps(dict(flat(d)), ensure_ascii=False))
        else:
            log(f'dump {f}')
ff.stdin.write(b'q'); ff.stdin.flush()
try: ff.wait(30)
except Exception: ff.kill()
json.dump({'recording_started': started, 'duration': now(), 'screen': [1920, 1080], 'window_title': title(h) if h else None,
           'steps': steps_out, 'marks': marks}, open(f'{OUT}/timeline.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
log(f'готово, ffmpeg exit {ff.returncode}')
