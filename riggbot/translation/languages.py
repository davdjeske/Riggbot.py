"""Canonical language codes.

The bot uses Google-style codes everywhere (config, flag map, output): "en", "ja", "zh-CN",
"zh-TW", ... Providers convert to and from their own codes. Comparisons ignore case.
"""

# Aliases other services use for the same languages.
_ALIASES = {
    'zh': 'zh-cn',          # plain "Chinese" means Simplified
    'zh-hans': 'zh-cn',     # Simplified Chinese
    'zh-hant': 'zh-tw',     # Traditional Chinese
    'zt': 'zh-tw',
    'nb': 'no',             # Norwegian Bokmål
    'iw': 'he',             # old code for Hebrew
    'jw': 'jv',             # old code for Javanese
}

# Languages Google Translate knows (from googletrans.constants.LANGUAGES), used to validate input.
_KNOWN = set('''
aar abk ace ach af ak alz am ar as ava awa ay az bak bal ban bbc bci be bem ber ber-atn bew bg bho bik
bm bn bod bre bs bts btx bua ca ceb cgg cha che chk chv ckb cnh co crh crs cs cy da de din doi dom dv
dyu dzo el en eo es et eu fa fa-af fao fi fij fil fon fr ful fur fy ga gaa gd gl glv gn gom gu ha haw
he hi hil hmn hr hrx ht hu hy iba id ig ilo is it ja jam jv ka kac kal kau kek kha kik kk km kn ko kom
kri ktu ku ky la lb lg lij lim lmo ln lo lt ltg luo lus lv mad mah mai mak mam mfe mg mhr mi min mk ml
mn mni-mtei mr ms ms-arab mt mwr my ndc-zw nde ne new nhe nl no nso nus ny oci om or oss pa pa-arab pag
pam pap pl por ps pt qu ro rom ru run rw sa sag sah sat scn sd shn si sk sl sm sme sn so sq sr ssw st
su sus sv sw szl ta tah tcy te tet tg th ti tiv tk tl ton tpi tr trp ts tsn tt tuk tum udm ug uk ur uz
vec ven vi war wol xh yi yo yua yue zap zh-cn zh-tw zu
'''.split())


def normalize(code: str) -> str:
    """Canonical form of a language code: 'EN' -> 'en', 'zh_cn' / 'ZH-HANS' -> 'zh-CN'."""
    # Tidy up: trim spaces, use "-" rather than "_", lowercase, and resolve aliases.
    key = code.strip().replace('_', '-').lower()
    key = _ALIASES.get(key, key)
    # Split "zh-cn" into "zh" and "cn"; codes without a "-" are done.
    lang, _, suffix = key.partition('-')
    if not suffix:
        return lang
    if len(suffix) == 2:
        suffix = suffix.upper()       # region: zh-CN
    elif len(suffix) == 4:
        suffix = suffix.title()       # script: ms-Arab
    return f'{lang}-{suffix}'


def same_language(a: str, b: str) -> bool:
    """True if two codes mean the same language, e.g. 'EN' and 'en'."""
    return normalize(a).lower() == normalize(b).lower()


def is_known(code: str) -> bool:
    """True if `code` is a language code Google Translate knows (used to validate /langflags input)."""
    return normalize(code).lower() in _KNOWN
