from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import date, datetime

db = SQLAlchemy()

class NguoiDung(db.Model, UserMixin):  # Kế thừa từ UserMixin
    __tablename__ = 'nguoi_dung'
    id = db.Column(db.Integer, primary_key=True)
    ten = db.Column(db.String(100), nullable=False)
    tk = db.Column(db.String(50), unique=True, nullable=False)
    mk = db.Column(db.String(50), nullable=False)
    so_tien = db.Column(db.Float, default=0.0)
    vai_tro = db.Column(db.String(20), default='user')  # 'user' hoặc 'admin'
class StockCodes(db.Model):
    __tablename__ = 'stock_codes'
    id = db.Column(db.Integer, primary_key=True)
    ma_cp = db.Column(db.String(10), unique=True, nullable=False)
class DanhMucCP(db.Model):
    __tablename__ = 'danh_muc_cp'
    id_nguoi_dung = db.Column(db.Integer, db.ForeignKey('nguoi_dung.id'), primary_key=True)
    ma_cp = db.Column(db.String(10), primary_key=True)
    so_luong = db.Column(db.Integer, nullable=False)

class LichSuGD(db.Model):
    __tablename__ = 'lich_su_gd'
    id_gd = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_nguoi_dung = db.Column(db.Integer, db.ForeignKey('nguoi_dung.id'), nullable=False)
    time = db.Column(db.DateTime, nullable=False)
    ma_cp = db.Column(db.String(10), nullable=False)
    so_luong = db.Column(db.Integer, nullable=False)
    gia_tri = db.Column(db.Float, nullable=False)

class LoaiCP(db.Model):
    __tablename__ = 'loai_cp'
    ma_cp = db.Column(db.String(10), primary_key=True)
    ten_linh_vuc = db.Column(db.String(100), db.ForeignKey('linh_vuc.ten_linh_vuc'), nullable=False)

class LinhVuc(db.Model):
    __tablename__ = 'linh_vuc'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ten_linh_vuc = db.Column(db.String(100), unique=True, nullable=False)

class TongGiaTriTrongNgay(db.Model):
    __tablename__ = 'tong_gia_tri_trong_ngay'
    id_nguoi_dung = db.Column(db.Integer, db.ForeignKey('nguoi_dung.id'), primary_key=True)
    time = db.Column(db.Date, primary_key=True)  # Theo ngày cụ thể
    gia_tri_tong_tai_san = db.Column(db.Float, nullable=False)

class DailyProfit(db.Model):
    __tablename__ = 'daily_profit'
    id = db.Column(db.Integer, primary_key=True)
    id_nguoi_dung = db.Column(db.Integer, db.ForeignKey('nguoi_dung.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, unique=True)
    total_assets = db.Column(db.Float, nullable=False)
    profit = db.Column(db.Float, nullable=False)
    nguoi_dung = db.relationship('NguoiDung', backref=db.backref('daily_profit', lazy=True))

class DailyPortfolioValue(db.Model):
    __tablename__ = 'daily_portfolio_value'
    id = db.Column(db.Integer, primary_key=True)
    id_nguoi_dung = db.Column(db.Integer, db.ForeignKey('nguoi_dung.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, unique=True)
    portfolio_value = db.Column(db.Float, nullable=False)
    nguoi_dung = db.relationship('NguoiDung', backref=db.backref('daily_portfolio_value', lazy=True))

class StockPriceDaily(db.Model):
    __tablename__ = 'stock_price_daily'
    id = db.Column(db.Integer, primary_key=True)
    ma_cp = db.Column(db.String(10), nullable=False)
    date = db.Column(db.Date, nullable=False)
    price = db.Column(db.Float, nullable=False)  # Giá đóng cửa
    volume = db.Column(db.BigInteger, nullable=False, default=0)  # Khối lượng giao dịch
    __table_args__ = (db.UniqueConstraint('ma_cp', 'date', name='unique_stock_date_daily'),)

class StockPriceHistorical(db.Model):
    __tablename__ = 'stock_price_historical'
    id = db.Column(db.Integer, primary_key=True)
    ma_cp = db.Column(db.String(10), nullable=False)
    date = db.Column(db.Date, nullable=False)
    open_price = db.Column(db.Float, nullable=False)
    high_price = db.Column(db.Float, nullable=False)
    low_price = db.Column(db.Float, nullable=False)
    close_price = db.Column(db.Float, nullable=False)
    volume = db.Column(db.BigInteger, nullable=False)
    __table_args__ = (db.UniqueConstraint('ma_cp', 'date', name='unique_stock_historical_date'),)

class StockInfo(db.Model):
    __tablename__ = 'stock_info'
    ma_cp = db.Column(db.String(10), primary_key=True)
    ten_cong_ty = db.Column(db.String(255), nullable=False)
    sector = db.Column(db.String(100), nullable=True)
    market_cap = db.Column(db.BigInteger, nullable=True)
    trailing_pe = db.Column(db.Float, nullable=True)
    trailing_eps = db.Column(db.Float, nullable=True)
    beta = db.Column(db.Float, nullable=True)
    dividend_yield = db.Column(db.Float, nullable=True)
    avg_volume_10d = db.Column(db.BigInteger, nullable=True)
    avg_volume_3m = db.Column(db.BigInteger, nullable=True)
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class StockFinancials(db.Model):
    __tablename__ = 'stock_financials'
    id = db.Column(db.Integer, primary_key=True)
    ma_cp = db.Column(db.String(10), nullable=False)
    year = db.Column(db.Integer, nullable=False)  # Năm báo cáo
    total_revenue = db.Column(db.BigInteger, nullable=True)
    net_income = db.Column(db.BigInteger, nullable=True)
    __table_args__ = (db.UniqueConstraint('ma_cp', 'year', name='unique_financials'),)

class StockDividends(db.Model):
    __tablename__ = 'stock_dividends'
    id = db.Column(db.Integer, primary_key=True)
    ma_cp = db.Column(db.String(10), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    __table_args__ = (db.UniqueConstraint('ma_cp', 'date', name='unique_dividend'),)

class StockCashFlow(db.Model):
    __tablename__ = 'stock_cashflow'
    id = db.Column(db.Integer, primary_key=True)
    ma_cp = db.Column(db.String(10), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    free_cash_flow = db.Column(db.BigInteger, nullable=True)
    __table_args__ = (db.UniqueConstraint('ma_cp', 'year', name='unique_cashflow'),)

class StockBalanceSheet(db.Model):
    __tablename__ = 'stock_balance_sheet'
    id = db.Column(db.Integer, primary_key=True)
    ma_cp = db.Column(db.String(10), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_liabilities = db.Column(db.BigInteger, nullable=True)
    total_equity = db.Column(db.BigInteger, nullable=True)
    __table_args__ = (db.UniqueConstraint('ma_cp', 'year', name='unique_balance_sheet'),)

class ApiCallLog(db.Model):
    __tablename__ = 'api_call_log'
    id = db.Column(db.Integer, primary_key=True)
    ma_cp = db.Column(db.String(10), nullable=False)
    api_method = db.Column(db.String(50), nullable=False)
    response_status = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)