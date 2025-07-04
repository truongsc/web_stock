class Config:
    SECRET_KEY = 'mysecretkey123'  # Chuỗi bí mật để bảo mật
    SQLALCHEMY_DATABASE_URI = 'mysql+mysqlconnector://root:23082004@localhost/stock_trading_db'
    # Thay 'root123' bằng mật khẩu MySQL của bạn
    SQLALCHEMY_TRACK_MODIFICATIONS = False