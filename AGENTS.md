# Agent Docs CLI

## Scope

- V1 intentionally без generated index, без автоматического патча `AGENTS.md` в проектах-потребителях и без отдельного agent skill.
- Direct push в `main`, обход `mode: readOnly` и запись вне `.agent-docs/` не поддерживаются.

## Архитектура

- CLI реализован как Python-пакет `agent_docs_cli` с entrypoint `agent-docs`.
- Переносимый проектный контракт хранится в `.agent-docs.yml`.
- Локальные checkout/worktree проекта лежат в `.agent-docs/` и должны быть ignored.
- Глобальный bare mirror docs repo живет в `~/.agent-docs/mirrors/`.
- Read worktree создается detached от base branch commit.
- Edit session создается только через `agent-docs edit <alias> --branch <name>` и только для `mode: pr`.
- Publish flow: commit docs changes, push branch, create GitHub PR через `gh`, затем вернуть docs path в read worktree.
- Direct push в base branch не поддерживать.

## Команды

- `agent-docs init`: создать `.agent-docs.yml`, добавить `.agent-docs/` в `.gitignore`.
- `agent-docs add <alias> <repo-url> --branch main --mode readOnly|pr`: зарегистрировать docs repo и выполнить sync.
- `agent-docs sync [alias]`: обновить read worktree, если нет active edit session.
- `agent-docs status [alias]`: показать mode, session state, branch, commit, dirty state и path.
- `agent-docs edit <alias> --branch <name>`: начать editable branch worktree.
- `agent-docs publish <alias> --message ... --title ... --body ...`: создать commit, push и GitHub PR.
- `agent-docs abort <alias>`: закрыть clean edit session без публикации.
- `agent-docs remove <alias>`: убрать регистрацию и локальный worktree.

## Разработка

- Изменения держи узкими: CLI contract, config schema, git workflow и тесты должны оставаться синхронизированы.
- Для ручных правок используй `apply_patch`.
- Не добавляй runtime-зависимости без причины; текущий v1 работает на стандартной библиотеке Python и опционально использует PyYAML, если он уже установлен.
- Не удаляй и не меняй пользовательские незакоммиченные изменения без явной просьбы.

## Проверки

Перед финалом запускай:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m agent_docs_cli --help
python3 -m py_compile src/agent_docs_cli/*.py
```

Для publish-related изменений тестируй через fake `gh`, а не через реальный GitHub.
