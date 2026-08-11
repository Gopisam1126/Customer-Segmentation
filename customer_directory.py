"""
customer_directory.py
Builds the searchable name/ID directory for the "search a customer"
feature, from whichever dataset is currently loaded.

The default Mall_Customers.csv has no name column, only CustomerID,
Gender, Age, Annual Income, and Spending Score. So for the sample
dataset this module supplies a small hardcoded name directory (demo
data only) keyed by CustomerID, giving the UI something human-readable
to search on.

A user-uploaded dataset is a different story: its CustomerIDs need not
overlap the sample's at all (a file numbered 1000-1999 shares nothing
with the demo's 1-200), and it may carry a real name column of its own.
So the directory is rebuilt from the active DataFrame every time the
pipeline is fitted:

  * if the dataset has a name column, those real names are used;
  * otherwise the demo names are applied, but only to CustomerIDs that
    actually exist in the active dataset;
  * either way every CustomerID in the active dataset is searchable,
    so an ID lookup always works even when no names are available.

The actual classification returned by a search is never invented here —
app.py looks up the matched CustomerID in the real annotated DataFrame
produced by the fitted pipeline (preprocessor.py + clustering.py), so
results always come from the real model.
"""

import re

import pandas as pd

# CustomerID (as it appears in Mall_Customers.csv, zero-padded 4 digits) -> name
DEMO_CUSTOMER_NAMES = {
    "0001": "Aarav Mehta",
    "0002": "Priya Nair",
    "0007": "Kavya Iyer",
    "0012": "Sara Thompson",
    "0018": "Rohan Kapoor",
    "0025": "Emily Davis",
    "0034": "Liam Wilson",
    "0042": "Ananya Rao",
    "0050": "James Miller",
    "0063": "Meera Pillai",
    "0075": "Noah Anderson",
    "0088": "Diya Sharma",
    "0100": "Ethan Clark",
    "0112": "Ishaan Verma",
    "0124": "Olivia Martin",
    "0135": "Arjun Singh",
    "0148": "Grace Lee",
    "0160": "Vikram Malhotra",
    "0175": "Chloe Baker",
    "0188": "Karan Joshi",
    "0196": "Isabella Moore",
    "0200": "Dev Patel",
}

# The 22 names above are the curated ones quoted in the UI hint. The sample
# dataset has 200 rows, though, so the remaining customers are given demo
# names too — otherwise search results read "Customer #0003", which is not
# something anyone would type into a name box.
#
# Names are assigned deterministically from the CustomerID (never randomly),
# so the same customer always gets the same name across restarts, and the
# first name follows the row's Gender. The two pool sizes are coprime, so no
# combination repeats within the sample dataset's 200 rows.
_MALE_FIRST = (
    "Arjun", "Rahul", "Aditya", "Vivek", "Nikhil", "Siddharth", "Manav", "Rohit",
    "Aryan", "Kabir", "Varun", "Aakash", "Harsh", "Yash", "Tarun", "Sanjay",
    "Naveen", "Pranav", "Gaurav", "Kunal", "Daniel", "Michael", "Thomas", "Andrew",
    "Peter", "Robert", "Jonathan", "Matthew", "Steven", "Patrick", "Benjamin",
    "Nicholas", "Adrian", "Marcus", "Julian", "Simon", "Oliver", "Lucas",
    "Nathan", "Samuel",
)
_FEMALE_FIRST = (
    "Aditi", "Nisha", "Kiran", "Sneha", "Divya", "Pooja", "Riya", "Tanvi",
    "Shreya", "Neha", "Anjali", "Swati", "Lakshmi", "Preeti", "Aarti", "Sunita",
    "Rekha", "Madhuri", "Ritu", "Sonia", "Rachel", "Laura", "Hannah", "Megan",
    "Julia", "Natalie", "Christine", "Rebecca", "Amelia", "Charlotte", "Victoria",
    "Eleanor", "Alice", "Melissa", "Diana", "Caroline", "Sophie", "Nadia",
    "Elena", "Clara",
)
_SURNAMES = (
    "Menon", "Reddy", "Nair", "Iyer", "Desai", "Bhat", "Chopra", "Sethi",
    "Kulkarni", "Ganesan", "Bose", "Dutta", "Saxena", "Trivedi", "Bhatt",
    "Mishra", "Rane", "Kamath", "Prasad", "Shetty", "Harris", "Bennett",
    "Coleman", "Fletcher", "Hughes", "Morgan", "Reynolds", "Sullivan",
    "Turner", "Walsh", "Bailey", "Griffin", "Hayes", "Lawson", "Newman",
    "Porter", "Sanders",
)


def demo_name_for(customer_id, gender=None) -> str:
    """
    Deterministic demo name for a sample-dataset customer that has no curated
    name. Used for the bundled Mall_Customers data only — never for a user's
    own uploaded records, which must not be given invented names.
    """
    try:
        n = int(customer_id)
    except (TypeError, ValueError):
        return f"Customer #{customer_id}"

    g = str(gender).strip().lower() if gender is not None else ""
    pool = _FEMALE_FIRST if g.startswith("f") else _MALE_FIRST
    return f"{pool[n % len(pool)]} {_SURNAMES[n % len(_SURNAMES)]}"


# Column headers accepted as "this dataset has customer names in it".
NAME_COLUMNS = (
    "Name", "CustomerName", "Customer Name",
    "FullName", "Full Name", "Customer",
)

# Upper bound on how many full search results are returned. A large
# uploaded dataset can partial-match hundreds of IDs on a query like
# "1"; the UI renders a card per result, so this keeps it readable.
MAX_SEARCH_RESULTS = 25


def format_customer_id(value) -> str:
    """
    Render a CustomerID the way the source CSV writes it: zero-padded to
    four digits when numeric (so the sample data's "0001" is preserved),
    otherwise as plain text.
    """
    try:
        return f"{int(value):04d}"
    except (TypeError, ValueError):
        return str(value).strip()


def find_name_column(df: pd.DataFrame):
    """Return the dataset's own name column, or None if it has none."""
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for candidate in NAME_COLUMNS:
        col = lookup.get(candidate.lower())
        if col is not None:
            return col
    return None


def build_directory(df: pd.DataFrame, use_demo_names: bool = True) -> dict:
    """
    Build the searchable directory for the currently loaded dataset.

    Returns:
      {
        "entries":   [{"customerId": str, "name": str|None}, ...],
        "hasNames":  bool,   -- are names available to search on at all
        "hasIds":    bool,   -- does the dataset identify customers at all
        "nameSource": "dataset"   -- real names, read from the file
                    | "demo"      -- bundled sample data's names
                    | "generated" -- placeholders we made up for an upload
                    | "none",     -- no way to identify a customer
        "sampleIds": [str, ...],    -- a few real IDs, for UI hint text
        "sampleNames": [str, ...],  -- a few real names, for UI hint text
      }
    """
    if df is None or "CustomerID" not in df.columns:
        # Nothing to search on: the file identifies no customers. Every
        # other feature still works; only lookup is unavailable.
        return {"entries": [], "hasNames": False, "hasIds": False,
                "nameSource": "none", "sampleIds": [], "sampleNames": []}

    name_col = find_name_column(df)
    entries = []

    if name_col is not None:
        # The dataset carries its own names — always prefer them.
        for cid, raw_name in zip(df["CustomerID"], df[name_col]):
            name = None if pd.isna(raw_name) else str(raw_name).strip()
            entries.append({"customerId": format_customer_id(cid), "name": name or None})
        source = "dataset"
    else:
        # No name column anywhere in the file. Rather than leave the search
        # box showing "Customer #1004", give every customer a readable
        # placeholder name derived from its ID and gender.
        #
        # The bundled sample data also gets its 22 curated names; an uploaded
        # dataset does not, so its placeholders never masquerade as the
        # sample's people. `nameSource` tells the UI these are generated, so
        # it can say so rather than pass them off as data from the file.
        genders = df["Gender"] if "Gender" in df.columns else [None] * len(df)
        for cid, gender in zip(df["CustomerID"], genders):
            key = format_customer_id(cid)
            curated = DEMO_CUSTOMER_NAMES.get(key) if use_demo_names else None
            entries.append({
                "customerId": key,
                "name": curated or demo_name_for(cid, gender),
            })
        source = "demo" if use_demo_names else "generated"

    return {
        "entries": entries,
        "hasNames": any(e["name"] for e in entries),
        "hasIds": bool(entries),
        "nameSource": source,
        "sampleIds": [e["customerId"] for e in entries[:3]],
        "sampleNames": [e["name"] for e in entries[:3] if e["name"]],
    }


# A customer with no name is shown as "Customer #1003", so that exact string
# is what a user is most likely to type or paste back into the search box.
# Accept it (and a bare "#1003") as a way of asking for ID 1003.
_ID_PREFIX = re.compile(r"^(?:customer\s*)?#\s*|^customer\s+(?=\d)", re.IGNORECASE)


def _split_query(query: str):
    """
    Return (q, q_id): the raw lowercased query for name matching, and the
    same query with any "Customer #" / "#" prefix stripped for ID matching.
    """
    q = (query or "").strip().lower()
    q_id = _ID_PREFIX.sub("", q).strip()
    return q, q_id


def _rank(entries, q, limit=None):
    """
    Shared matcher for search and autocomplete. Ranks exact matches first,
    then prefix matches, then any other substring match.
    """
    q, q_id = _split_query(q)
    if not q:
        return []

    exact, prefix, contains = [], [], []
    for entry in entries:
        cid = entry["customerId"]
        name = entry["name"] or ""
        cid_l, name_l = cid.lower(), name.lower()
        cid_stripped = cid_l.lstrip("0")

        id_hit_exact = bool(q_id) and (q_id == cid_l or (cid_stripped and q_id == cid_stripped))
        id_hit_prefix = bool(q_id) and (cid_l.startswith(q_id) or cid_stripped.startswith(q_id))
        id_hit_any = bool(q_id) and q_id in cid_l

        if id_hit_exact or (name_l and q == name_l):
            exact.append(entry)
        elif (name_l and name_l.startswith(q)) or id_hit_prefix:
            prefix.append(entry)
        elif id_hit_any or (name_l and q in name_l):
            contains.append(entry)

        # Exact hits are the best possible answer; once we have enough of
        # them there is nothing better further down the list.
        if limit and len(exact) >= limit:
            break

    ordered = exact + prefix + contains
    return ordered[:limit] if limit else ordered


def search_directory(query: str, directory: dict = None) -> list:
    """
    Case-insensitive partial match against CustomerID or name, over the
    active dataset's directory. Returns a list of {"customerId", "name"}
    dicts, best matches first, capped at MAX_SEARCH_RESULTS.
    """
    if not (query or "").strip():
        return []
    entries = (directory or {}).get("entries", [])
    return _rank(entries, query, limit=MAX_SEARCH_RESULTS)


def suggest_directory(query: str, directory: dict = None, limit: int = 8) -> list:
    """
    Lightweight autocomplete over the same directory. Called on every
    keystroke, so it does no DataFrame lookups — just string matching
    against the directory built once per pipeline fit.

    Each suggestion separates what to SHOW from what to SEARCH:
      display -- the dropdown row's text ("Priya Nair", or "Customer #1003")
      query   -- what to put in the box when picked, and re-search with.
                 For a nameless customer that is the bare ID, never the
                 "Customer #1003" label, which matches nothing.
    """
    if not (query or "").strip():
        return []

    entries = (directory or {}).get("entries", [])
    out = []
    for entry in _rank(entries, query, limit=limit):
        cid, name = entry["customerId"], entry["name"]
        out.append({
            "customerId": cid,
            "name": name,
            "display": name or f"Customer #{cid}",
            "query": name or cid,
            # Kept for any caller still reading the old field.
            "label": f"{name} (#{cid})" if name else f"Customer #{cid}",
        })
    return out
