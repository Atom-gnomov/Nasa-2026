# Nasa-2026

NASA Space Apps Challenge 2026 — інструмент для порівняння місць і дат посадки на південному полюсі Місяця
(положення Сонця й Землі над горизонтом, енергія та вікна зв'язку).

- [docs/CHALLENGE.md](docs/CHALLENGE.md) — оригінальний текст завдання (англійською)
- [docs/VISION.md](docs/VISION.md) — що хочемо бачити ми і команда (наповнюється поступово)
- [docs/MODULES.md](docs/MODULES.md) — вимоги до модулів і API
- [docs/MATH.md](docs/MATH.md) — математика розрахунків і контрольні числа
- [docs/CONTRACTS.md](docs/CONTRACTS.md) — контракти API, даних і фронтенду (`contracts/openapi.yaml`)
- [docs/RESOURCES.md](docs/RESOURCES.md) — джерела даних, бібліотеки та стек візуалізації
- [docs/TASKS.md](docs/TASKS.md) — задачі, порядок реалізації, розподіл між агентами
- [docs/PROPOSALS.md](docs/PROPOSALS.md) — пропозиції та покращення
- [AGENTS.md](AGENTS.md) — точка входу для агентів (мова роботи — українська)

## Запуск

Потрібен Python 3.11+.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
flask --app app run --debug
```

Сайт відкриється на http://127.0.0.1:5000. Тести: `python -m pytest`.

Залежності включають ефемериди JPL DE440 (пакет `naif-de440`, ~114 МБ). Свій файл ефемерид можна вказати змінною `LSE_EPHEMERIS_PATH`.

Приклад запиту метрик для точки біля південного полюса:

```bash
curl "http://127.0.0.1:5000/api/metrics?lat=-89.5&lon=0&datetime=2027-07-01T00:00&height=2"
```
