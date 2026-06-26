"""
Initialize the complex demo e-commerce SQLite database.

Creates 15 tables with realistic data:
  customers, categories, brands, products, suppliers, product_suppliers,
  warehouses, inventory, orders, order_items, payments, reviews,
  promotions, departments, employees

Includes self-referencing FKs, many-to-many relationships,
hierarchical data, and diverse data types.

Usage:
    python scripts/init_demo_db.py
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

# Seed for reproducibility
random.seed(42)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "demo_ecommerce.db")


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # Remove existing DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    create_tables(conn)
    seed_data(conn)

    conn.commit()
    conn.close()
    print(f"[OK] Demo database created at: {os.path.abspath(DB_PATH)}")
    print_stats()


# ══════════════════════════════════════════════════════════════════
# Schema Definition
# ══════════════════════════════════════════════════════════════════

def create_tables(conn):
    conn.executescript("""
    -- Departments for employees
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        budget REAL DEFAULT 0,
        location TEXT
    );

    -- Employees with self-referencing manager FK
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        department_id INTEGER REFERENCES departments(id),
        hire_date TEXT NOT NULL,
        salary REAL NOT NULL,
        manager_id INTEGER REFERENCES employees(id),
        is_active INTEGER DEFAULT 1
    );

    -- Customers
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        city TEXT,
        state TEXT,
        country TEXT NOT NULL,
        registration_date TEXT NOT NULL,
        customer_tier TEXT CHECK(customer_tier IN ('bronze', 'silver', 'gold', 'platinum')) DEFAULT 'bronze',
        is_active INTEGER DEFAULT 1
    );

    -- Categories with self-referencing parent (hierarchy)
    CREATE TABLE categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        parent_category_id INTEGER REFERENCES categories(id),
        description TEXT,
        is_active INTEGER DEFAULT 1
    );

    -- Brands
    CREATE TABLE brands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        country TEXT,
        founded_year INTEGER,
        website TEXT
    );

    -- Products
    CREATE TABLE products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        category_id INTEGER REFERENCES categories(id),
        brand_id INTEGER REFERENCES brands(id),
        price REAL NOT NULL CHECK(price > 0),
        cost_price REAL NOT NULL CHECK(cost_price > 0),
        weight_kg REAL,
        sku TEXT UNIQUE,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );

    -- Suppliers
    CREATE TABLE suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        contact_name TEXT,
        email TEXT,
        phone TEXT,
        country TEXT NOT NULL,
        rating REAL CHECK(rating BETWEEN 1 AND 5)
    );

    -- Product-Supplier many-to-many
    CREATE TABLE product_suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id),
        supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
        supply_price REAL NOT NULL,
        lead_time_days INTEGER DEFAULT 7,
        is_primary INTEGER DEFAULT 0,
        UNIQUE(product_id, supplier_id)
    );

    -- Warehouses
    CREATE TABLE warehouses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        city TEXT NOT NULL,
        country TEXT NOT NULL,
        capacity INTEGER NOT NULL,
        manager_id INTEGER REFERENCES employees(id)
    );

    -- Inventory
    CREATE TABLE inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id),
        warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
        quantity INTEGER NOT NULL DEFAULT 0,
        last_restocked TEXT,
        UNIQUE(product_id, warehouse_id)
    );

    -- Orders
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        order_date TEXT NOT NULL,
        status TEXT CHECK(status IN ('pending','processing','shipped','delivered','cancelled','returned')) DEFAULT 'pending',
        shipping_address TEXT,
        shipping_city TEXT,
        shipping_country TEXT,
        shipping_cost REAL DEFAULT 0,
        total_amount REAL NOT NULL,
        notes TEXT
    );

    -- Order Items
    CREATE TABLE order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        product_id INTEGER NOT NULL REFERENCES products(id),
        quantity INTEGER NOT NULL CHECK(quantity > 0),
        unit_price REAL NOT NULL,
        discount_percent REAL DEFAULT 0 CHECK(discount_percent BETWEEN 0 AND 100)
    );

    -- Payments
    CREATE TABLE payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        payment_method TEXT CHECK(payment_method IN ('credit_card','debit_card','paypal','bank_transfer','crypto')) NOT NULL,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        status TEXT CHECK(status IN ('pending','completed','failed','refunded')) DEFAULT 'pending',
        transaction_id TEXT UNIQUE
    );

    -- Reviews
    CREATE TABLE reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        title TEXT,
        comment TEXT,
        review_date TEXT NOT NULL,
        is_verified INTEGER DEFAULT 0
    );

    -- Promotions
    CREATE TABLE promotions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        description TEXT,
        discount_percent REAL NOT NULL CHECK(discount_percent BETWEEN 0 AND 100),
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        min_order_amount REAL DEFAULT 0,
        max_uses INTEGER,
        times_used INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    );

    -- Create indexes for common queries
    CREATE INDEX idx_orders_customer ON orders(customer_id);
    CREATE INDEX idx_orders_date ON orders(order_date);
    CREATE INDEX idx_orders_status ON orders(status);
    CREATE INDEX idx_order_items_order ON order_items(order_id);
    CREATE INDEX idx_order_items_product ON order_items(product_id);
    CREATE INDEX idx_products_category ON products(category_id);
    CREATE INDEX idx_products_brand ON products(brand_id);
    CREATE INDEX idx_reviews_product ON reviews(product_id);
    CREATE INDEX idx_inventory_product ON inventory(product_id);
    CREATE INDEX idx_payments_order ON payments(order_id);
    """)


# ══════════════════════════════════════════════════════════════════
# Data Seeding
# ══════════════════════════════════════════════════════════════════

# ── Reference Data ───────────────────────────────────────────────

FIRST_NAMES = [
    "James", "Emma", "Liam", "Olivia", "Noah", "Ava", "Sophia", "Mason",
    "Isabella", "Logan", "Mia", "Lucas", "Charlotte", "Ethan", "Amelia",
    "Aiden", "Harper", "Jackson", "Evelyn", "Sebastian", "Luna", "Mateo",
    "Ella", "Henry", "Scarlett", "Owen", "Grace", "Alexander", "Chloe",
    "Daniel", "Penelope", "William", "Layla", "Benjamin", "Riley",
    "Elijah", "Zoey", "Jayden", "Nora", "Carter", "Lily", "Dylan",
    "Eleanor", "Gabriel", "Hannah", "Julian", "Lillian", "Levi", "Addison",
    "Priya", "Raj", "Yuki", "Chen", "Fatima", "Omar", "Ingrid", "Lars",
    "Sofia", "Carlos", "Ana", "Pedro", "Mei", "Hiroshi", "Aisha", "Kwame",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas",
    "Hernandez", "Moore", "Martin", "Jackson", "Thompson", "White",
    "Lee", "Harris", "Clark", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
    "Kim", "Patel", "Chen", "Singh", "Kumar", "Tanaka", "Mueller",
    "Johansson", "Petrov", "Santos", "Ali", "O'Brien", "Schmidt",
]

CITIES_COUNTRIES = [
    ("New York", "New York", "USA"), ("Los Angeles", "California", "USA"),
    ("Chicago", "Illinois", "USA"), ("Houston", "Texas", "USA"),
    ("Phoenix", "Arizona", "USA"), ("San Francisco", "California", "USA"),
    ("Seattle", "Washington", "USA"), ("Boston", "Massachusetts", "USA"),
    ("Denver", "Colorado", "USA"), ("Austin", "Texas", "USA"),
    ("London", None, "UK"), ("Manchester", None, "UK"),
    ("Berlin", None, "Germany"), ("Munich", None, "Germany"),
    ("Paris", None, "France"), ("Lyon", None, "France"),
    ("Tokyo", None, "Japan"), ("Osaka", None, "Japan"),
    ("Toronto", "Ontario", "Canada"), ("Vancouver", "BC", "Canada"),
    ("Sydney", "NSW", "Australia"), ("Melbourne", "VIC", "Australia"),
    ("Mumbai", "Maharashtra", "India"), ("Bangalore", "Karnataka", "India"),
    ("São Paulo", None, "Brazil"), ("Dubai", None, "UAE"),
    ("Singapore", None, "Singapore"), ("Stockholm", None, "Sweden"),
    ("Amsterdam", None, "Netherlands"), ("Seoul", None, "South Korea"),
]

CATEGORIES_HIERARCHY = [
    # (name, parent_name, description)
    ("Electronics", None, "Electronic devices and accessories"),
    ("Smartphones", "Electronics", "Mobile phones and accessories"),
    ("Laptops", "Electronics", "Portable computers"),
    ("Audio", "Electronics", "Headphones, speakers, and audio equipment"),
    ("Wearables", "Electronics", "Smartwatches and fitness trackers"),
    ("Clothing", None, "Apparel and fashion items"),
    ("Men's Clothing", "Clothing", "Men's apparel"),
    ("Women's Clothing", "Clothing", "Women's apparel"),
    ("Shoes", "Clothing", "Footwear for all genders"),
    ("Home & Kitchen", None, "Home goods and kitchen appliances"),
    ("Furniture", "Home & Kitchen", "Tables, chairs, and storage"),
    ("Kitchen Appliances", "Home & Kitchen", "Cooking and food prep equipment"),
    ("Decor", "Home & Kitchen", "Home decoration items"),
    ("Sports & Outdoors", None, "Sports equipment and outdoor gear"),
    ("Fitness", "Sports & Outdoors", "Gym and fitness equipment"),
    ("Camping", "Sports & Outdoors", "Camping and hiking gear"),
    ("Books", None, "Physical and digital books"),
    ("Fiction", "Books", "Novels and short stories"),
    ("Non-Fiction", "Books", "Educational and informational books"),
    ("Beauty & Health", None, "Personal care and health products"),
]

BRANDS = [
    ("TechNova", "USA", 2015, "https://technova.example.com"),
    ("ElectroPeak", "Japan", 2010, "https://electropeak.example.com"),
    ("UrbanStyle", "Italy", 2008, "https://urbanstyle.example.com"),
    ("NatureFit", "Germany", 2012, "https://naturefit.example.com"),
    ("HomeEssence", "Sweden", 2005, "https://homeessence.example.com"),
    ("SoundWave", "USA", 2018, "https://soundwave.example.com"),
    ("ActivePro", "UK", 2014, "https://activepro.example.com"),
    ("GreenLeaf", "Canada", 2019, "https://greenleaf.example.com"),
    ("LuxCraft", "France", 2001, "https://luxcraft.example.com"),
    ("DigitalEdge", "South Korea", 2016, "https://digitaledge.example.com"),
    ("PureAura", "Australia", 2017, "https://pureaura.example.com"),
    ("SwiftGear", "USA", 2020, "https://swiftgear.example.com"),
    ("CozyNest", "Denmark", 2013, "https://cozynest.example.com"),
    ("PageTurner", "UK", 2003, "https://pageturner.example.com"),
    ("VitalCore", "India", 2021, "https://vitalcore.example.com"),
]

PRODUCT_TEMPLATES = [
    # (name_template, category, price_range, cost_multiplier, weight_range)
    ("Pro Smartphone X{n}", "Smartphones", (299, 1299), 0.5, (0.15, 0.22)),
    ("UltraBook Pro {n}", "Laptops", (599, 2499), 0.55, (1.2, 2.5)),
    ("Wireless Earbuds {n}", "Audio", (29, 299), 0.4, (0.05, 0.08)),
    ("Smart Watch Series {n}", "Wearables", (99, 599), 0.45, (0.04, 0.08)),
    ("Noise-Cancel Headphones {n}", "Audio", (79, 449), 0.4, (0.2, 0.35)),
    ("Bluetooth Speaker {n}", "Audio", (19, 199), 0.4, (0.3, 1.5)),
    ("Men's Premium T-Shirt {n}", "Men's Clothing", (15, 89), 0.35, (0.15, 0.3)),
    ("Women's Summer Dress {n}", "Women's Clothing", (25, 199), 0.3, (0.2, 0.4)),
    ("Running Shoes Model {n}", "Shoes", (49, 249), 0.4, (0.3, 0.5)),
    ("Ergonomic Office Chair {n}", "Furniture", (149, 899), 0.45, (8, 18)),
    ("Smart Blender Pro {n}", "Kitchen Appliances", (39, 299), 0.4, (1.5, 4)),
    ("Minimalist Wall Art {n}", "Decor", (15, 149), 0.3, (0.3, 2)),
    ("Yoga Mat Premium {n}", "Fitness", (19, 99), 0.35, (1, 2.5)),
    ("Camping Tent {n}-Person", "Camping", (49, 499), 0.45, (2, 8)),
    ("Bestseller Novel Vol.{n}", "Fiction", (8, 29), 0.3, (0.2, 0.5)),
    ("Science Handbook Ed.{n}", "Non-Fiction", (12, 59), 0.35, (0.3, 0.8)),
    ("Organic Face Cream {n}ml", "Beauty & Health", (9, 79), 0.25, (0.05, 0.3)),
    ("Gaming Laptop Elite {n}", "Laptops", (999, 3499), 0.5, (2, 3.5)),
    ("Portable Charger {n}mAh", "Electronics", (15, 79), 0.35, (0.1, 0.4)),
    ("Standing Desk Adjustable {n}", "Furniture", (199, 799), 0.5, (15, 35)),
]

SUPPLIER_NAMES = [
    ("Global Supply Co.", "Li Wei", "China"),
    ("EuroParts GmbH", "Hans Mueller", "Germany"),
    ("Pacific Trading Ltd.", "Sakura Tanaka", "Japan"),
    ("AmeriSource Inc.", "John Baker", "USA"),
    ("IndiaFab Solutions", "Arjun Patel", "India"),
    ("Nordic Logistics AB", "Erik Johansson", "Sweden"),
    ("MexiTrade SA", "Maria Lopez", "Mexico"),
    ("AussieParts Pty", "Sarah Wilson", "Australia"),
    ("UK Wholesale Ltd.", "James Brown", "UK"),
    ("KoreaTech Corp.", "Min-Jun Park", "South Korea"),
    ("BrazilExport Ltda.", "Pedro Santos", "Brazil"),
    ("CanadianGoods Inc.", "Emily Chen", "Canada"),
    ("FrenchQuality SAS", "Pierre Dubois", "France"),
    ("ItalyDirect Srl", "Marco Rossi", "Italy"),
    ("DutchTrade BV", "Anna de Vries", "Netherlands"),
]

PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "bank_transfer", "crypto"]
ORDER_STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled", "returned"]

REVIEW_TITLES = [
    "Great product!", "Exceeded expectations", "Good value for money",
    "Decent quality", "Not bad", "Could be better", "Disappointed",
    "Amazing!", "Perfect for my needs", "Highly recommend",
    "Solid build quality", "Fast shipping", "Love it!",
    "Okay for the price", "Would buy again",
]

REVIEW_COMMENTS = [
    "Really happy with this purchase. Works exactly as described.",
    "The quality is outstanding for the price point. Very impressed.",
    "Arrived quickly and was well-packaged. No complaints.",
    "Does the job but nothing spectacular. Average product.",
    "Had some issues initially but customer service was helpful.",
    "Better than expected! Will definitely recommend to friends.",
    "Not quite what I was looking for. Returning it.",
    "Absolutely love it! Best purchase I've made this year.",
    "Good product overall, minor issues with the finish.",
    "Perfect gift idea. The recipient was thrilled!",
    "Build quality could be improved, but functionality is great.",
    "Fast delivery, product matches the description perfectly.",
    "A bit overpriced for what you get, but still decent.",
    "Excellent value. Comparable to much more expensive alternatives.",
    "Sturdy and well-made. Using it daily without any problems.",
]

PROMO_CODES = [
    ("WELCOME10", "New customer welcome discount", 10, 0),
    ("SUMMER25", "Summer sale - 25% off", 25, 50),
    ("FLASH15", "Flash sale - 15% off everything", 15, 30),
    ("VIP30", "VIP customer exclusive - 30% off", 30, 100),
    ("FREESHIP", "Free shipping on orders over $75", 5, 75),
    ("HOLIDAY20", "Holiday season special", 20, 40),
    ("LOYALTY15", "Loyalty program discount", 15, 25),
    ("BUNDLE10", "Bundle deal - extra 10% off", 10, 60),
    ("CLEARANCE40", "End of season clearance", 40, 20),
    ("BIRTHDAY25", "Birthday month special", 25, 0),
]

DEPARTMENTS = [
    ("Engineering", 500000, "San Francisco"),
    ("Sales", 300000, "New York"),
    ("Marketing", 250000, "Los Angeles"),
    ("Customer Support", 200000, "Austin"),
    ("Human Resources", 150000, "Chicago"),
]


def seed_data(conn):
    cur = conn.cursor()

    # ── 1. Departments ──
    for name, budget, location in DEPARTMENTS:
        cur.execute(
            "INSERT INTO departments (name, budget, location) VALUES (?, ?, ?)",
            (name, budget, location),
        )

    # ── 2. Employees (50) ──
    emp_ids = []
    for i in range(50):
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        email = f"{fn.lower()}.{ln.lower()}{i}@company.example.com"
        dept_id = random.randint(1, len(DEPARTMENTS))
        days_ago = random.randint(30, 2500)
        hire_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        salary = round(random.uniform(45000, 180000), 2)
        manager_id = random.choice(emp_ids) if emp_ids and random.random() > 0.15 else None

        cur.execute(
            "INSERT INTO employees (first_name, last_name, email, department_id, hire_date, salary, manager_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fn, ln, email, dept_id, hire_date, salary, manager_id),
        )
        emp_ids.append(cur.lastrowid)

    # ── 3. Customers (120) ──
    customer_ids = []
    tiers = ["bronze"] * 50 + ["silver"] * 30 + ["gold"] * 15 + ["platinum"] * 5
    random.shuffle(tiers)

    for i in range(120):
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        city, state, country = random.choice(CITIES_COUNTRIES)
        days_ago = random.randint(1, 1500)
        reg_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        tier = tiers[i % len(tiers)]

        cur.execute(
            "INSERT INTO customers (first_name, last_name, email, phone, city, state, country, registration_date, customer_tier) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fn, ln, f"{fn.lower()}.{ln.lower()}{i}@example.com",
             f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
             city, state, country, reg_date, tier),
        )
        customer_ids.append(cur.lastrowid)

    # ── 4. Categories ──
    cat_name_to_id = {}
    for name, parent_name, desc in CATEGORIES_HIERARCHY:
        parent_id = cat_name_to_id.get(parent_name)
        cur.execute(
            "INSERT INTO categories (name, parent_category_id, description) VALUES (?, ?, ?)",
            (name, parent_id, desc),
        )
        cat_name_to_id[name] = cur.lastrowid

    # ── 5. Brands ──
    brand_ids = []
    for name, country, year, website in BRANDS:
        cur.execute(
            "INSERT INTO brands (name, country, founded_year, website) VALUES (?, ?, ?, ?)",
            (name, country, year, website),
        )
        brand_ids.append(cur.lastrowid)

    # ── 6. Products (200) ──
    product_ids = []
    for i in range(200):
        template = random.choice(PRODUCT_TEMPLATES)
        name_tmpl, cat_name, (pmin, pmax), cost_mult, (wmin, wmax) = template
        name = name_tmpl.format(n=random.randint(1, 999))
        cat_id = cat_name_to_id.get(cat_name, 1)
        brand_id = random.choice(brand_ids)
        price = round(random.uniform(pmin, pmax), 2)
        cost = round(price * cost_mult, 2)
        weight = round(random.uniform(wmin, wmax), 2)
        sku = f"SKU-{i+1:05d}"
        days_ago = random.randint(1, 800)
        created = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        is_active = 1 if random.random() > 0.05 else 0

        cur.execute(
            "INSERT INTO products (name, description, category_id, brand_id, price, cost_price, weight_kg, sku, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, f"High-quality {name.lower()} with premium features.", cat_id, brand_id,
             price, cost, weight, sku, is_active, created),
        )
        product_ids.append(cur.lastrowid)

    # ── 7. Suppliers ──
    supplier_ids = []
    for company, contact, country in SUPPLIER_NAMES:
        rating = round(random.uniform(2.5, 5.0), 1)
        cur.execute(
            "INSERT INTO suppliers (company_name, contact_name, email, phone, country, rating) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (company, contact, f"contact@{company.lower().replace(' ', '').replace('.', '')}.com",
             f"+{random.randint(1,99)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
             country, rating),
        )
        supplier_ids.append(cur.lastrowid)

    # ── 8. Product-Supplier mappings ──
    for pid in product_ids:
        n_suppliers = random.randint(1, 3)
        chosen = random.sample(supplier_ids, min(n_suppliers, len(supplier_ids)))
        for j, sid in enumerate(chosen):
            supply_price = round(random.uniform(5, 500), 2)
            lead_days = random.choice([3, 5, 7, 10, 14, 21, 30])
            cur.execute(
                "INSERT OR IGNORE INTO product_suppliers (product_id, supplier_id, supply_price, lead_time_days, is_primary) "
                "VALUES (?, ?, ?, ?, ?)",
                (pid, sid, supply_price, lead_days, 1 if j == 0 else 0),
            )

    # ── 9. Warehouses ──
    warehouse_ids = []
    warehouses = [
        ("East Coast Hub", "New York", "USA"),
        ("West Coast Hub", "Los Angeles", "USA"),
        ("Central Europe DC", "Berlin", "Germany"),
        ("Asia Pacific DC", "Tokyo", "Japan"),
        ("UK Distribution Center", "London", "UK"),
    ]
    for i, (name, city, country) in enumerate(warehouses):
        mgr_id = random.choice(emp_ids)
        cur.execute(
            "INSERT INTO warehouses (name, city, country, capacity, manager_id) VALUES (?, ?, ?, ?, ?)",
            (name, city, country, random.randint(5000, 50000), mgr_id),
        )
        warehouse_ids.append(cur.lastrowid)

    # ── 10. Inventory ──
    for pid in product_ids:
        n_wh = random.randint(1, 3)
        chosen_wh = random.sample(warehouse_ids, min(n_wh, len(warehouse_ids)))
        for wid in chosen_wh:
            qty = random.randint(0, 500)
            days_ago = random.randint(1, 60)
            restocked = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            cur.execute(
                "INSERT OR IGNORE INTO inventory (product_id, warehouse_id, quantity, last_restocked) "
                "VALUES (?, ?, ?, ?)",
                (pid, wid, qty, restocked),
            )

    # ── 11. Orders (600) ──
    order_ids = []
    for i in range(600):
        cid = random.choice(customer_ids)
        days_ago = random.randint(0, 730)
        order_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        # Status weighted: more delivered than pending
        status_weights = [0.05, 0.08, 0.12, 0.55, 0.12, 0.08]
        status = random.choices(ORDER_STATUSES, weights=status_weights, k=1)[0]

        city, state_name, country = random.choice(CITIES_COUNTRIES)
        ship_cost = round(random.uniform(0, 25), 2)

        # Generate order items first to calculate total
        n_items = random.randint(1, 5)
        items_pids = random.sample(product_ids, min(n_items, len(product_ids)))
        item_rows = []
        total = ship_cost

        for pid in items_pids:
            qty = random.randint(1, 4)
            # Get product price
            cur.execute("SELECT price FROM products WHERE id = ?", (pid,))
            row = cur.fetchone()
            unit_price = row[0] if row else 29.99
            discount = random.choice([0, 0, 0, 5, 10, 15, 20])
            line_total = qty * unit_price * (1 - discount / 100)
            total += line_total
            item_rows.append((pid, qty, unit_price, discount))

        total = round(total, 2)

        cur.execute(
            "INSERT INTO orders (customer_id, order_date, status, shipping_address, shipping_city, shipping_country, shipping_cost, total_amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, order_date, status, f"{random.randint(1,999)} Main Street", city, country, ship_cost, total),
        )
        oid = cur.lastrowid
        order_ids.append(oid)

        # Insert order items
        for pid, qty, unit_price, discount in item_rows:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount_percent) "
                "VALUES (?, ?, ?, ?, ?)",
                (oid, pid, qty, unit_price, discount),
            )

    # ── 12. Payments ──
    for oid in order_ids:
        cur.execute("SELECT total_amount, status, order_date FROM orders WHERE id = ?", (oid,))
        row = cur.fetchone()
        if not row:
            continue
        amount, status, odate = row

        method = random.choice(PAYMENT_METHODS)

        if status in ("cancelled",):
            pay_status = "refunded"
        elif status in ("pending",):
            pay_status = random.choice(["pending", "completed"])
        elif status in ("returned",):
            pay_status = "refunded"
        else:
            pay_status = "completed"

        txn_id = f"TXN-{oid:06d}-{random.randint(1000,9999)}"

        cur.execute(
            "INSERT INTO payments (order_id, payment_method, amount, payment_date, status, transaction_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (oid, method, amount, odate, pay_status, txn_id),
        )

    # ── 13. Reviews (400) ──
    for i in range(400):
        pid = random.choice(product_ids)
        cid = random.choice(customer_ids)
        rating = random.choices([1, 2, 3, 4, 5], weights=[5, 8, 15, 35, 37], k=1)[0]
        title = random.choice(REVIEW_TITLES)
        comment = random.choice(REVIEW_COMMENTS)
        days_ago = random.randint(0, 600)
        rdate = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        verified = 1 if random.random() > 0.3 else 0

        cur.execute(
            "INSERT INTO reviews (product_id, customer_id, rating, title, comment, review_date, is_verified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pid, cid, rating, title, comment, rdate, verified),
        )

    # ── 14. Promotions ──
    base_date = datetime.now()
    for code, desc, discount, min_amount in PROMO_CODES:
        start_offset = random.randint(-180, 30)
        start = (base_date + timedelta(days=start_offset)).strftime("%Y-%m-%d")
        end = (base_date + timedelta(days=start_offset + random.randint(14, 90))).strftime("%Y-%m-%d")
        max_uses = random.choice([100, 200, 500, 1000, None])
        times_used = random.randint(0, max_uses or 500)
        is_active = 1 if start_offset <= 0 else 0

        cur.execute(
            "INSERT INTO promotions (code, description, discount_percent, start_date, end_date, min_order_amount, max_uses, times_used, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (code, desc, discount, start, end, min_amount, max_uses, times_used, is_active),
        )


def print_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f"\nDatabase Statistics:")
    print(f"{'Table':<25} {'Rows':>8}")
    print("-" * 35)
    for (table,) in tables:
        count = cur.execute(f"SELECT COUNT(*) FROM \"{table}\"").fetchone()[0]
        print(f"  {table:<23} {count:>8}")
    conn.close()


if __name__ == "__main__":
    main()
