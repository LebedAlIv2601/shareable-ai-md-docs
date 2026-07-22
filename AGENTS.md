# Disgust Docs CLI

## Scope

- V1 intentionally без generated index и без автоматического патча `AGENTS.md` в проектах-потребителях.
- Agent skill поддерживается как bundled installable skill через `disgust-docs skill install`.
- Direct push в base branch и обход `mode: readOnly` не поддерживаются.
- Управляемые snapshot paths должны находиться внутри проекта, быть effectively ignored, не должны пересекаться и не могут находиться внутри `.git/` или `.disgust-docs/`.

## Архитектура

- CLI реализован как Python-пакет `disgust_docs_cli` с entrypoint `disgust-docs`.
- Переносимый проектный контракт хранится в `.disgust-docs.yml`.
- Глобальный обычный cache clone каждого docs repo живет в `~/.disgust-docs/repos/` и используется только как источник tracked Git objects/refs.
- `update` экспортирует точный `origin/<branch>` commit в ignored project-local snapshot без `.git`.
- Управляемые ignore entries должны иметь приоритет над более ранними negate-правилами в корневом `.gitignore`.
- Project-local state и manifests хранятся в `.disgust-docs/state.json`; записи state/config должны быть атомарными.
- `update` не перезаписывает unpublished snapshot changes без явного `--discard-local`.
- `publish` переносит snapshot в временный checkout, создает commit, push ветки и GitHub PR через `gh`, не меняя локальный snapshot.
- Этапы publish сохраняются, чтобы повтор команды продолжал push/PR flow после частичного сбоя.
- Direct push в base branch не поддерживать.

## Команды

- `disgust-docs setup`: создать `.disgust-docs.yml` и ignore entries для state/snapshot.
- `disgust-docs add <alias> <repo-url> --branch main --mode readOnly|pr --path docs`: зарегистрировать repo и выполнить первый update.
- `disgust-docs update [alias] [--discard-local]`: fetch cache и экспортировать Gitless snapshot.
- `disgust-docs status [alias]`: показать mode, snapshot phase, base commit, publish branch, PR и path.
- `disgust-docs diff <alias>`: показать изменения snapshot относительно последнего update.
- `disgust-docs publish <alias> --branch ... --message ... --title ... --body ...`: создать/обновить commit, branch и GitHub PR, сохранив snapshot.
- `disgust-docs remove <alias>`: убрать регистрацию и безопасный локальный snapshot.
- `disgust-docs skill install [--global]`: установить bundled agent skill локально в `.agents/skills/disgust-docs` или глобально в `${CODEX_HOME:-~/.codex}/skills/disgust-docs`.
- `init` и `sync` остаются deprecated aliases для `setup` и `update`.

## Разработка

- Изменения держи узкими: CLI contract, config schema, git workflow и тесты должны оставаться синхронизированы.
- Для ручных правок используй `apply_patch`.
- Не добавляй runtime-зависимости без причины; текущий v1 работает на стандартной библиотеке Python и опционально использует PyYAML, если он уже установлен.
- Не удаляй и не меняй пользовательские незакоммиченные изменения без явной просьбы.
- Для snapshot export используй tracked commit archive, не копируй рабочее дерево cache clone.
- Для publish-related изменений тестируй retry после сбоя `gh` и сохранение локального snapshot.

## Релиз

- PyPI publishing выполняется через `.github/workflows/publish.yml` по тегам `v*`.
- Перед релизом обнови `version` в `pyproject.toml`.
- Создай тег, совпадающий с `version` в `pyproject.toml`, после commit и push:

```bash
git tag v0.2.0
git push origin main
git push origin v0.2.0
```

## Проверки

Перед финалом запускай:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m disgust_docs_cli --help
python3 -m py_compile src/disgust_docs_cli/*.py
```

Для publish-related изменений тестируй через fake `gh`, а не через реальный GitHub.
