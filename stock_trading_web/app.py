from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_caching import Cache
from flask_minify import Minify
from config import Config
from models import db, NguoiDung
from routes import init_routes

app = Flask(__name__)
app.config.from_object(Config)

# Khởi tạo các thành phần
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
cache = Cache(app)
cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 10800})
Minify(app=app, html=True, js=True, cssless=True)

# Hàm tải người dùng
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(NguoiDung, int(user_id))

# Khởi tạo route và truyền cache
init_routes(app, cache)

# Tạo bảng cơ sở dữ liệu trong context
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)