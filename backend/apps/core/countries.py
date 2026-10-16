"""
Canonical country names (SRS 4.2 profile, 4.4 matching).

Profiles store countries in one spelling so catalogue matching never breaks on
"USA" vs "United States":

- `citizenship` and `address.country` store the world name ("United States").
- `preferences.countries` stores the catalogue's spelling, i.e. the value used in
  `university.country` ("US", "UK"); every other country is spelt the same in both.

Aliases only cover unambiguous alternative spellings. Anything that is not a known
country or alias is rejected by the API, so the UI offers a list to pick from.
"""

WORLD = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina", "Armenia",
    "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium",
    "Belize", "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
    "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Chad",
    "Chile", "China", "Colombia", "Comoros", "Congo", "Costa Rica", "Côte d'Ivoire", "Croatia", "Cuba", "Cyprus",
    "Czech Republic", "Democratic Republic of the Congo", "Denmark", "Djibouti", "Dominica", "Dominican Republic",
    "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji",
    "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala",
    "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hong Kong", "Hungary", "Iceland", "India",
    "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya",
    "Kiribati", "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya",
    "Liechtenstein", "Lithuania", "Luxembourg", "Macau", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali",
    "Malta", "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia",
    "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal", "Netherlands", "New Zealand",
    "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau",
    "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar",
    "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines",
    "Samoa", "San Marino", "São Tomé and Príncipe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles",
    "Sierra Leone", "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa",
    "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden", "Switzerland", "Syria",
    "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago",
    "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom",
    "United States", "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia",
    "Zimbabwe",
]

# World name -> spelling used by the university catalogue, where it differs.
CATALOGUE_NAMES = {"United States": "US", "United Kingdom": "UK"}

ALIASES = {
    "us": "United States", "usa": "United States", "u.s.": "United States", "u.s.a.": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "great britain": "United Kingdom", "britain": "United Kingdom",
    "korea": "South Korea", "republic of korea": "South Korea", "korea, republic of": "South Korea",
    "uae": "United Arab Emirates", "czechia": "Czech Republic", "holland": "Netherlands",
    "the netherlands": "Netherlands", "turkiye": "Turkey", "türkiye": "Turkey", "ivory coast": "Côte d'Ivoire",
    "russian federation": "Russia", "viet nam": "Vietnam", "swaziland": "Eswatini", "burma": "Myanmar",
    "east timor": "Timor-Leste", "cabo verde": "Cape Verde", "macao": "Macau",
}

_BY_KEY = {name.casefold(): name for name in WORLD}
_BY_KEY.update({alias: name for alias, name in ALIASES.items()})


def canonical(value: str) -> str | None:
    """The world name for `value` (any known spelling, any case), or None if it is not a known country."""
    return _BY_KEY.get((value or "").strip().casefold())


def catalogue_name(value: str) -> str | None:
    """The catalogue spelling for `value` ("United States" / "USA" -> "US"), or None if unknown."""
    name = canonical(value)
    return CATALOGUE_NAMES.get(name, name) if name else None


def options() -> list[dict]:
    """Every country with the value to store for target countries (`catalogue_name`)."""
    return [{"name": name, "catalogue_name": CATALOGUE_NAMES.get(name, name)} for name in WORLD]
