Записывает короткие демо десктопных программ на windows-latest (GitHub Actions).

Как добавить сценарий:
1. Создай `demos/<slug>.json` (slug: `^[a-z0-9-]+$`): `winget_id`, `launch` (путь к exe или имя ярлыка из меню Пуск), `title` (необязательно, regexp заголовка окна), `settle` (пауза после запуска, с), `pre` (необязательно, команды PowerShell до запуска, например конфиг с русским языком), `inputs` (файлы из `demos/inputs/`, копируются в `C:\demo\`), `steps`.
2. Шаги: `wait {s}`, `hotkey {keys:"ctrl+n"}`, `type {text}`, `click {x,y}` (от левого верхнего угла окна), `click_text {text}` (UI Automation; Qt и диалоги находит, Electron и Flutter нет), `drag {path:[[x,y],...], ms}`, `scroll {clicks, x, y}`, `mark {name}`.
3. Запусти workflow `record` с входом `demo=<slug>` и скачай артефакт `out`.
4. В артефакте: `demo.mp4` (1920x1080, 30 fps), `timeline.json` (время шагов и прямоугольник окна в пикселях экрана), `step_NN.png`, `log.txt`.

Запись стартует после появления и разворачивания окна программы. Окно занимает рабочую область (1920x1032, нижние 48 px экрана пустые), прямоугольник окна всегда есть в `timeline.json`.
