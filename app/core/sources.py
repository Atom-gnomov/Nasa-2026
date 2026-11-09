"""Контракти джерел даних (docs/CONTRACTS.md, розділ 4).

Зовнішні дані (DEM, карти освітленості, експорти Horizons, списки місць) стануть відомі
пізніше. Щоб їх підключення не зачіпало математику й API, кожне джерело реалізує один
із протоколів нижче. Математичне ядро й сервіси залежать лише від цих протоколів.

Як підключити новий набір даних:
    1. Покласти файли в data_cache/<dataset_id>/ разом із manifest.json
       (схема contracts/schemas/dataset_manifest.schema.json).
    2. Написати адаптер у app/adapters/<dataset_id>.py, що реалізує потрібний протокол.
    3. Додати контрактний тест: адаптер повертає значення в правильних одиницях і системі координат.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

import numpy as np

from app.core.horizon import HorizonMask


@runtime_checkable
class HeightSource(Protocol):
    """Рельєф Місяця.

    Контракт:
        - вхід: селенографічні lat/lon у градусах (MOON_ME), масиви будь-якої однакової форми;
        - вихід: висота в МЕТРАХ відносно сфери R = 1737,4 км, та сама форма;
        - поза покриттям — NaN (споживач вирішує, що робити).
    Сумісний з app.core.horizon.compute_mask (аргумент height_fn).
    """

    id: str
    resolution_m: float

    def __call__(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray: ...

    def covers(self, lat: float, lon: float) -> bool: ...


@runtime_checkable
class MaskStore(Protocol):
    """Сховище передрахованих масок горизонту (contracts/schemas/horizon_mask.schema.json).

    get() повертає None, якщо маски немає — тоді сервіс бере гладку сферу або рахує на льоту.
    Азимути маски — від півночі за годинниковою стрілкою; на полюсі — grid north (меридіан lon).
    """

    def get(self, lat: float, lon: float, observer_height_m: float) -> HorizonMask | None: ...

    def put(self, lat: float, lon: float, observer_height_m: float, mask: HorizonMask, source: str) -> None: ...


@runtime_checkable
class IlluminationSource(Protocol):
    """Готові карти освітленості (напр., PGDA Mazarico et al., 2011) — друга черга.

    Контракт: частка часу 0..1, коли Сонце над горизонтом, для точки; NaN поза покриттям.
    Використовується для швидкого фільтра «години Сонця» і для валідації наших розрахунків.
    """

    id: str

    def sun_fraction(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray: ...


@runtime_checkable
class CatalogSource(Protocol):
    """Каталог об'єктів (місця посадки, станції, космодроми).

    Контракт: записи — словники за схемами contracts/schemas/*.schema.json.
    """

    id: str

    def records(self) -> Iterable[dict]: ...
