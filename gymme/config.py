import os
from dataclasses import dataclass

import yaml


@dataclass
class GymmeConfig:
    field_prefs: dict[str, int]
    hour_prefs: dict[str, int]
    token: str
    open_id: str
    send_key: str


def load_config(config_path: str = None) -> GymmeConfig:
    """
    Load user preferences and essential configurations from the config file.

    Preferences defined as:
    -> 0: ignore, 1: ok to book, 5: very much preferred, 10: must book

    Args:
        config_path: Path to the preference config file. Defaults to conf/pref.yaml

    Returns:
        GymmeConfig: Configuration object containing field prefs, hour prefs, auth
            token, open ID, and send key loaded from the YAML file
    """

    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "conf", "pref.yaml")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
        return GymmeConfig(
            field_prefs=cfg.get("field_prefs", {}),
            hour_prefs=cfg.get("hour_prefs", {}),
            token=cfg.get("token", ""),
            open_id=cfg.get("open_id", ""),
            send_key=cfg.get("send_key", ""),
        )


# Hard-coded configurations if request fails at peak hours.
# No changes are expected here, but can be modified for future updates.
fields_cfg = {
    "220": "主馆1",
    "221": "主馆2",
    "222": "主馆3",
    "223": "主馆4",
    "224": "主馆5",
    "225": "主馆6",
    "226": "主馆7",
    "227": "主馆8",
    "228": "副馆9",
    "229": "副馆10",
    "230": "副馆11",
    "231": "副馆12",
}
hours_cfg = {
    328228: {"begin": "08:00", "end": "09:00", "create": 1705719518, "daytype": "morning"},
    328229: {"begin": "09:00", "end": "10:00", "create": 1705719519, "daytype": "morning"},
    328230: {"begin": "10:00", "end": "11:00", "create": 1705719519, "daytype": "morning"},
    328231: {"begin": "11:00", "end": "12:00", "create": 1705719519, "daytype": "morning"},
    328232: {"begin": "12:00", "end": "13:00", "create": 1705719519, "daytype": "morning"},
    328233: {"begin": "13:00", "end": "14:00", "create": 1705719519, "daytype": "morning"},
    328234: {"begin": "14:00", "end": "15:00", "create": 1705719519, "daytype": "day"},
    328235: {"begin": "15:00", "end": "16:00", "create": 1705719519, "daytype": "day"},
    328236: {"begin": "16:00", "end": "17:00", "create": 1705719519, "daytype": "day"},
    328237: {"begin": "17:00", "end": "18:00", "create": 1705719519, "daytype": "day"},
    328238: {"begin": "18:00", "end": "19:00", "create": 1705719519, "daytype": "night"},
    328239: {"begin": "19:00", "end": "20:00", "create": 1705719519, "daytype": "night"},
    328240: {"begin": "20:00", "end": "21:00", "create": 1705719519, "daytype": "night"},
    328241: {"begin": "21:00", "end": "22:00", "create": 1705719519, "daytype": "night"},
}
prices_cfg = {
    "weekday": {
        "morning": {"daytype": "morning", "price": 10, "half_price": 0},
        "day": {"daytype": "day", "price": 20, "half_price": 0},
        "night": {"daytype": "night", "price": 50, "half_price": 0},
    },
    "weekend": {
        "morning": {"daytype": "morning", "price": 20, "half_price": 0},
        "day": {"daytype": "day", "price": 50, "half_price": 0},
        "night": {"daytype": "night", "price": 50, "half_price": 0},
    },
}
