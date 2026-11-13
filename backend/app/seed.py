"""Deterministic synthetic seed: 25 shops, ~100-product catalogue, the crafted
three-shop demo scenario (bilateral swaps fail, the three-shop cycle works),
plus quotes, random lots and needs for the remaining shops."""
import random
from datetime import date, timedelta

from . import db

# (brand, base_name_hi, category, emoji, aliases, [(variant, pack, unit, mrp_paise)])
CATALOG = [
    ("Parle-G", "पारले-जी", "biscuit", "🍪", ["parle", "parle-g", "पारले", "glucose biscuit"],
     [("100g", 100, "g", 1000), ("250g", 250, "g", 2500), ("550g", 550, "g", 6000)]),
    ("Marie Gold", "मैरी गोल्ड", "biscuit", "🍪", ["marie", "मैरी"],
     [("100g", 100, "g", 1500), ("250g", 250, "g", 3500), ("600g", 600, "g", 7500)]),
    ("Good Day", "गुड डे", "biscuit", "🍪", ["good day", "goodday", "गुड डे"],
     [("200g", 200, "g", 3000), ("600g", 600, "g", 8500)]),
    ("Hide & Seek", "हाइड एंड सीक", "biscuit", "🍪", ["hide seek", "हाइड सीक"],
     [("120g", 120, "g", 3000), ("300g", 300, "g", 6500)]),
    ("Tata Tea", "टाटा चाय", "tea", "☕", ["tata tea", "chai patti", "चाय पत्ती"],
     [("250g", 250, "g", 14000), ("500g", 500, "g", 27000), ("1kg", 1000, "g", 52000)]),
    ("Red Label", "रेड लेबल", "tea", "☕", ["red label", "रेड लेबल"],
     [("250g", 250, "g", 15000), ("500g", 500, "g", 29000)]),
    ("Nescafe Classic", "नेस्कैफे", "coffee", "☕", ["nescafe", "coffee", "कॉफी"],
     [("50g", 50, "g", 18000), ("100g", 100, "g", 33000)]),
    ("Tata Salt", "टाटा नमक", "salt", "🧂", ["tata salt", "namak", "नमक"],
     [("1kg", 1, "kg", 2800)]),
    ("Aashirvaad Atta", "आशीर्वाद आटा", "atta", "🌾", ["aashirvaad", "atta", "आटा"],
     [("5kg", 5, "kg", 26000), ("10kg", 10, "kg", 49000)]),
    ("India Gate", "इंडिया गेट", "rice", "🍚", ["india gate", "basmati", "चावल"],
     [("Classic 1kg", 1, "kg", 16000), ("Classic 5kg", 5, "kg", 75000)]),
    ("Tata Sampann Toor Dal", "ताता तूर दाल", "dal", "🫘", ["toor dal", "arhar", "तूर दाल"],
     [("500g", 500, "g", 9500), ("1kg", 1, "kg", 18500)]),
    ("Tata Sampann Moong Dal", "ताता मूंग दाल", "dal", "🫘", ["moong dal", "मूंग दाल"],
     [("500g", 500, "g", 9000), ("1kg", 1, "kg", 17000)]),
    ("Tata Sampann Besan", "ताता बेसन", "atta", "🌾", ["besan", "बेसन"],
     [("500g", 500, "g", 7500)]),
    ("Fortune Sunflower Oil", "फॉर्च्यून तेल", "oil", "🛢️", ["fortune", "sunflower oil", "तेल"],
     [("1L", 1, "L", 14000), ("5L", 5, "L", 68000)]),
    ("Dhara Mustard Oil", "धारा सरसों तेल", "oil", "🛢️", ["dhara", "mustard oil", "सरसों तेल"],
     [("1L", 1, "L", 15000), ("5L", 5, "L", 72000)]),
    ("Maggi", "मैगी", "noodles", "🍜", ["maggi", "मैगी", "noodles"],
     [("70g", 70, "g", 1400), ("4-pack 280g", 280, "g", 5600), ("12-pack", 840, "g", 14000)]),
    ("Top Ramen", "टॉप रामन", "noodles", "🍜", ["top ramen", "रामन"],
     [("70g", 70, "g", 1400)]),
    ("Kurkure", "कुरकुरे", "snack", "🥨", ["kurkure", "कुरकुरे"],
     [("90g", 90, "g", 1800)]),
    ("Lay's", "लेज़", "snack", "🥔", ["lays", "लेज़"],
     [("52g", 52, "g", 2000), ("90g", 90, "g", 3500)]),
    ("Haldiram Bhujia", "हल्दीराम भुजिया", "snack", "🥨", ["bhujia", "भुजिया", "haldiram"],
     [("200g", 200, "g", 5500), ("1kg", 1, "kg", 24000)]),
    ("Haldiram Soan Papdi", "हल्दीराम सोन पापड़ी", "sweet", "🍬", ["soan papdi", "सोन पापड़ी"],
     [("250g", 250, "g", 6000), ("500g", 500, "g", 11000)]),
    ("Colgate Strong Teeth", "कोलगेट", "toothpaste", "🪥", ["colgate", "कोलगेट", "manjan", "मंजन"],
     [("100g", 100, "g", 5500), ("200g", 200, "g", 9900), ("300g", 300, "g", 14500)]),
    ("Pepsodent", "पेप्सोडेंट", "toothpaste", "🪥", ["pepsodent", "पेप्सोडेंट"],
     [("140g", 140, "g", 7600)]),
    ("Dabur Red", "डाबर रेड", "toothpaste", "🪥", ["dabur red", "डाबर रेड"],
     [("100g", 100, "g", 9500)]),
    ("Clinic Plus", "क्लिनिक प्लस", "shampoo", "🧴", ["clinic plus", "क्लिनिक प्लस", "shampoo", "शैम्पू"],
     [("175ml", 175, "ml", 8500), ("355ml", 355, "ml", 16000)]),
    ("Sunsilk", "सनसिल्क", "shampoo", "🧴", ["sunsilk", "सनसिल्क"],
     [("175ml", 175, "ml", 8000)]),
    ("Head & Shoulders", "हेड एंड शोल्डर्स", "shampoo", "🧴", ["head shoulders"],
     [("180ml", 180, "ml", 14500)]),
    ("Lifebuoy", "लाइफबॉय", "soap", "🧼", ["lifebuoy", "लाइफबॉय", "sabun", "साबुन"],
     [("100g", 100, "g", 2800), ("150g", 150, "g", 4000)]),
    ("Lux", "लक्स", "soap", "🧼", ["lux", "लक्स"],
     [("100g", 100, "g", 2800)]),
    ("Cinthol", "सिंथोल", "soap", "🧼", ["cinthol", "सिंथोल"],
     [("100g", 100, "g", 3500)]),
    ("Surf Excel", "सर्फ एक्सेल", "detergent", "🧺", ["surf", "washing powder", "वॉशिंग पाउडर"],
     [("500g", 500, "g", 6200), ("1kg", 1, "kg", 12000), ("2kg", 2, "kg", 23500)]),
    ("Ariel", "एरियल", "detergent", "🧺", ["ariel", "एरियल"],
     [("1kg", 1, "kg", 18500)]),
    ("Ghadi Detergent", "घड़ी", "detergent", "🧺", ["ghadi", "घड़ी"],
     [("1kg", 1, "kg", 6500)]),
    ("Vim Bar", "विम बार", "dishwash", "🍽️", ["vim", "बार", "bartan sabun"],
     [("200g", 200, "g", 2000), ("400g", 400, "g", 3800)]),
    ("Pril", "प्रिल", "dishwash", "🍽️", ["pril", "प्रिल"],
     [("500ml", 500, "ml", 9900)]),
    ("Amul Butter", "अमूल बटर", "dairy", "🧈", ["amul", "butter", "मक्खन"],
     [("100g", 100, "g", 5600), ("500g", 500, "g", 26500)]),
    ("Amul Milk Powder", "अमूल मिल्क पाउडर", "dairy", "🥛", ["milk powder", "दूध पाउडर"],
     [("500g", 500, "g", 33000)]),
    ("Madhur Sugar", "मधुर चीनी", "sugar", "🍬", ["madhur", "sugar", "cheeni", "चीनी"],
     [("1kg", 1, "kg", 4800), ("5kg", 5, "kg", 23000)]),
    ("MDH Chana Masala", "एमडीएच छोले मसाला", "masala", "🌶️", ["mdh", "chana masala", "मसाला"],
     [("100g", 100, "g", 6500)]),
    ("MDH Garam Masala", "एमडीएच गरम मसाला", "masala", "🌶️", ["garam masala", "गरम मसाला"],
     [("100g", 100, "g", 8000)]),
    ("Everest Haldi", "एवरेस्ट हल्दी", "masala", "🌶️", ["haldi", "हल्दी", "turmeric"],
     [("100g", 100, "g", 4000), ("200g", 200, "g", 7500)]),
    ("Everest Lal Mirch", "एवरेस्ट लाल मिर्च", "masala", "🌶️", ["lal mirch", "लाल मिर्च", "chilli powder"],
     [("100g", 100, "g", 4200)]),
    ("Everest Dhaniya", "एवरेस्ट धनिया", "masala", "🌶️", ["dhaniya", "धनिया"],
     [("100g", 100, "g", 4000)]),
    ("Bournvita", "बोर्नविटा", "drink", "🥤", ["bournvita", "बोर्नविटा"],
     [("500g", 500, "g", 24500), ("1kg", 1, "kg", 46000)]),
    ("Glucon-D", "ग्लूकोन डी", "drink", "🥤", ["glucon", "ग्लूकोन"],
     [("250g", 250, "g", 11500)]),
    ("Parachute Coconut Oil", "पैराशूट नारियल तेल", "hairoil", "💆", ["parachute", "coconut oil", "नारियल तेल"],
     [("200ml", 200, "ml", 8500), ("600ml", 600, "ml", 23000)]),
    ("Dabur Honey", "डाबर शहद", "honey", "🍯", ["dabur", "honey", "शहद"],
     [("250g", 250, "g", 15500)]),
    ("Frooti", "फ्रूटी", "drink", "🧃", ["frooti", "फ्रूटी"],
     [("200ml", 200, "ml", 1000)]),
    ("Real Mixed Fruit", "रियल जूस", "drink", "🧃", ["real juice", "रियल"],
     [("1L", 1, "L", 11500)]),
    ("Knorr Soup", "नूडल सूप", "soup", "🍲", ["knorr", "soup", "सूप"],
     [("50g", 50, "g", 6500)]),
    ("Britannia Cake", "ब्रिटानिया केक", "snack", "🍰", ["cake", "केक"],
     [("65g", 65, "g", 1500)]),
    ("Dairy Milk", "डेयरी मिल्क", "chocolate", "🍫", ["dairy milk", "cadbury", "चॉकलेट"],
     [("24g", 24, "g", 1000), ("54g", 54, "g", 3000)]),
    ("Mango Bite", "मैंगो बाइट", "candy", "🍬", ["mango bite", "कैंडी", "toffee"],
     [("100g pouch", 100, "g", 3000)]),
    ("Dettol Handwash", "डेटॉल", "hygiene", "🧴", ["dettol", "डेटॉल", "handwash"],
     [("200ml", 200, "ml", 9900)]),
    ("Harpic", "हार्पिक", "cleaning", "🚽", ["harpic", "हार्पिक"],
     [("500ml", 500, "ml", 10500)]),
    ("Odonil", "ओडोनिल", "freshener", "🌬️", ["odonil", "ओडोनिल"],
     [("50g", 50, "g", 3500)]),
]

# Generic aliases deliberately map to several SKUs → ambiguity/clarification cases.
GENERIC_ALIASES = [
    ("biscuit", "बिस्कुट", ["Parle-G", "Marie Gold", "Good Day", "Hide & Seek"]),
    ("soap", "साबुन", ["Lifebuoy", "Lux", "Cinthol"]),
    ("chips", "चिप्स", ["Lay's", "Kurkure"]),
    ("chocolate", "चॉकलेट", ["Dairy Milk"]),
    ("tea", "चाय", ["Tata Tea", "Red Label"]),
    ("oil", "तेल", ["Fortune Sunflower Oil", "Dhara Mustard Oil", "Parachute Coconut Oil"]),
    ("detergent", "डिटर्जेंट", ["Surf Excel", "Ariel", "Ghadi Detergent"]),
    ("toothpaste", "टूथपेस्ट", ["Colgate Strong Teeth", "Pepsodent", "Dabur Red"]),
    ("shampoo", "शैम्पू", ["Clinic Plus", "Sunsilk", "Head & Shoulders"]),
    ("masala", "मसाला", ["MDH Chana Masala", "MDH Garam Masala", "Everest Haldi", "Everest Lal Mirch"]),
    ("sugar", "चीनी", ["Madhur Sugar"]),
    ("atta", "आटा", ["Aashirvaad Atta", "Tata Sampann Besan"]),
]

SHOPS = [
    ("Sharma Kirana Store", "शर्मा किराना स्टोर", "Ramesh Sharma"),
    ("Gupta General Store", "गुप्ता जनरल स्टोर", "Suresh Gupta"),
    ("Khan Provision Store", "खान प्रोविज़न स्टोर", "Imran Khan"),
    ("Verma Super Mart", "वर्मा सुपर मार्ट", "Anil Verma"),
    ("Yadav Provision", "यादव प्रोविज़न", "Kishan Yadav"),
    ("Meena Stores", "मीणा स्टोर्स", "Rakesh Meena"),
    ("Jain Ration Shop", "जैन रेशन शॉप", "Mukesh Jain"),
    ("Choudhary Kirana", "चौधरी किराना", "Omprakash Choudhary"),
    ("Aggarwal Traders", "अग्रवाल ट्रेडर्स", "Naresh Aggarwal"),
    ("Mishra Provision", "मिश्रा प्रोविज़न", "Shyam Mishra"),
    ("Patel Corner Store", "पटेल कॉर्नर स्टोर", "Bhavesh Patel"),
    ("Singh General", "सिंह जनरल", "Harvinder Singh"),
    ("Reddy Stores", "रेड्डी स्टोर्स", "Venkat Reddy"),
    ("Nair Mart", "नायर मार्ट", "Vinod Nair"),
    ("Ali Stores", "अली स्टोर्स", "Ali Saifi"),
    ("Tiwari Bhandar", "तिवारी भंडार", "Dinesh Tiwari"),
    ("Dubey Kirana", "दुबे किराना", "Rajesh Dubey"),
    ("Joshi Provision", "जोशी प्रोविज़न", "Sanjay Joshi"),
    ("Chauhan Store", "चौहान स्टोर", "Vikram Chauhan"),
    ("Rathore Kirana", "राठौड़ किराना", "Devendra Rathore"),
    ("Saxena Stores", "सक्सेना स्टोर्स", "Alok Saxena"),
    ("Bhandari Mart", "भंडारी मार्ट", "Girish Bhandari"),
    ("Kulkarni Provision", "कुलकर्णी प्रोविज़न", "Amit Kulkarni"),
    ("Iyer Stores", "अय्यर स्टोर्स", "Mohan Iyer"),
    ("Prajapati Kirana", "प्रजापति किराना", "Bhavna Prajapati"),
]

TODAY = date(2026, 10, 24)


def _catalog_rows():
    """Return (products, product_aliases, generic_alias_product_ids)."""
    products = []
    aliases = []
    generic_ids = {}
    pid = 0
    for brand, hi, cat, emoji, base_aliases, variants in CATALOG:
        for label, pack, unit, mrp in variants:
            pid += 1
            name = f"{brand} {label}"
            products.append((pid, brand, name, f"{hi} {label}", label, pack, unit, cat, mrp, emoji))
            for a in base_aliases:
                aliases.append((pid, a, "en"))
            aliases.append((pid, name.lower(), "en"))
            aliases.append((pid, hi, "hi"))
    name_to_id = {p[2]: p[0] for p in products}
    for en, hi, brands in GENERIC_ALIASES:
        ids = [name_to_id[n] for n in name_to_id if any(n.startswith(b) for b in brands)]
        for pid in ids:
            aliases.append((pid, en, "en"))
            aliases.append((pid, hi, "hi"))
        generic_ids[en] = ids
    return products, aliases, generic_ids


def _demo_trio(conn, product_ids):
    """Crafted scenario: only the 3-cycle A→C→B→A covers all confirmed needs."""
    def lot(shop, name, qty, days=None, slow=0, floor=2):
        pid = product_ids[name]
        mrp = next(p[8] for p in _CATALOG_CACHE if p[2] == name)
        expiry = (TODAY + timedelta(days=days)).isoformat() if days else None
        conn.execute(
            "INSERT INTO stock_lots(shop_id, product_id, qty, cost_paise, expiry_date, condition,"
            " permit_share, slow, retained_floor, version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,'sealed',1,?,?,1,?,?)",
            (shop, pid, qty, int(mrp * 0.88), expiry, slow, floor, db.now_iso(), db.now_iso()))

    def need(shop, name, qty, urgency="normal"):
        pid = product_ids[name]
        conn.execute(
            "INSERT INTO needs(shop_id, product_id, qty, urgency, alt_product_ids, budget_paise,"
            " min_shelf_days, status, created_at) VALUES (?,?,?,?,'[]',NULL,14,'open',?)",
            (shop, pid, qty, urgency, db.now_iso()))

    lot(1, "Parle-G 100g", 20, slow=1)
    lot(1, "Marie Gold 100g", 8, days=10, slow=1)          # near-expiry action demo
    lot(1, "Tata Salt 1kg", 24)
    lot(1, "Maggi 70g", 30)
    lot(1, "Tata Tea 250g", 12)
    lot(2, "Surf Excel 500g", 15, slow=1)
    lot(2, "Vim Bar 200g", 25)
    lot(2, "Ghadi Detergent 1kg", 18)
    lot(2, "Lifebuoy 100g", 20)
    lot(3, "Colgate Strong Teeth 100g", 20, slow=1)
    lot(3, "Dabur Honey 250g", 9)
    lot(3, "MDH Garam Masala 100g", 14)
    lot(3, "Madhur Sugar 1kg", 30)
    need(1, "Surf Excel 500g", 15, "urgent")
    need(2, "Colgate Strong Teeth 100g", 20, "urgent")
    need(3, "Parle-G 100g", 20, "urgent")


_CATALOG_CACHE = None


def seed(db_path=None, force=False) -> bool:
    global _CATALOG_CACHE
    db.init_db(db_path)
    conn = db.connect(db_path)
    try:
        if not force and conn.execute("SELECT COUNT(*) c FROM shops").fetchone()["c"] > 0:
            return False
        products, aliases, generic_ids = _catalog_rows()
        _CATALOG_CACHE = products
        rng = random.Random(42)
        base_lat, base_lng = 26.8750, 75.7900

        with db.tx(conn):
            conn.execute("DELETE FROM audit_events"); conn.execute("DELETE FROM inventory_log")
            conn.execute("DELETE FROM sessions"); conn.execute("DELETE FROM idempotency")
            conn.execute("DELETE FROM sandbox_actions"); conn.execute("DELETE FROM approvals")
            conn.execute("DELETE FROM reservations"); conn.execute("DELETE FROM cash_reservations"); conn.execute("DELETE FROM plans")
            conn.execute("DELETE FROM planning_runs"); conn.execute("DELETE FROM captures")
            conn.execute("DELETE FROM supplier_quotes"); conn.execute("DELETE FROM needs")
            conn.execute("DELETE FROM stock_lots"); conn.execute("DELETE FROM aliases")
            conn.execute("DELETE FROM products"); conn.execute("DELETE FROM shops")

            for i, (name, hi, owner) in enumerate(SHOPS, start=1):
                conn.execute(
                    "INSERT INTO shops(id, name, name_hi, owner_name, lat, lng, cash_limit_paise,"
                    " sharing_opt_in, version) VALUES (?,?,?,?,?,?,?,?,1)",
                    (i, name, hi, owner,
                     base_lat + rng.uniform(-0.018, 0.018), base_lng + rng.uniform(-0.018, 0.018),
                     rng.randrange(15, 45) * 10000, 1 if rng.random() < 0.85 else 0))
            # shops 1-3 sit close together so the demo cluster is walkable
            for sid, (dlat, dlng) in {1: (0.000, 0.000), 2: (0.004, 0.003), 3: (-0.003, 0.005)}.items():
                conn.execute("UPDATE shops SET lat=?, lng=?, sharing_opt_in=1 WHERE id=?",
                             (base_lat + dlat, base_lng + dlng, sid))

            for row in products:
                conn.execute(
                    "INSERT INTO products(id, brand, name, name_hi, variant, pack_size, unit,"
                    " category, mrp_paise, emoji) VALUES (?,?,?,?,?,?,?,?,?,?)", row)
            for pid, text, lang in aliases:
                conn.execute("INSERT INTO aliases(product_id, alias_text, lang) VALUES (?,?,?)",
                             (pid, text, lang))

            product_ids = {p[2]: p[0] for p in products}
            _demo_trio(conn, product_ids)
            # Explicit fictional date observations for the hero exchange lots.
            conn.execute("UPDATE stock_lots SET expiry_date=? WHERE shop_id IN (1,2,3)",
                         ((date.today() + timedelta(days=90)).isoformat(),))


            names = [p[2] for p in products]
            for shop in range(4, 26):
                for _ in range(rng.randrange(3, 8)):
                    name = rng.choice(names)
                    mrp = next(p[8] for p in products if p[2] == name)
                    days = rng.choice([None, None, None, 8, 12, 20, 120, 240])
                    expiry = (TODAY + timedelta(days=days)).isoformat() if days else None
                    conn.execute(
                        "INSERT INTO stock_lots(shop_id, product_id, qty, cost_paise, expiry_date,"
                        " condition, permit_share, slow, retained_floor, version, created_at, updated_at)"
                        " VALUES (?,?,?,?,?,'sealed',?,?,?,?,?,?)",
                        (shop, product_ids[name], rng.randrange(4, 40), int(mrp * rng.uniform(0.84, 0.93)),
                         expiry, 1 if rng.random() < 0.7 else 0, 1 if rng.random() < 0.25 else 0,
                         rng.randrange(0, 4), 1, db.now_iso(), db.now_iso()))
                for _ in range(rng.randrange(1, 4)):
                    name = rng.choice(names)
                    conn.execute(
                        "INSERT INTO needs(shop_id, product_id, qty, urgency, alt_product_ids,"
                        " budget_paise, min_shelf_days, status, created_at) VALUES (?,?,?,?, '[]', NULL, 14, 'open', ?)",
                        (shop, product_ids[name], rng.randrange(4, 20),
                         "urgent" if rng.random() < 0.3 else "normal", db.now_iso()))

            for p in products:
                conn.execute(
                    "INSERT INTO supplier_quotes(product_id, supplier_name, price_paise,"
                    " min_order_packs, lead_days) VALUES (?,?,?,?,?)",
                    (p[0], "Gupta Distributors" if rng.random() < 0.5 else "Shree Balaji Agencies",
                     int(p[8] * rng.uniform(0.86, 0.95)), 1, rng.choice([1, 2])))

            db.log_event(conn, "system", "seed.completed", payload={
                "shops": 25, "products": len(products), "aliases": len(aliases)})
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    print("seeded:", seed(force=True))
