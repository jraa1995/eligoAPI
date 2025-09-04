NAICS_2022_TITLES = {
    "541511": "Custom Computer Programming Services",
    "541512": "Computer Systems Design Services",
    "236220": "Commercial and Institutional Building Construction",
    "336611": "Ship Building and Repairing",
}

def valid_naics(code: str) -> bool:
    return len(code) == 6 and code.isdigit()

def title_for(code: str) -> str:
    return NAICS_2022_TITLES.get(code, "Unknown NAICS")
