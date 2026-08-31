import secrets
import string
from django.conf import settings
from .models import EmailAddress, get_default_domain

# Lightweight curated wordlists for human-like random email generation
ADJECTIVES = [
    'amber', 'azure', 'bold', 'brave', 'bright', 'calm', 'clever', 'cool',
    'crisp', 'crystal', 'cyan', 'dark', 'dawn', 'deep', 'dusk', 'eager',
    'early', 'easy', 'emerald', 'epic', 'fair', 'fast', 'fine', 'flash',
    'frost', 'gentle', 'glad', 'gold', 'golden', 'grand', 'green', 'happy',
    'hardy', 'honest', 'iron', 'jade', 'keen', 'light', 'lively', 'lucky',
    'magic', 'maple', 'misty', 'moon', 'neat', 'neon', 'noble', 'ocean',
    'opal', 'pale', 'prime', 'pure', 'quick', 'quiet', 'rapid', 'rare',
    'red', 'rich', 'rose', 'ruby', 'rusty', 'sage', 'sharp', 'shiny',
    'silent', 'silk', 'silver', 'sleek', 'smart', 'solar', 'spark', 'spicy',
    'star', 'stone', 'storm', 'sunny', 'super', 'sweet', 'swift', 'teal',
    'tidy', 'true', 'urban', 'valiant', 'vast', 'velvet', 'vivid', 'warm',
    'wild', 'wise', 'zesty'
]

NOUNS = [
    'badger', 'bear', 'bison', 'breeze', 'cedar', 'cliff', 'cloud', 'comet',
    'coral', 'crane', 'crag', 'creek', 'drift', 'dune', 'eagle', 'elm',
    'ember', 'falcon', 'finch', 'flame', 'forest', 'fox', 'frost', 'galaxy',
    'gecko', 'glade', 'grove', 'harbor', 'haven', 'hawk', 'heron', 'hound',
    'island', 'jasper', 'jay', 'lagoon', 'lark', 'leaf', 'lion', 'lynx',
    'marsh', 'meadow', 'meteor', 'moose', 'moss', 'nebula', 'oak', 'oasis',
    'ocean', 'orca', 'otter', 'owl', 'panda', 'path', 'peak', 'pebble',
    'pine', 'planet', 'pond', 'quail', 'rain', 'raven', 'reef', 'ridge',
    'river', 'robin', 'sage', 'shadow', 'shore', 'spark', 'sparrow', 'spring',
    'star', 'stone', 'storm', 'stream', 'summit', 'tiger', 'timber', 'trail',
    'valley', 'viper', 'vortex', 'wave', 'whale', 'willow', 'wind', 'wolf',
    'woods', 'zebra'
]

GENERATOR_STYLES = ('short', 'standard', 'human_like')


def generate_raw_candidate(style='standard'):
    """
    Generate a raw local-part string based on the chosen style.
    - short: 5 alphanumeric characters (e.g. 'x7k29')
    - standard: 8 alphanumeric characters (e.g. 'k7x92m4p')
    - human_like: adjective + noun + 2-digit number (e.g. 'silverfox42')
    """
    alphabet = string.ascii_lowercase + string.digits
    
    if style == 'short':
        # 5 characters: ensure start with letter or digit (ascii_lowercase + digits already is)
        return ''.join(secrets.choice(alphabet) for _ in range(5))
    elif style == 'human_like':
        adj = secrets.choice(ADJECTIVES)
        noun = secrets.choice(NOUNS)
        num = secrets.randbelow(90) + 10  # 10 to 99
        return f"{adj}{noun}{num}"
    else:  # default to 'standard'
        return ''.join(secrets.choice(alphabet) for _ in range(8))


def generate_random_local_part(style='standard', domain=None, max_attempts=100):
    """
    Generate a unique, non-reserved local_part for the given domain.
    Retries up to max_attempts to ensure uniqueness.
    """
    if style not in GENERATOR_STYLES:
        style = 'standard'
        
    if domain is None:
        domain = get_default_domain()
        
    reserved = set(getattr(settings, 'RESERVED_EMAIL_ADDRESSES', []))

    for _ in range(max_attempts):
        candidate = generate_raw_candidate(style=style).lower()
        
        # Check against reserved addresses
        if candidate in reserved:
            continue
            
        # Check uniqueness in database
        if not EmailAddress.objects.filter(local_part=candidate, domain=domain).exists():
            return candidate

    raise RuntimeError("Failed to generate a unique email address after multiple attempts.")
