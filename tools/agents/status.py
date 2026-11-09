"""Стан команди агентів: відставання від main, чужі гілки й заявки на задачі.

Запуск з кореня репозиторію:
    python tools/agents/status.py            # огляд
    python tools/agents/status.py --check B3 # чи вільна задача B3 (код виходу 1, якщо зайнята)

Що перевіряє:
    - наскільки поточна гілка відстає від origin/main (і чи потрібно підтягнути main);
    - заявки «Зараз:» на дошці docs/BOARD.md у гілці coordination (головне джерело), у main
      і в усіх активних гілках;
    - гілки інших агентів (<ім'я>/<ID>-...) і ID задач у їхніх назвах;
    - на скільки комітів coordination випереджає main (документи, які ще не злиті).
Лише читає: нічого не змінює, крім `git fetch --prune`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

COORD = "coordination"
AGENTS = ["perun", "veles", "yarylo", "svarog", "stryboh", "chornobog"]
TASK_ID = re.compile(r"\b([BMFGIDP]\d{1,2})\b")
BRANCH_TASK = re.compile(r"^(?P<agent>[a-z]+)/(?P<task>[A-Z]\d{1,2})(?:-|$)")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout.strip()


def board_claims(ref: str) -> dict[str, list[str]]:
    """{ім'я агента: [ID задач]} з розділу «Зараз у роботі» дошки в гілці ref."""
    text = git("show", f"{ref}:docs/BOARD.md")
    if not text or "## Зараз у роботі" not in text:
        return {}
    section = text.split("## Зараз у роботі", 1)[1].split("## Журнал", 1)[0]
    claims: dict[str, list[str]] = {}
    current = None
    for line in section.splitlines():
        if line.startswith("### "):
            current = line[4:].strip()
        elif current and line.strip().startswith("- **Зараз:**"):
            ids = TASK_ID.findall(line)
            if ids:
                claims[current] = ids
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", metavar="ID", help="перевірити, чи вільна задача")
    args = parser.parse_args()

    git("fetch", "--prune", "--quiet", "origin")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    behind = git("rev-list", "--count", "HEAD..origin/main") or "?"
    print(f"Поточна гілка: {branch}; відстає від origin/main на {behind} коміт(ів)")
    if behind not in ("0", "?"):
        print("  → підтягніть main: git fetch origin && git rebase origin/main  (або git merge origin/main)")

    remote = [b.strip().removeprefix("origin/") for b in git("branch", "-r", "--format=%(refname:short)").splitlines()]
    remote = [b for b in remote if b and b not in ("HEAD", "origin")]

    taken: dict[str, list[str]] = {}

    def add(task: str, where: str) -> None:
        taken.setdefault(task, []).append(where)

    if COORD in remote:
        ahead = git("rev-list", "--count", f"origin/main..origin/{COORD}")
        print(f"Гілка {COORD}: документів, ще не злитих у main, — {ahead} коміт(ів)")
        print(f"  актуальні документи: git show origin/{COORD}:docs/TASKS.md")
    else:
        print(f"⚠️  Гілки {COORD} немає на origin — дошка читається лише з main і гілок")

    for ref, label in ((f"origin/{COORD}", COORD), ("origin/main", "main")):
        claims = board_claims(ref)
        print(f"\nЗаявки на дошці в {label}:" + ("" if claims else " —"))
        for agent, ids in claims.items():
            print(f"  {agent}: {', '.join(ids)}")
            for task in ids:
                add(task, f"дошка {label} ({agent})")

    print("\nАктивні гілки (не злиті в main):")
    for b in sorted(remote):
        if b in ("main", COORD):
            continue
        merged = subprocess.run(["git", "merge-base", "--is-ancestor", f"origin/{b}", "origin/main"],
                                check=False).returncode == 0
        if merged:
            continue
        m = BRANCH_TASK.match(b)
        task = m["task"] if m and m["agent"] in AGENTS else None
        last = git("log", "-1", "--format=%cr, %an", f"origin/{b}")
        print(f"  {b}" + (f"  [{task}]" if task else "") + f" — останній коміт {last}")
        if task:
            add(task, f"гілка {b}")
        # Дошку читаємо в усіх активних гілках: гілка сесії Перуна може не мати префікса perun/.
        for agent, ids in board_claims(f"origin/{b}").items():
            for t in ids:
                add(t, f"дошка в {b} ({agent})")

    if args.check:
        task = args.check.upper()
        where = sorted(set(taken.get(task, [])))
        own = [w for w in where if branch in w]
        others = [w for w in where if w not in own]
        if others:
            print(f"\n✋ Задача {task} уже зайнята: {'; '.join(others)}")
            return 1
        print(f"\n✅ Задача {task} вільна" + (" (заявка ваша)" if own else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
