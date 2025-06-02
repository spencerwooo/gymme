# Preferences defined as:
# -> 0: ignore, 1: ok to book, 5: very much preferred, 10: must book
field_pref_scores = {
    "220": 1,  # 主馆1
    "221": 5,  # 主馆2
    "222": 7,  # 主馆3
    "223": 2,  # 主馆4
    "224": 3,  # 主馆5
    "225": 8,  # 主馆6
    "226": 6,  # 主馆7
    "227": 4,  # 主馆8
    "228": 1,  # 副馆9
    "229": 2,  # 副馆10
    "230": 3,  # 副馆11
    "231": 4,  # 副馆12
}
hour_pref_scores = {
    "328228": 0,  # 8:00-9:00
    "328229": 0,  # 9:00-10:00
    "328230": 2,  # 10:00-11:00
    "328231": 3,  # 11:00-12:00
    "328232": 5,  # 12:00-13:00
    "328233": 7,  # 13:00-14:00
    "328234": 9,  # 14:00-15:00
    "328235": 10,  # 15:00-16:00
    "328236": 10,  # 16:00-17:00
    "328237": 0,  # 17:00-18:00
    "328238": 0,  # 18:00-19:00
    "328239": 0,  # 19:00-20:00
    "328240": 0,  # 20:00-21:00
    "328241": 0,  # 21:00-22:00
}

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
