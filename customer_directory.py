"""
customer_directory.py
Hardcoded demo mapping of customer names -> CustomerID.

The Mall_Customers.csv dataset has no name column, only CustomerID,
Gender, Age, Annual Income, and Spending Score. For the "search a
customer by name or ID" feature, this module supplies a small
hardcoded name directory (demo data only) so the UI has something
human-readable to search on. The actual classification returned by
a search is never invented here — app.py looks up the matched
CustomerID in the real annotated DataFrame produced by the fitted
pipeline (preprocessor.py + clustering.py), so results always come
from the real model.
"""

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


def search_directory(query: str) -> list:
    """
    Case-insensitive partial match against CustomerID or name.
    Returns a list of {"customerId", "name"} dicts, best matches first
    (exact ID match, then exact name match, then partial matches).
    """
    if not query:
        return []
    q = query.strip().lower()

    exact, partial = [], []
    for cid, name in DEMO_CUSTOMER_NAMES.items():
        entry = {"customerId": cid, "name": name}
        if q == cid.lower() or q == cid.lstrip("0").lower() or q == name.lower():
            exact.append(entry)
        elif q in cid.lower() or q in name.lower():
            partial.append(entry)

    return exact + partial


def suggest_directory(query: str, limit: int = 8) -> list:
    """
    Lightweight autocomplete over the same demo directory: returns up to
    `limit` {"customerId", "name", "label"} entries whose name or ID
    contains the query, ranked with name-prefix matches first, then
    ID-prefix matches, then any other substring match. Intended to be
    called on every keystroke, so it does no DataFrame lookups — just
    string matching against the small hardcoded directory.
    """
    q = (query or "").strip().lower()
    if not q:
        return []

    prefix_name, prefix_id, contains = [], [], []
    for cid, name in DEMO_CUSTOMER_NAMES.items():
        entry = {"customerId": cid, "name": name, "label": f"{name} (#{cid})"}
        name_l, cid_l, cid_stripped = name.lower(), cid.lower(), cid.lstrip("0").lower()
        if name_l.startswith(q):
            prefix_name.append(entry)
        elif cid_l.startswith(q) or cid_stripped.startswith(q):
            prefix_id.append(entry)
        elif q in name_l or q in cid_l:
            contains.append(entry)

    ordered = prefix_name + prefix_id + contains
    return ordered[:limit]
