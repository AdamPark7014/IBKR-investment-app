# Agentes en IBKR-INVESTMENT-app

## Git: SOLO `main` (regla dura, va antes que todo lo demás)

Adam es el único programador. Este repo tiene **una sola rama: `main`**, para Claude, Cursor (editor, CLI y
Cloud/Background Agents), Grok y cualquier otro agente.

- Flujo: `git pull --rebase origin main` → cambios pequeños → **verificaciones en verde** (`ruff check . && mypy src && pytest -q`) → commit con la
  línea `Agente: <quién>` → `git pull --rebase origin main` → `git push origin main`.
- **Nunca**: ramas (`git branch X`, `git checkout -b`, `git switch -c`), worktrees, PRs (`gh pr create` o el PR
  automático de los Cloud Agents), push a otra rama ni `--force`.
- **Cloud/Background Agents de Cursor:** si la plataforma te pone en una rama `cursor/…`, no abras PR. Al terminar:
  `git fetch origin main && git rebase origin/main`, verificaciones, `git push origin HEAD:main` y borra tu rama remota.
  Si no puedes llegar a `main`, detente y deja un resumen; no dejes la rama ni el PR vivos.
- Si aparece otra rama: si sirve y pasa las verificaciones, fusiónala a `main` y bórrala (local y remota) en el mismo turno.
- Cambios visuales notables: mockup y visto bueno de Adam primero. Un cambio de texto no cambia lógica ni esconde
  errores del servidor. Nada de datos personales ni secretos en el repo.
- Deploy solo desde `main`, con verificaciones en verde. Única excepción: Adam pide una rama por su nombre.

Regla completa: `.cursor/rules/git-solo-main.mdc` y `C:\dev\scripts\ai-os\GIT-SOLO-MAIN.md`.
