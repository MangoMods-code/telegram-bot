import os
import json
import shutil
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from collections import Counter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# ----------------- Load Environment -----------------
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
PAYPAL_USERNAME = os.getenv("PAYPAL_USERNAME")
ADMINS = ["6407125860"]

# ----------------- File Paths -----------------
PRODUCTS_FILE = "products.json"
CART_FILE = "cart_data.json"
ORDERS_FILE = "orders_data.json"
LOG_FILE = "purchase.log"

# ----------------- In-Memory Data -----------------
products = []
user_cart = {}
user_orders = {}

# ----------------- File Operations -----------------
def load_products():
    if Path(PRODUCTS_FILE).exists():
        try:
            with open(PRODUCTS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("❌ Error loading products.json")
    return []

def save_products():
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=2)

def load_data():
    global user_cart, user_orders
    user_cart = json.loads(Path(CART_FILE).read_text()) if Path(CART_FILE).exists() else {}
    user_orders = json.loads(Path(ORDERS_FILE).read_text()) if Path(ORDERS_FILE).exists() else {}

def save_cart():
    with open(CART_FILE, "w") as f:
        json.dump(user_cart, f)

def save_orders():
    with open(ORDERS_FILE, "w") as f:
        json.dump(user_orders, f)

def log_purchase(user_id, cart):
    with open(LOG_FILE, "a") as f:
        f.write(f"User {user_id} - Order:\n")
        for item in cart:
            f.write(f"  - {item['name']} (${item['price']})\n")
        f.write("\n")

def backup_files():
    backup_dir = Path("backups") / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    for file in [ORDERS_FILE, CART_FILE, PRODUCTS_FILE, LOG_FILE]:
        if Path(file).exists():
            shutil.copy(file, backup_dir / file)

# ----------------- User Commands -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /list to view products.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/list - List products\n"
        "/cart - View cart\n"
        "/checkout - Checkout\n"
        "/orders - View your orders\n"
        "/addproduct - (Admin) Add product\n"
        "/removeproduct - (Admin) Remove product\n"
        "/categories - Browse by category\n"
        "/search <keyword> - Search products\n"
        "/stats - Show bot stats (admin)"
    )

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not products:
        await update.message.reply_text("No products available.")
        return

    for product in products:
        keyboard = [[InlineKeyboardButton("Add to Cart", callback_data=f"add_{product['id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{product['name']}\n${product['price']}\n{product['description']}",
            reply_markup=reply_markup
        )

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cart = user_cart.get(user_id, [])
    if not cart:
        await update.message.reply_text("Your cart is empty.")
        return
    total = sum(item['price'] for item in cart)
    text = "\n".join([f"{item['name']} - ${item['price']}" for item in cart])
    text += f"\n\nTotal: ${total}"
    await update.message.reply_text(text)

async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cart = user_cart.get(user_id, [])
    if not cart:
        await update.message.reply_text("Your cart is empty.")
        return
    total = sum(item['price'] for item in cart)
    confirm_button = InlineKeyboardButton("Confirm Checkout", callback_data="confirm_checkout")
    reply_markup = InlineKeyboardMarkup([[confirm_button]])
    await update.message.reply_text(
        f"Total: ${total}\nClick below to confirm your order.",
        reply_markup=reply_markup
    )

async def confirm_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    cart = user_cart.get(user_id, [])
    if not cart:
        await query.edit_message_text("Your cart is empty.")
        return

    user_orders.setdefault(user_id, []).extend(cart)
    log_purchase(user_id, cart)
    backup_files()

    await query.edit_message_text("✅ Checkout complete! Thank you.")
    user_cart[user_id] = []
    save_cart()
    save_orders()

async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    orders = user_orders.get(user_id, [])
    if not orders:
        await update.message.reply_text("You have no past orders.")
        return
    text = "\n".join([f"{item['name']} - ${item['price']}" for item in orders])
    await update.message.reply_text(f"Your Orders:\n{text}")

# ----------------- Admin Commands -----------------
async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in ADMINS:
        await update.message.reply_text("Access denied.")
        return
    try:
        name, price, description, category = " ".join(context.args).split(";")
        product = {
            "id": str(len(products) + 1),
            "name": name.strip(),
            "price": float(price.strip()),
            "description": description.strip(),
            "category": category.strip()
        }
        products.append(product)
        save_products()
        await update.message.reply_text(f"✅ Added: {name}")
    except:
        await update.message.reply_text("Usage: /addproduct Name ; Price ; Description ; Category")

async def remove_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in ADMINS:
        await update.message.reply_text("Access denied.")
        return
    try:
        product_id = context.args[0]
        global products
        products = [p for p in products if p['id'] != product_id]
        save_products()
        await update.message.reply_text(f"✅ Removed product ID {product_id}")
    except:
        await update.message.reply_text("Usage: /removeproduct <id>")

async def list_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = sorted(set(p['category'] for p in products))
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in categories]
    await update.message.reply_text("Select a category:", reply_markup=InlineKeyboardMarkup(keyboard))

async def category_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split("_", 1)[1]
    filtered = [p for p in products if p['category'] == cat]
    if not filtered:
        await query.edit_message_text(f"No products in {cat}.")
        return
    text = "\n".join([f"{p['name']} - ${p['price']}" for p in filtered])
    await query.edit_message_text(f"Products in {cat}:\n{text}")

async def search_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /search <keyword>")
        return
    keyword = " ".join(context.args).lower()
    results = [p for p in products if keyword in p['name'].lower()]
    if not results:
        await update.message.reply_text("No products found.")
        return
    text = "\n".join([f"{p['name']} - ${p['price']}" for p in results])
    await update.message.reply_text(f"Search results:\n{text}")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in ADMINS:
        await update.message.reply_text("Access denied.")
        return
    total_orders = sum(len(orders) for orders in user_orders.values())
    total_revenue = sum(p['price'] for orders in user_orders.values() for p in orders)
    top_users = Counter({uid: len(orders) for uid, orders in user_orders.items()}).most_common(3)
    text = (
        f"📊 Stats:\n"
        f"Users: {len(user_orders)}\n"
        f"Orders: {total_orders}\n"
        f"Revenue: ${total_revenue}\n"
        f"Top Users: {top_users}"
    )
    await update.message.reply_text(text)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    if query.data.startswith("add_"):
        pid = query.data.split("_", 1)[1]
        product = next((p for p in products if p["id"] == pid), None)
        if product:
            user_cart.setdefault(user_id, []).append(product)
            save_cart()
            await query.edit_message_text(f"✅ {product['name']} added to cart.")

# ----------------- Main Entry -----------------
if __name__ == "__main__":
    load_data()
    products = load_products()

    application = ApplicationBuilder().token(API_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("cart", view_cart))
    application.add_handler(CommandHandler("checkout", checkout))
    application.add_handler(CallbackQueryHandler(confirm_checkout, pattern="^confirm_checkout$"))
    application.add_handler(CommandHandler("orders", view_orders))
    application.add_handler(CommandHandler("addproduct", add_product))
    application.add_handler(CommandHandler("removeproduct", remove_product))
    application.add_handler(CommandHandler("categories", list_categories))
    application.add_handler(CallbackQueryHandler(category_filter, pattern="^cat_"))
    application.add_handler(CommandHandler("search", search_products))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CallbackQueryHandler(handle_callback))

    print("✅ Bot is running. Press Ctrl+C to stop.")
    application.run_polling()
