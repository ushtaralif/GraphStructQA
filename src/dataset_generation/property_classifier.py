"""
property_classifier.py — dynamically classify Wikidata properties into domains.

Fetches the English label + description for each property from the Wikidata API
and uses keyword matching to assign a domain. Results are cached locally so each
property is only fetched once across all pipeline runs.

Manual overrides in MANUAL_OVERRIDES take priority over keyword matching.
"""

import json
import os
import time
from typing import Dict, Optional

import requests

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "your_wikidata_user_pass)"}

# Keyword sets ordered by priority (first match wins).
# Keywords are checked against "label + description" in lowercase.
_DOMAIN_KEYWORDS = [
    ("Recognition",    ["award", "prize", "honor", "honour", "medal",
                        "recognition", "nominated for", "distinguished"]),
    ("Political",      ["position held", "office held", "political party",
                        "government", "minister", "president", "senator",
                        "elected", "diplomatic", "legislative", "parliament",
                        "chairperson", "head of state", "head of government"]),
    ("Academic",       ["university", "educated at", "academic degree",
                        "field of work", "doctoral", "thesis", "dissertation",
                        "research", "scholar", "alma mater", "student of",
                        "taught by", "supervisor"]),
    ("Organizational", ["organization", "company", "founded by", "subsidiary",
                        "employer", "industry", "director", "chairman", "ceo",
                        "parent organization", "has part", "member of"]),
    ("Biographical",   ["person", "occupation", "born", "death", "burial",
                        "spouse", "child", "parent", "sibling", "relative",
                        "nationality", "family", "native language",
                        "place of birth", "place of death", "residence",
                        "cause of death", "manner of death", "medical"]),
    ("Geographic",     ["country", "location", "place", "city", "region",
                        "capital", "territory", "continent", "coordinates",
                        "located in", "shares border", "administrative",
                        "body of water"]),
    ("Cultural",       ["culture", "symbol", "currency", "flag", "anthem",
                        "colour", "color", "instrument", "religion",
                        "tradition", "language of", "replaced by", "replaces"]),
]

# Manual overrides — these always win regardless of description text.
MANUAL_OVERRIDES: Dict[str, str] = {
    # Academic
    "P108": "Academic", "P69":   "Academic", "P185":  "Academic",
    "P184": "Academic", "P101":  "Academic", "P800":  "Academic",
    "P1066":"Academic", "P512":  "Academic", "P803":  "Academic",
    "P737": "Academic", "P1365": "Academic", "P1366": "Academic",
    # Recognition
    "P166": "Recognition", "P1411":"Recognition", "P2650":"Recognition",
    "P1027":"Recognition", "P138": "Recognition",
    # Political
    "P39":  "Political", "P102": "Political", "P463":  "Political",
    "P541": "Political", "P6":   "Political", "P122":  "Political",
    "P1313":"Political", "P1906":"Political", "P194":  "Political",
    "P488": "Political", "P2388":"Political", "P1142": "Political",
    "P530": "Political", "P241": "Political", "P1308": "Political",
    # Biographical
    "P19":  "Biographical", "P20": "Biographical", "P21":  "Biographical",
    "P22":  "Biographical", "P25": "Biographical", "P26":  "Biographical",
    "P40":  "Biographical", "P53": "Biographical", "P734": "Biographical",
    "P735": "Biographical", "P27": "Biographical", "P172": "Biographical",
    "P1344":"Biographical", "P1412":"Biographical","P106": "Biographical",
    "P551": "Biographical", "P509":"Biographical", "P1050":"Biographical",
    "P119": "Biographical", "P1196":"Biographical","P103": "Biographical",
    "P937": "Biographical",
    # Geographic
    "P17":  "Geographic", "P131":"Geographic", "P276": "Geographic",
    "P159": "Geographic", "P36": "Geographic", "P150": "Geographic",
    "P495": "Geographic", "P740":"Geographic", "P30":  "Geographic",
    "P361": "Geographic", "P47": "Geographic", "P1589":"Geographic",
    "P610": "Geographic", "P421":"Geographic", "P190": "Geographic",
    "P1376":"Geographic", "P206":"Geographic",
    # Organizational
    "P749": "Organizational", "P1416":"Organizational",
    "P355": "Organizational", "P452":"Organizational",
    "P112": "Organizational", "P527":"Organizational",
    "P1037":"Organizational",
    # Cultural
    "P237": "Cultural", "P163":"Cultural", "P417": "Cultural",
    "P462": "Cultural", "P38": "Cultural", "P822": "Cultural",
    "P155": "Cultural", "P156":"Cultural", "P6364":"Cultural",
    "P1303":"Cultural",
    # Arts & Media
    "P50":  "Arts & Media", "P57":  "Arts & Media", "P86":   "Arts & Media",
    "P136": "Arts & Media", "P161": "Arts & Media", "P170":  "Arts & Media",
    "P175": "Arts & Media", "P1476":"Arts & Media", "P179":  "Arts & Media",
    "P1811":"Arts & Media", "P453": "Arts & Media", "P674":  "Arts & Media",
    "P1441":"Arts & Media", "P144": "Arts & Media", "P577":  "Arts & Media",
    "P1191":"Arts & Media", "P123": "Arts & Media", "P400":  "Arts & Media",
    "P1433":"Arts & Media", "P2437":"Arts & Media", "P1113": "Arts & Media",
    "P725": "Arts & Media", "P449": "Arts & Media", "P1080": "Arts & Media",
    "P135": "Arts & Media",
    # Sports
    "P641": "Sports", "P54":  "Sports", "P118":  "Sports",
    "P413": "Sports", "P286": "Sports", "P115":  "Sports",
    "P1923":"Sports", "P2522":"Sports", "P3450": "Sports",
    # Academic (science)
    "P171": "Academic", "P105": "Academic", "P225":  "Academic",
    "P703": "Academic", "P274": "Academic", "P2102": "Academic",
    "P2101":"Academic", "P1086":"Academic", "P2054": "Academic",
    "P1057":"Academic", "P2293":"Academic", "P2175": "Academic",
    "P2176":"Academic", "P1995":"Academic", "P277":  "Academic",
}


# Logical / taxonomical meta-properties: they state what kind of thing an item is or how
# items / properties relate to each other, not a topical domain. They are removed before a query's domain is assigned (sparql_domain_classifier.py).
META_PROPERTIES: Dict[str, str] = {
    "P31":   "instance of",
    "P279":  "subclass of",
    "P1647": "subproperty of",
    "P1269": "facet of",
    "P460":  "said to be the same as",
    "P1889": "different from",
    "P1552": "has characteristic",
    "P1963": "properties for this type",
    "P910":  "topic's main category",
}


class PropertyClassifier:
    """
    Classifies Wikidata property IDs into domain strings.

    Priority:
      1. MANUAL_OVERRIDES (instant, no API)
      2. Local cache (file on disk, survives restarts)
      3. Wikidata API fetch → keyword match → cache result
    """

    def __init__(self, cache_path: str = "data/cache/property_domains.json"):
        self.cache_path = cache_path
        self._cache: Dict[str, Dict] = {}
        self._load_cache()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def domain(self, pid: str) -> str:
        """Return domain string for a property ID, fetching if necessary."""
        if pid in MANUAL_OVERRIDES:
            return MANUAL_OVERRIDES[pid]
        if pid in self._cache:
            return self._cache[pid]["domain"]
        self.prefetch([pid])
        return self._cache.get(pid, {}).get("domain", "Other")

    def label(self, pid: str) -> Optional[str]:
        """Return English label for a property ID, or None if unknown."""
        if pid in self._cache:
            return self._cache[pid].get("label")
        return None

    def prefetch(self, pids: list):
        """
        Batch-fetch labels + descriptions for a list of property IDs.
        Skips IDs already in MANUAL_OVERRIDES or local cache.
        """
        unknown = [
            p for p in pids
            if p not in MANUAL_OVERRIDES and p not in self._cache
        ]
        if not unknown:
            return
        self._fetch(unknown)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path) as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save_cache(self):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with open(self.cache_path, "w") as f:
            json.dump(self._cache, f, indent=2, sort_keys=True)

    def _fetch(self, pids: list):
        for i in range(0, len(pids), 50):
            batch = pids[i: i + 50]
            try:
                resp = requests.get(
                    WIKIDATA_API,
                    params={
                        "action": "wbgetentities",
                        "ids": "|".join(batch),
                        "props": "labels|descriptions",
                        "languages": "en",
                        "format": "json",
                    },
                    headers=HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                for pid, edata in resp.json().get("entities", {}).items():
                    label = (edata.get("labels", {})
                                  .get("en", {}).get("value", pid))
                    desc  = (edata.get("descriptions", {})
                                  .get("en", {}).get("value", ""))
                    domain = self._classify(label, desc)
                    self._cache[pid] = {
                        "label":  label,
                        "desc":   desc,
                        "domain": domain,
                    }
            except Exception as e:
                print(f"  [PropertyClassifier] fetch error: {e}")
            time.sleep(0.1)
        self._save_cache()

    @staticmethod
    def _classify(label: str, description: str) -> str:
        text = (label + " " + description).lower()
        for domain, keywords in _DOMAIN_KEYWORDS:
            if any(kw in text for kw in keywords):
                return domain
        return "Other"
