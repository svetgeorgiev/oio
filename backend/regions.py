"""Conservative topic-focused research profiles. These are NOT geolocation classifiers.

A profile is an investigator-selected *topic filter preset*. Its name and
keywords do not establish where a post was authored or who controls an account.
"""
import re

# Example topics are neutral location/institution terms, not political labels.
PROFILES = (
    {'id': 'custom', 'name': 'Custom research', 'flag': '🌐',
     'timezone': 'UTC', 'keywords': '', 'languages': [],
     'description': 'Select your own public topics and optional declared-language filter.'},
    {'id': 'eu', 'name': 'European topics', 'flag': '🇪🇺',
     'timezone': 'Europe/Brussels', 'keywords': 'European Union | Brussels | Strasbourg', 'languages': [],
     'description': 'Multilingual EU-related public topics; no country-of-author inference.'},
    {'id': 'uk', 'name': 'United Kingdom topics', 'flag': '🇬🇧',
     'timezone': 'Europe/London', 'keywords': 'United Kingdom | Westminster | London', 'languages': ['en'],
     'description': 'UK-related public topics; English-language filter is optional.'},
    {'id': 'bg', 'name': 'Bulgarian topics', 'flag': '🇧🇬',
     'timezone': 'Europe/Sofia', 'keywords': 'България | София | Пловдив', 'languages': ['bg'],
     'description': 'Bulgarian-language, Bulgaria-related discussion; not author location.'},
    {'id': 'de', 'name': 'German topics', 'flag': '🇩🇪',
     'timezone': 'Europe/Berlin', 'keywords': 'Deutschland | Berlin | Bundestag', 'languages': ['de'],
     'description': 'German-language, Germany-related public topics; not author location.'},
    {'id': 'fr', 'name': 'French topics', 'flag': '🇫🇷',
     'timezone': 'Europe/Paris', 'keywords': 'France | Paris | Assemblée nationale', 'languages': ['fr'],
     'description': 'French-language, France-related public topics; not author location.'},
)
PROFILE_BY_ID = {p['id']: p for p in PROFILES}
# Well-formed BCP 47 primary or primary-region tags; do not try to infer language.
LANG_RE = re.compile(r'^[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,2}$')


def capture_languages(value):
    """Validate an optional language allowlist for new observation sessions."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 6:
        raise ValueError('languages must be a list of at most six language tags')
    result = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError('Invalid language tag')
        tag = item.strip().lower()
        if not LANG_RE.fullmatch(tag):
            raise ValueError('Invalid language tag; use codes such as bg, en, fr or en-gb')
        if tag not in result:
            result.append(tag)
    return result


def observed_languages(value):
    """Retain only plausible, explicitly supplied public record.langs; unknown == []."""
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:10]:
        if isinstance(item, str):
            tag = item.strip().lower()
            if LANG_RE.fullmatch(tag) and tag not in result:
                result.append(tag)
    return result


def declared_language_matches(record_tags, requested):
    """A missing record.langs is unknown and will NOT match a selected filter."""
    if not requested:
        return True
    for wanted in requested:
        for tag in record_tags:
            if tag == wanted or ('-' not in wanted and tag.startswith(wanted + '-')):
                return True
    return False


def profile_id(value):
    if not isinstance(value, str) or value not in PROFILE_BY_ID:
        raise ValueError('Unknown research profile')
    return value


def public_profiles():
    return [dict(p, languages=list(p['languages'])) for p in PROFILES]
