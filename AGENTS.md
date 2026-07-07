# Disgust Docs CLI

## Scope

- V1 intentionally без generated index, без автоматического патча `AGENTS.md` в проектах-потребителях и без отдельного agent skill.
- Direct push в `main`, обход `mode: readOnly` и запись вне `.disgust-docs/` не поддерживаются.

## Архитектура

- CLI реализован как Python-пакет `disgust_docs_cli` с entrypoint `disgust-docs`.
- Переносимый проектный контракт хранится в `.disgust-docs.yml`.
- Локальные checkout/worktree проекта лежат в `.disgust-docs/` и должны быть ignored.
- Глобальный bare mirror docs repo живет в `~/.disgust-docs/mirrors/`.
- Read worktree создается detached от base branch commit.
- Edit session создается только через `disgust-docs edit <alias> --branch <name>` и только для `mode: pr`.
- Publish flow: commit docs changes, push branch, create GitHub PR через `gh`, затем вернуть docs path в read worktree.
- Direct push в base branch не поддерживать.

## Команды

- `disgust-docs init`: создать `.disgust-docs.yml`, добавить `.disgust-docs/` в `.gitignore`.
- `disgust-docs add <alias> <repo-url> --branch main --mode readOnly|pr`: зарегистрировать docs repo и выполнить sync.
- `disgust-docs sync [alias]`: обновить read worktree, если нет active edit session.
- `disgust-docs status [alias]`: показать mode, session state, branch, commit, dirty state и path.
- `disgust-docs edit <alias> --branch <name>`: начать editable branch worktree.
- `disgust-docs publish <alias> --message ... --title ... --body ...`: создать commit, push и GitHub PR.
- `disgust-docs abort <alias>`: закрыть clean edit session без публикации.
- `disgust-docs remove <alias>`: убрать регистрацию и локальный worktree.

## Разработка

- Изменения держи узкими: CLI contract, config schema, git workflow и тесты должны оставаться синхронизированы.
- Для ручных правок используй `apply_patch`.
- Не добавляй runtime-зависимости без причины; текущий v1 работает на стандартной библиотеке Python и опционально использует PyYAML, если он уже установлен.
- Не удаляй и не меняй пользовательские незакоммиченные изменения без явной просьбы.

## Проверки

Перед финалом запускай:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m disgust_docs_cli --help
python3 -m py_compile src/disgust_docs_cli/*.py
```

Для publish-related изменений тестируй через fake `gh`, а не через реальный GitHub.
