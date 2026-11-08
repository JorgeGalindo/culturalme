"""
Pasada semanal de culturalme en el Mac mini (launchd, viernes 07:00).

  pipeline.run()     lee las fuentes con `claude -p` y etiqueta
  curate.curate()    la portada de la semana
  generate()         docs/
  git commit + push  Vercel publica en cada push a main

Todo con la suscripción de Claude de Jorge: ninguna API de pago. Si algo
falla, o falla más de un tercio de las fuentes, aviso en el Mac y por correo.

    python semanal.py
"""

from __future__ import annotations

import subprocess
import sys
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLAUDE = str(Path.home() / ".local/bin/claude")
AVISAR_A = "jorgegalindoalfonso@gmail.com"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def avisar(asunto: str, cuerpo: str) -> None:
    """Notificación en el Mac y correo a Jorge (lo sigue desde el móvil)."""
    subprocess.run(["/usr/bin/osascript", "-e", "on run argv", "-e",
                    "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run",
                    f"culturalme · {asunto}", cuerpo[:200]], capture_output=True)
    prompt = (f"Envía un correo con mcp__claude_ai_Gmail__send_message a {AVISAR_A}. "
              f"Asunto: «culturalme · {asunto}». Cuerpo, tal cual:\n\n{cuerpo}")
    try:
        subprocess.run([CLAUDE, "-p", "--model", "claude-haiku-5-5", "--no-session-persistence",
                        "--allowedTools", "mcp__claude_ai_Gmail__send_message"],
                       input=prompt, capture_output=True, text=True, timeout=600, cwd=ROOT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  (correo no enviado: {exc})")


def publish() -> str:
    git("add", "data/culturalme.db", "data/curation.json", "docs")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return "sin cambios"
    commit = git("commit", "-q", "-m", f"update {date.today().isoformat()}")
    if commit.returncode:
        raise RuntimeError(f"git commit falló: {commit.stderr[-300:]}")
    push = git("push", "-q", "origin", "main")
    if push.returncode:
        raise RuntimeError(f"git push falló: {push.stderr[-300:]}")
    return "publicado"


def main() -> int:
    print(f"— culturalme {date.today().isoformat()}")
    pull = git("pull", "-q", "--rebase", "--autostash", "origin", "main")
    if pull.returncode:
        print(f"  git pull falló, sigo con lo local: {pull.stderr.strip()[-200:]}")

    import curate
    import generate
    import pipeline

    try:
        summary = pipeline.run()
    except Exception as exc:
        traceback.print_exc()
        avisar("La pasada no ha podido leer nada",
               f"{type(exc).__name__}: {exc}\n\nLa web sigue con la semana anterior. "
               "Suele ser la sesión de Claude en el mini: abre `claude` allí y comprueba que entra.")
        return 1

    problemas = []
    try:
        curate.curate()
    except Exception as exc:
        traceback.print_exc()
        problemas.append(f"Portada sin actualizar (se queda la anterior): {type(exc).__name__}: {exc}")

    try:
        generate.generate()
        estado = publish()
    except Exception as exc:
        traceback.print_exc()
        avisar("No se ha podido publicar", f"{type(exc).__name__}: {exc}")
        return 1
    print(f"  {estado}")

    total = len(summary["ok"]) + len(summary["failed"])
    if len(summary["failed"]) * 3 > total:
        problemas.append(f"Fallan {len(summary['failed'])} de {total} fuentes:\n"
                         + "\n".join(f"- {n}: {e[:150]}" for n, e in summary["failed"]))
    if problemas:
        avisar("Pasada con problemas", "\n\n".join(problemas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
