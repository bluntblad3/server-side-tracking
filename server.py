from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from utils.gtm_server import GTMServerSide, track_pageview
from utils.config import GTM_CONFIG
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = '426415839e71b10a8c2cb9fbe55eaa9c'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize GTM Server-Side Tracking
gtm = GTMServerSide(
    gtm_server_url=GTM_CONFIG['server_url'],
    container_id=GTM_CONFIG['container_id'],
    api_secret=GTM_CONFIG.get('api_secret'),
    container_config=GTM_CONFIG.get('container_config')
)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(100), nullable=True)
    
class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    user = db.relationship('User', backref=db.backref('cart_items', lazy=True))
    product = db.relationship('Product')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_ordered = db.Column(db.DateTime, default=datetime.utcnow)
    complete = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref=db.backref('orders', lazy=True))
    
class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    order = db.relationship('Order', backref=db.backref('items', lazy=True))
    product = db.relationship('Product')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# GTM Server-Side Routes
@app.route('/collect', methods=['POST'])
def gtm_collect():
    """Endpoint for Google Tag Manager server-side data collection"""
    try:
        # Get the request data
        payload = request.get_json(silent=True) or {}
        
        # Log the event data for debugging
        app.logger.info(f"GTM Collect: {json.dumps(payload)}")
        
        # Return a success response (204 No Content is typical for tracking endpoints)
        return make_response('', 204)
    except Exception as e:
        app.logger.error(f"Error processing GTM data: {str(e)}")
        return make_response(jsonify({'error': str(e)}), 500)

@app.route('/gtm/debug', methods=['GET'])
def gtm_debug():
    """GTM Debug Interface"""
    # Get the query parameters
    gtm_id = request.args.get('id')
    gtm_auth = request.args.get('gtm_auth')
    gtm_preview = request.args.get('gtm_preview')
    
    # Log the debug request
    app.logger.info(f"GTM Debug accessed: ID={gtm_id}, Auth={gtm_auth}, Preview={gtm_preview}")
    
    # Get recent events of each type
    page_views = gtm.get_recent_events(event_type='page_view', limit=10)
    product_views = gtm.get_recent_events(event_type='view_item', limit=10)
    add_to_cart_events = gtm.get_recent_events(event_type='add_to_cart', limit=10)
    logouts = gtm.get_recent_events(event_type='user_logout', limit=10)
    all_events = gtm.get_recent_events(limit=20)
    
    debug_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>GTM Debug Interface</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; }}
            h1, h2, h3 {{ color: #333; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .info {{ background: #f4f4f4; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .param {{ margin-bottom: 10px; }}
            .key {{ font-weight: bold; }}
            .event {{ background: #fff; padding: 10px; margin: 10px 0; border-left: 3px solid #ccc; border-radius: 3px; }}
            .event-time {{ color: #666; font-size: 0.9em; }}
            .event-name {{ font-weight: bold; color: #2c3e50; }}
            .event-data {{ margin-top: 5px; font-family: monospace; white-space: pre-wrap; font-size: 0.8em; max-height: 100px; overflow-y: auto; }}
            .page-view {{ border-left-color: #3498db; }}
            .product-view {{ border-left-color: #2ecc71; }}
            .add-to-cart {{ border-left-color: #e74c3c; }}
            .user-logout {{ border-left-color: #f39c12; }}
            .tab {{ overflow: hidden; border: 1px solid #ccc; background-color: #f1f1f1; }}
            .tab button {{ background-color: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 14px 16px; transition: 0.3s; }}
            .tab button:hover {{ background-color: #ddd; }}
            .tab button.active {{ background-color: #ccc; }}
            .tabcontent {{ display: none; padding: 6px 12px; border: 1px solid #ccc; border-top: none; }}
            #AllEvents {{ display: block; }}
        </style>
        <script>
            function openEventTab(evt, tabName) {{
                var i, tabcontent, tablinks;
                tabcontent = document.getElementsByClassName("tabcontent");
                for (i = 0; i < tabcontent.length; i++) {{
                    tabcontent[i].style.display = "none";
                }}
                tablinks = document.getElementsByClassName("tablinks");
                for (i = 0; i < tablinks.length; i++) {{
                    tablinks[i].className = tablinks[i].className.replace(" active", "");
                }}
                document.getElementById(tabName).style.display = "block";
                evt.currentTarget.className += " active";
            }}
            
            // Auto-reload the page every 10 seconds
            setTimeout(function() {{
                location.reload();
            }}, 10000);
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Google Tag Manager Debug Interface</h1>
            <div class="info">
                <div class="param"><span class="key">Container ID:</span> {gtm_id or GTM_CONFIG['container_id']}</div>
                <div class="param"><span class="key">Auth:</span> {gtm_auth or 'Not provided'}</div>
                <div class="param"><span class="key">Preview Mode:</span> {gtm_preview or 'Not active'}</div>
            </div>
            
            <h2>Active Configuration</h2>
            <div class="info">
                <div class="param"><span class="key">Server URL:</span> {GTM_CONFIG['server_url']}</div>
                <div class="param"><span class="key">Container ID:</span> {GTM_CONFIG['container_id']}</div>
                <div class="param"><span class="key">API Secret Set:</span> {'Yes' if GTM_CONFIG.get('api_secret') else 'No'}</div>
                <div class="param"><span class="key">Container Config Available:</span> {'Yes' if GTM_CONFIG.get('container_config') else 'No'}</div>
            </div>
            
            <h2>Recent Events</h2>
            <div class="tab">
                <button class="tablinks active" onclick="openEventTab(event, 'AllEvents')">All Events ({len(all_events)})</button>
                <button class="tablinks" onclick="openEventTab(event, 'PageViews')">Page Views ({len(page_views)})</button>
                <button class="tablinks" onclick="openEventTab(event, 'ProductViews')">Product Views ({len(product_views)})</button>
                <button class="tablinks" onclick="openEventTab(event, 'AddToCart')">Add to Cart ({len(add_to_cart_events)})</button>
                <button class="tablinks" onclick="openEventTab(event, 'Logouts')">User Logouts ({len(logouts)})</button>
            </div>
            
            <div id="AllEvents" class="tabcontent">
                <h3>All Recent Events</h3>
                {''.join([f"""
                <div class="event {'page-view' if e['event_name'] == 'page_view' else 'product-view' if e['event_name'] == 'view_item' else 'add-to-cart' if e['event_name'] == 'add_to_cart' else 'user-logout' if e['event_name'] == 'user_logout' else ''}">
                    <div class="event-time">{e['timestamp']}</div>
                    <div class="event-name">{e['event_name']}</div>
                    <div class="event-data">{json.dumps(e['data'], indent=2)}</div>
                </div>
                """ for e in all_events]) or "<p>No events recorded yet</p>"}
            </div>
            
            <div id="PageViews" class="tabcontent">
                <h3>Page View Events</h3>
                {''.join([f"""
                <div class="event page-view">
                    <div class="event-time">{e['timestamp']}</div>
                    <div class="event-name">{e['event_name']}</div>
                    <div class="event-data">{json.dumps(e['data'], indent=2)}</div>
                </div>
                """ for e in page_views]) or "<p>No page view events recorded yet</p>"}
            </div>
            
            <div id="ProductViews" class="tabcontent">
                <h3>Product View Events</h3>
                {''.join([f"""
                <div class="event product-view">
                    <div class="event-time">{e['timestamp']}</div>
                    <div class="event-name">{e['event_name']}</div>
                    <div class="event-data">{json.dumps(e['data'], indent=2)}</div>
                </div>
                """ for e in product_views]) or "<p>No product view events recorded yet</p>"}
            </div>
            
            <div id="AddToCart" class="tabcontent">
                <h3>Add to Cart Events</h3>
                {''.join([f"""
                <div class="event add-to-cart">
                    <div class="event-time">{e['timestamp']}</div>
                    <div class="event-name">{e['event_name']}</div>
                    <div class="event-data">{json.dumps(e['data'], indent=2)}</div>
                </div>
                """ for e in add_to_cart_events]) or "<p>No add to cart events recorded yet</p>"}
            </div>
            
            <div id="Logouts" class="tabcontent">
                <h3>User Logout Events</h3>
                {''.join([f"""
                <div class="event user-logout">
                    <div class="event-time">{e['timestamp']}</div>
                    <div class="event-name">{e['event_name']}</div>
                    <div class="event-data">{json.dumps(e['data'], indent=2)}</div>
                </div>
                """ for e in logouts]) or "<p>No user logout events recorded yet</p>"}
            </div>
        </div>
    </body>
    </html>
    """
    
    return debug_html

# Routes
@app.route('/')
@track_pageview(gtm)
def home():
    products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
@track_pageview(gtm)
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
            
        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        
        # First user is admin
        if User.query.count() == 0:
            user.is_admin = True
            
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
@track_pageview(gtm)
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('Invalid username or password')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    gtm.send_event('user_logout')
    logout_user()
    return redirect(url_for('home'))

@app.route('/product/<int:product_id>')
@track_pageview(gtm)
def product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Track product view event
    gtm.send_event('view_item', {
        'items': [{
            'item_id': product.id,
            'item_name': product.name,
            'price': product.price
        }]
    })
    
    return render_template('product.html', product=product)

@app.route('/cart')
@login_required
@track_pageview(gtm)
def cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))
    
    # Check if item already in cart
    cart_item = CartItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = CartItem(user_id=current_user.id, product_id=product_id, quantity=quantity)
        db.session.add(cart_item)
        
    db.session.commit()
    
    # Track add to cart event
    gtm.track_add_to_cart(
        item_id=product.id,
        item_name=product.name,
        price=product.price,
        quantity=quantity
    )
    
    flash(f'Added {product.name} to your cart!')
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<int:item_id>')
@login_required
def remove_from_cart(item_id):
    cart_item = CartItem.query.get_or_404(item_id)
    if cart_item.user_id != current_user.id:
        flash('You cannot remove this item!')
        return redirect(url_for('cart'))
        
    db.session.delete(cart_item)
    db.session.commit()
    flash('Item removed from cart')
    return redirect(url_for('cart'))

@app.route('/checkout')
@login_required
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Your cart is empty')
        return redirect(url_for('cart'))
        
    # Create order
    order = Order(user_id=current_user.id)
    db.session.add(order)
    
    # Prepare for GTM tracking
    order_items = []
    order_total = 0
    
    # Add items to order
    for item in cart_items:
        order_item = OrderItem(order_id=order.id, product_id=item.product_id, quantity=item.quantity)
        db.session.add(order_item)
        
        # Update product stock
        product = item.product
        product.stock -= item.quantity
        
        # Add to tracking data
        order_items.append({
            'item_id': str(product.id),
            'item_name': product.name,
            'price': product.price,
            'quantity': item.quantity
        })
        order_total += product.price * item.quantity
        
        # Remove from cart
        db.session.delete(item)
        
    order.complete = True
    db.session.commit()
    
    # Track purchase event
    gtm.track_purchase(
        transaction_id=str(order.id),
        value=order_total,
        items=order_items
    )
    
    flash('Order placed successfully!')
    return redirect(url_for('orders'))

@app.route('/orders')
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.date_ordered.desc()).all()
    return render_template('orders.html', orders=orders)

# Admin routes
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('home'))
        
    return render_template('admin/index.html')

@app.route('/admin/products')
@login_required
def admin_products():
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('home'))
        
    products = Product.query.all()
    return render_template('admin/products.html', products=products)

@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        stock = int(request.form.get('stock'))
        
        product = Product(name=name, description=description, price=price, stock=stock)
        
        # Handle image upload
        if 'image' in request.files:
            image = request.files['image']
            if image.filename:
                filename = f"{name.lower().replace(' ', '_')}.jpg"
                image.save(os.path.join(app.root_path, 'static/images', filename))
                product.image = filename
                
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully!')
        return redirect(url_for('admin_products'))
        
    return render_template('admin/add_product.html')

@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('home'))
        
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        product.stock = int(request.form.get('stock'))
        
        # Handle image upload
        if 'image' in request.files and request.files['image'].filename:
            image = request.files['image']
            filename = f"{product.name.lower().replace(' ', '_')}.jpg"
            image.save(os.path.join(app.root_path, 'static/images', filename))
            product.image = filename
            
        db.session.commit()
        flash('Product updated successfully!')
        return redirect(url_for('admin_products'))
        
    return render_template('admin/edit_product.html', product=product)

@app.route('/admin/delete_product/<int:product_id>')
@login_required
def delete_product(product_id):
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('home'))
        
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully!')
    return redirect(url_for('admin_products'))

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('home'))
        
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/toggle_admin/<int:user_id>')
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('home'))
        
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f"Admin status {'granted to' if user.is_admin else 'revoked from'} {user.username}")
    return redirect(url_for('admin_users'))

@app.route('/admin/orders')
@login_required
def admin_orders():
    if not current_user.is_admin:
        flash('Access denied: Admin privileges required')
        return redirect(url_for('home'))
        
    orders = Order.query.order_by(Order.date_ordered.desc()).all()
    return render_template('admin/orders.html', orders=orders)

# Initialize the database
with app.app_context():
    db.create_all()
    
    # Create admin user if no users exist
    if User.query.count() == 0:
        admin = User(username="admin", email="admin@example.com", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        
        # Add some sample products
        products = [
            Product(name="Laptop", description="High-performance laptop with SSD", price=999.99, stock=10, image="laptop.jpg"),
            Product(name="Smartphone", description="Latest smartphone with high-res camera", price=699.99, stock=15, image="smartphone.jpg"),
            Product(name="Headphones", description="Noise-cancelling wireless headphones", price=199.99, stock=20, image="headphones.jpg"),
        ]
        db.session.add_all(products)
        db.session.commit()

if __name__ == "__main__":
    # For development
    # app.run(host="0.0.0.0", port=5015, debug=True)
    
    # For production with nginx
    app.run(host="127.0.0.1", port=5015)
