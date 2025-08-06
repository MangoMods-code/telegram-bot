from dotenv import load_dotenv
from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.ext import CallbackQueryHandler
from collections import defaultdict, Counter
import shutil
import json
from pathlib import Path
load_dotenv()
import os
from datetime import datetime


API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
if not API_TOKEN:
    raise SystemExit("❌ TELEGRAM_API_TOKEN not set. Check your .env file.")
CART_FILE = "cart_data.json"
ORDERS_FILE = "orders_data.json"
ADMINS = ["6407125860"]
PAYPAL_USERNAME = os.getenv("PAYPAL_USERNAME")
DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN")

def load_data():
    global user_cart, user_orders
    user_cart = json.loads(Path(CART_FILE).read_text()) if Path(CART_FILE).exists() else {}
    user_orders = json.loads(Path(ORDERS_FILE).read_text()) if Path(ORDERS_FILE).exists() else {}


PRODUCTS_FILE = "products.json"
products = load_products()

def load_products():
    if Path(PRODUCTS_FILE).exists():
        with open(PRODUCTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_products():
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=2)

products = load_products()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Official Mango Bot!\n"
        "/start - Welcome Message\n"
        "/list - Browse Products\n"
        "/cart - View Your Cart\n"
        "/help - List Commands\n"
        "/checkout - Checkout what you have in your cart!\n"
        "/orders - View Your Past Orders\n"
        "/categories - Browse by category\n"
        "/search <keyword> - Search products\n"
        "/stats - Admin stats (orders, revenue, top product)\n"

    )

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for product in products:
        caption = (
            f"<b>{product['name']}</b>\n"
            f"<i>{product['description']}</i>\n\n"
            f"<b>Price:</b><b>${product['price']}</b>"
        )

        keyboard = [
            [InlineKeyboardButton("Add To Cart", callback_data=f"buy_{product['id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_photo(
            photo=open(product["image"], "rb"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        
user_cart = {}

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    product_id = int(query.data.split("_")[1])
    product = next((p for p in products if p["id"] == product_id), None)

    if product:
        user_cart.setdefault(str(user_id), []).append(product)
        await query.answer()
        await query.edit_message_caption(
            caption=f"✅ {product['name']} added to your cart! 🛒"
        )
        save_cart()

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cart = user_cart.get(str(user_id), [])

    if not cart:
        await update.message.reply_text("Your cart is empty.")
        return

    message = "🛒 <b>Your Cart:</b>\n\n"
    total = 0
    for item in cart:
        message += f"• {item['name']} - ${item['price']}\n"
        total += item['price']
    message += f"\n<b>Total:</b> ${total:.2f}"

    await update.message.reply_text(message, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Welcome Message\n"
        "/list - Browse Products\n"
        "/cart - View Your Cart\n"
        "/help - List Commands\n"
        "/checkout - Checkout Your Cart!\n"
        "/orders - View Your Past Orders\n"
        "/categories - Browse by category\n"
        "/search <keyword> - Search products\n"
        "/stats - Admin stats (orders, revenue, top product)\n"

    )

async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cart = user_cart.get(str(user_id), [])

    if not cart:
        await update.message.reply_text("Your cart is empty.")
        return

    total = sum(item["price"] for item in cart)
    message = f"🧾 <b>Checkout Summary:</b>\n\n"
    for item in cart:
        message += f"• {item['name']} - ${item['price']}\n"
    message += f"\n<b>Total:</b> ${total:.2f}\n\n"
    message += "Do you want to confirm your purchase?"

    keyboard = [[InlineKeyboardButton("✅ Confirm", callback_data="confirm_checkout")]]
    await update.message.reply_text(message, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cart = user_cart.get(str(user_id), [])

    if not cart:
        await query.message.reply_text("Your cart is empty.")
        return

    total_amount = sum(item["price"] for item in cart)
    user_orders.setdefault(str(user_id), []).append(cart.copy())
    user_cart[str(user_id)] = []
    save_cart()
    save_orders()
    log_purchase(user_id, cart)
    backup_files()

    await query.answer()

    paypal_link = f"https://paypal.me/{PAYPAL_USERNAME}/{total_amount}"
    await query.message.reply_text(
        f"💳 Please pay <b>${total_amount:.2f}</b> using the link below:\n"
        f"{paypal_link}\n\n"
        "📸 After payment, please send a screenshot or your PayPal email for manual verification.\n\n"
        "✅ Thank you for your purchase!",
        parse_mode="HTML"
    )



async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    orders = user_orders.get(str(user_id), [])

    cart = user_cart.get(str(user_id), [])
    if cart:
        user_orders.setdefault(str(user_id), []).append(cart.copy())
        user_cart[str(user_id)] = []
        save_cart()
        save_orders()

    if not orders:
        await update.message.reply_text("You have no completed purchases.")
        return

    message = "📦 <b>Your Orders:</b>\n"
    for i, order in enumerate(orders, 1):
        items = ", ".join(p["name"] for p in order)
        total = sum(p["price"] for p in order)
        message += f"\nOrder {i}: {items} | Total: ${total:.2f}"
    
    await update.message.reply_text(message, parse_mode="HTML")

async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to add products.")
        return

    args = context.args
    if len(args) < 5:
        await update.message.reply_text(
            "Usage:\n/addproduct <name> <price> <description> <image_url> <category>"
        )
        return

    name = args[0]
    try:
        price = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid price format.")
        return

    description = args[2]
    image_url = args[3]
    category = args[4]

    product_id = max([p["id"] for p in products], default=0) + 1
    new_product = {
        "id": product_id,
        "name": name,
        "description": description,
        "price": price,
        "image": image_url,
        "category": category,
    }
    products.append(new_product)
    save_products()
    await update.message.reply_text(f"✅ Product '{name}' added successfully!")


async def remove_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to remove products.")
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/removeproduct <product_id>")
        return

    try:
        product_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid product ID.")
        return

    for i, p in enumerate(products):
        if p["id"] == product_id:
            del products[i]
            save_products()
            await update.message.reply_text(f"✅ Product ID {product_id} removed.")
            return

    await update.message.reply_text(f"❌ Product ID {product_id} not found.")

async def list_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = sorted(set(p.get("category", "Uncategorized") for p in products))
    if not categories:
        await update.message.reply_text("No categories available.")
        return

    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in categories]
    await update.message.reply_text("Select a category:", reply_markup=InlineKeyboardMarkup(keyboard))

async def category_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    filtered = [p for p in products if p.get("category") == category]

    if not filtered:
        await query.edit_message_text(f"No products found in category: {category}")
        return

    for product in filtered:
        keyboard = [
            [InlineKeyboardButton("🛒 Add to Cart", callback_data=f"buy_{product['id']}")]
        ]
        await query.message.reply_photo(
            photo=product["image"],
            caption=f"<b>{product['name']}</b>\n\n{product['description']}\n\n💵 ${product['price']}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def search_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /search <keyword>")
        return

    keyword = " ".join(context.args).lower()
    matches = [p for p in products if keyword in p["name"].lower() or keyword in p["description"].lower()]

    if not matches:
        await update.message.reply_text("No matching products found.")
        return

    for product in matches:
        keyboard = [
            [InlineKeyboardButton("🛒 Add to Cart", callback_data=f"buy_{product['id']}")]
        ]
        await update.message.reply_photo(
            photo=product["image"],
            caption=f"<b>{product['name']}</b>\n\n{product['description']}\n\n💵 ${product['price']}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to view stats.")
        return

    total_users = len(user_orders)
    total_orders = 0
    total_revenue = 0.0
    product_counter = Counter()

    for user_id, orders in user_orders.items():
        for order in orders:
            total_orders += 1
            for item in order:
                total_revenue += item["price"]
                product_counter[item["name"]] += 1

    if product_counter:
        top_product, top_count = product_counter.most_common(1)[0]
        top_text = f"{top_product} ({top_count} orders)"
    else:
        top_text = "None"

    await update.message.reply_text(
        f"📊 <b>Usage Stats:</b>\n"
        f"👥 Users: <b>{total_users}</b>\n"
        f"🛒 Orders: <b>{total_orders}</b>\n"
        f"💰 Revenue: <b>${total_revenue:.2f}</b>\n"
        f"🔥 Top Product: <b>{top_text}</b>",
        parse_mode="HTML"
    )

    


def save_cart():
    with open(CART_FILE, "w") as f:
        json.dump(user_cart, f)

def save_orders():
    with open(ORDERS_FILE, "w") as f:
        json.dump(user_orders, f)

def log_purchase(user_id, cart):
    with open("purchase.log", "a") as f:
        f.write(f"User {user_id} - Order:\n")
        for item in cart:
            f.write(f"  - {item['name']} (${item['price']})\n")
        f.write("\n")

def load_products():
    if Path(PRODUCTS_FILE).exists():
        try:
            with open(PRODUCTS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("❌ Error: products.json is corrupted.")
            return []
    return []

def backup_files():
    backup_dir = Path("backups") / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir.mkdir(parents=True, exist_ok=True)

    for filename in ["orders_data.json", "cart_data.json", "products.json", "purchase.log"]:
        source = Path(filename)
        if source.exists():
            shutil.copy(source, backup_dir / source.name)



user_cart = {}
user_orders = {}
load_data()

def main():
    app = ApplicationBuilder().token(API_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(CommandHandler("cart", view_cart))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("checkout", checkout))
    app.add_handler(CallbackQueryHandler(confirm_checkout, pattern="^confirm_checkout$"))
    app.add_handler(CommandHandler("orders", view_orders))
    app.add_handler(CommandHandler("addproduct", add_product))
    app.add_handler(CommandHandler("removeproduct", remove_product))
    app.add_handler(CommandHandler("categories", list_categories))
    app.add_handler(CommandHandler("search", search_products))
    app.add_handler(CallbackQueryHandler(category_filter, pattern=r"^cat_"))
    app.add_handler(CommandHandler("stats", show_stats))




    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
