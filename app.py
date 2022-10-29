import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    id = session.get("user_id")
    user_data = db.execute("SELECT * FROM users WHERE id = ?", id)
    cash = float(user_data[0]["cash"])
    stocks = db.execute(
        "SELECT symbol, SUM(units) AS shares, value FROM current_stocks WHERE user_id = ? AND units > 0 GROUP BY symbol", id)
    stock_value = db.execute(
        "SELECT SUM(value) AS final_value FROM current_stocks WHERE user_id = ? AND units > 0 GROUP BY user_id", id)

    print(id)
    for row in stocks:
        row['price'] = lookup(row['symbol'])['price']

    if len(stock_value) < 1:
        value = 0
    else:
        value = stock_value[0]["final_value"]

    return render_template("index.html", cash=cash, stocks=stocks, value=value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        id = session.get("user_id")

        # check which stocks user already owns
        symbols = db.execute("SELECT symbol FROM current_stocks WHERE user_id = ?", id)
        AVAILABLE_STOCKS = []
        i = 0
        while i < len(symbols):
            available_symbols = symbols[i]["symbol"]
            i += 1
            AVAILABLE_STOCKS.append(available_symbols)
        print(AVAILABLE_STOCKS)

        # check user enters a symbol
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Please enter the stock you wish to buy", 403)
        # convert stock to uppercase if valid
        else:
            symbol = symbol.upper()

        shares = int(request.form.get("shares"))
        stock_data = lookup(symbol)
        user_data = db.execute("SELECT cash FROM users WHERE id = ?", id)
        cash = user_data[0]["cash"]
        share = db.execute(
            "SELECT SUM(units) as units FROM current_stocks WHERE user_id = ? AND symbol = ?", id, symbol)
        # check if user currently owns shares of stock
        cur_shares = share[0]["units"]
        if cur_shares is None:
            current_shares = 0
        else:
            current_shares = cur_shares
        new_shares = int(current_shares) + int(shares)

        # check stock is valid
        if stock_data is None:
            cost = 0
            stock_price = 0
            return apology("Stock not found")
        else:
            cost = shares * stock_data["price"]
            stock_price = stock_data["price"]

        # check how much stock user will have available after purchase
        updated_cash = float(cash) - float(cost)
        share_value = float(stock_price * new_shares)

        # error check
        if not shares:
            return apology("Must enter a number of shares")
        if shares < 1:
            return apology("Must enter a positive number of shares")
        if cash < cost:
            return apology("You do not have enough cash for this purchase")

        # if user already owns some of stock update the number of shares they own and current value and if not insert stock into db
        if symbol in AVAILABLE_STOCKS:
            db.execute("UPDATE current_stocks SET price = ?, units = ?, value = ? WHERE user_id = ? AND symbol = ?",
                       stock_price, new_shares, share_value, id, symbol)

        else:
            db.execute("INSERT INTO current_stocks (user_id, symbol, price, units, value) VALUES(?, ?, ?, ?, ?)",
                       id, symbol, stock_price, shares, cost)

        db.execute("INSERT INTO purchases(user_id, symbol, price, units, cost, status) VALUES(?, ?, ?, ?, ?, ?)",
                   id, symbol, stock_price, shares, cost, "bought")
        db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, id)
        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    id = session.get("user_id")
    stocks = db.execute("SELECT symbol, units, price, cost, status, time FROM purchases WHERE user_id = ?", id)

    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock_data = lookup(symbol)
        # check for valid stock, if valid then return the price
        if stock_data:
            return render_template("quoted.html", stock_data=stock_data)
        return apology("Stock not found")
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # ask the user for required info
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        password_hash = generate_password_hash(password)
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # error check
        if not username:
            return apology("Username Required", 403)
        if len(rows) == 1:
            return apology("Username already exists", 403)
        if not password:
            return apology("Password Required", 403)
        if len(password) < 8:
            return apology("Password must have at least 8 characters", 403)
        if not any(c.isdigit() for c in password):
            return apology("Password must contain numbers", 403)
        if not confirmation:
            return apology("Please re-enter password", 403)
        if not password == confirmation:
            return apology("Passwords do not match", 403)

        # if valid then update the user db
        db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", username, password_hash)

        # automatically login the user after they have registered
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        session["user_id"] = rows[0]["id"]
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    id = session.get("user_id")
    symbols = db.execute("SELECT symbol FROM current_stocks WHERE user_id = ?", id)
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        stock_data = lookup(symbol)
        sell_price = shares * stock_data["price"]
        user_data = db.execute("SELECT cash FROM users WHERE id = ?", id)
        cash = user_data[0]["cash"]
        updated_cash = float(cash) + float(sell_price)

        # check the number of shares user currently owns of a stock
        share = db.execute("SELECT SUM(units) as units FROM current_stocks WHERE user_id = ? AND symbol = ?", id, symbol)
        cur_shares = share[0]["units"]
        if cur_shares is None:
            current_shares = 0
        else:
            current_shares = cur_shares
        new_shares = int(current_shares) - int(shares)
        share_value = float(stock_data["price"] * new_shares)

        # check current available stocks the user has
        AVAILABLE_STOCKS = []
        i = 0
        while i < len(symbols):
            available_symbols = symbols[i]["symbol"]
            i += 1
            AVAILABLE_STOCKS.append(available_symbols)
        print(AVAILABLE_STOCKS)

        # error check
        if not symbol:
            return apology("Please enter the stock you wish to sell")
        if symbol not in AVAILABLE_STOCKS:
            return apology("Invalid stock")
        if stock_data is None:
            return apology("Stock not found")
        if not shares:
            return apology("Must enter number of shares")
        if shares < 1:
            return apology("Must enter a positive number of shares")
        if shares > current_shares:
            return apology("You do not have enough shares available to sell")
        # if valid update the relevant databases
        db.execute("INSERT INTO purchases(user_id, symbol, price, units, cost, status) VALUES(?, ?, ?, ?, ?, ?)",
                   id, symbol, stock_data["price"], shares, sell_price, "sold")
        db.execute("UPDATE current_stocks SET price = ?, units = ?, value = ? WHERE user_id = ? AND symbol = ?",
                   stock_data["price"], new_shares, share_value, id, symbol)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, id)
        return redirect("/")

    return render_template("sell.html", symbols=symbols)