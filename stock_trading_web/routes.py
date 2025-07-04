from functools import wraps
import random
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
import plotly
import sqlalchemy
from models import db, NguoiDung, DanhMucCP, LichSuGD, TongGiaTriTrongNgay, DailyProfit, DailyPortfolioValue, StockPriceDaily, StockPriceHistorical, StockInfo, StockFinancials, StockDividends, StockCashFlow, StockBalanceSheet, ApiCallLog, StockCodes
from datetime import datetime, date, timedelta, timezone
import yfinance as yf
import plotly.graph_objs as go
import calendar as cal
import calendar
import numpy as np
import pandas as pd
import json
from sqlalchemy import func
from flask import jsonify

def get_previous_trading_day(ma_cp, current_date):
    """
    Tìm ngày giao dịch trước đó (bỏ qua ngày không giao dịch).
    ma_cp: Mã cổ phiếu
    current_date: Ngày hiện tại
    Trả về: Ngày giao dịch trước đó hoặc None nếu không tìm thấy
    """
    previous_date = current_date - timedelta(days=1)
    while previous_date >= current_date - timedelta(days=30):  # Giới hạn tìm kiếm trong 30 ngày để tránh vòng lặp vô hạn
        price_record = StockPriceDaily.query.filter_by(ma_cp=ma_cp, date=previous_date).first()
        if price_record:
            return previous_date
        previous_date -= timedelta(days=1)
    return None

def init_routes(app, cache):
    # Hàm kiểm tra vai trò admin
    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.vai_tro != 'admin':
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function

    # Routes người dùng
    @app.route('/')
    def index():
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            tk = request.form['tk']
            mk = request.form['mk']
            user = NguoiDung.query.filter_by(tk=tk).first()
            if user and user.mk == mk:
                login_user(user)
                if user.vai_tro == 'admin':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('dashboard'))
            flash('Sai tài khoản hoặc mật khẩu')
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            ten = request.form['ten']
            tk = request.form['tk']
            mk = request.form['mk']
            if NguoiDung.query.filter_by(tk=tk).first():
                flash('Tài khoản đã tồn tại')
            else:
                new_user = NguoiDung(ten=ten, tk=tk, mk=mk, so_tien=100000.0, vai_tro='user')
                db.session.add(new_user)
                db.session.commit()
                flash('Đăng ký thành công! Hãy đăng nhập.')
                return redirect(url_for('login'))
        return render_template('register.html')

    @app.route('/update_stock_prices', methods=['POST'])
    @login_required
    def update_stock_prices():
        try:
            traded_stocks = db.session.query(LichSuGD.ma_cp).distinct().all()
            stock_codes_records = StockCodes.query.all()
            stock_codes = list(set([stock[0] for stock in traded_stocks] + [record.ma_cp for record in stock_codes_records]))
            today = date.today()

            for ma_cp in stock_codes:
                stock = yf.Ticker(ma_cp)
                hist = stock.history(period='1d', interval='1d')
                if not hist.empty:
                    last_price = float(hist['Close'].iloc[-1])
                    last_volume = int(hist['Volume'].iloc[-1])
                    daily_price = StockPriceDaily(
                        ma_cp=ma_cp,
                        date=today,
                        price=last_price,
                        volume=last_volume
                    )
                    db.session.merge(daily_price)

                    historical_price = StockPriceHistorical(
                        ma_cp=ma_cp,
                        date=today,
                        open_price=float(hist['Open'].iloc[-1]),
                        high_price=float(hist['High'].iloc[-1]),
                        low_price=float(hist['Low'].iloc[-1]),
                        close_price=last_price,
                        volume=last_volume
                    )
                    db.session.merge(historical_price)

                    db.session.add(ApiCallLog(
                        ma_cp=ma_cp,
                        api_method='history_1d',
                        response_status='success',
                        timestamp=datetime.now(timezone.utc)
                    ))

                info = stock.info
                stock_info = StockInfo(
                    ma_cp=ma_cp,
                    ten_cong_ty=info.get('longName', 'N/A'),
                    sector=info.get('sector', 'N/A'),
                    market_cap=info.get('marketCap', 0),
                    trailing_pe=info.get('trailingPE', 0) or None,
                    trailing_eps=info.get('trailingEps', 0) or None,
                    beta=info.get('beta', 0) or None,
                    dividend_yield=info.get('dividendYield', 0) or None,
                    avg_volume_10d=info.get('averageVolume10days', 0) or None,
                    avg_volume_3m=info.get('averageDailyVolume3Month', 0) or None,
                    last_updated=datetime.now(timezone.utc)
                )
                db.session.merge(stock_info)

                db.session.add(ApiCallLog(
                    ma_cp=ma_cp,
                    api_method='info',
                    response_status='success',
                    timestamp=datetime.now(timezone.utc)
                ))

                financials = stock.financials
                if not financials.empty:
                    for year in financials.columns:
                        year_int = year.year
                        total_revenue = int(financials[year].loc['Total Revenue']) if 'Total Revenue' in financials[year].index else None
                        net_income = int(financials[year].loc['Net Income']) if 'Net Income' in financials[year].index else None
                        financial_record = StockFinancials(
                            ma_cp=ma_cp,
                            year=year_int,
                            total_revenue=total_revenue,
                            net_income=net_income
                        )
                        db.session.merge(financial_record)

                dividends = stock.dividends
                if not dividends.empty:
                    for index, amount in dividends.items():
                        dividend_record = StockDividends(
                            ma_cp=ma_cp,
                            date=index.date(),
                            amount=float(amount)
                        )
                        db.session.merge(dividend_record)

                cashflow = stock.cashflow
                if not cashflow.empty:
                    for year in cashflow.columns:
                        year_int = year.year
                        free_cash_flow = int(cashflow[year].loc['Free Cash Flow']) if 'Free Cash Flow' in cashflow[year].index else None
                        cashflow_record = StockCashFlow(
                            ma_cp=ma_cp,
                            year=year_int,
                            free_cash_flow=free_cash_flow
                        )
                        db.session.merge(cashflow_record)

                balance_sheet = stock.balance_sheet
                if not balance_sheet.empty:
                    for year in balance_sheet.columns:
                        year_int = year.year
                        total_liabilities = int(balance_sheet[year].loc['Total Liabilities']) if 'Total Liabilities' in balance_sheet[year].index else None
                        total_equity = int(balance_sheet[year].loc['Total Stockholder Equity']) if 'Total Stockholder Equity' in balance_sheet[year].index else None
                        balance_record = StockBalanceSheet(
                            ma_cp=ma_cp,
                            year=year_int,
                            total_liabilities=total_liabilities,
                            total_equity=total_equity
                        )
                        db.session.merge(balance_record)

            db.session.commit()
            flash('Cập nhật dữ liệu cổ phiếu thành công!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Lỗi khi cập nhật: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

    @app.route('/dashboard', methods=['GET', 'POST'])
    @login_required
    def dashboard():
     if current_user.vai_tro == 'admin':
        return redirect(url_for('admin_dashboard'))

     user = db.session.get(NguoiDung, current_user.id)
     holdings = DanhMucCP.query.filter_by(id_nguoi_dung=user.id).all()

     total_assets = user.so_tien or 0.0
     portfolio_stocks = []
     today = date.today()  # 07:17 AM +07, Thursday, June 19, 2025

     missing_data = False
     for holding in holdings:
        price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=today).first()
        if not price_record:
            price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp).order_by(StockPriceDaily.date.desc()).first()
            missing_data = True
        if not price_record:
            continue

        last_price = float(price_record.price)
        last_volume = int(price_record.volume)

        # Tìm ngày giao dịch trước đó
        prev_trading_day = get_previous_trading_day(holding.ma_cp, price_record.date)
        prev_price = last_price
        change = 0.0
        if prev_trading_day:
            prev_price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=prev_trading_day).first()
            if prev_price_record:
                prev_price = float(prev_price_record.price)
                change = ((last_price - prev_price) / prev_price * 100) if prev_price != 0 else 0.0

        gia_tri = last_price * holding.so_luong
        total_assets += gia_tri
        portfolio_stocks.append({
            'ma_cp': holding.ma_cp,
            'so_luong': holding.so_luong,
            'gia': round(last_price, 2),
            'gia_tri': round(gia_tri, 2),
            'change': round(change, 2)
        })

     # Dữ liệu thị trường
     market_data = []
     stock_codes_records = StockCodes.query.all()
     stock_codes = [record.ma_cp for record in stock_codes_records]
     for symbol in stock_codes:
        price_record = StockPriceDaily.query.filter_by(ma_cp=symbol, date=today).first()
        if not price_record:
            price_record = StockPriceDaily.query.filter_by(ma_cp=symbol).order_by(StockPriceDaily.date.desc()).first()
        if not price_record:
            market_data.append({
                'ma_cp': symbol,
                'gia': 100.0,
                'change': round(random.uniform(-5.0, 5.0), 2),
                'volume': 1000
            })
            continue

        last_price = float(price_record.price)
        last_volume = int(price_record.volume)

        prev_trading_day = get_previous_trading_day(symbol, price_record.date)
        prev_price = last_price
        pct_change = 0.0
        if prev_trading_day:
            prev_price_record = StockPriceDaily.query.filter_by(ma_cp=symbol, date=prev_trading_day).first()
            if prev_price_record:
                prev_price = float(prev_price_record.price)
                pct_change = ((last_price - prev_price) / prev_price * 100) if prev_price != 0 else 0.0

        market_data.append({
            'ma_cp': symbol,
            'gia': round(last_price, 2),
            'change': round(pct_change, 2),
            'volume': last_volume
        })

     yesterday = today - timedelta(days=1)
     yesterday_record = TongGiaTriTrongNgay.query.filter_by(id_nguoi_dung=user.id, time=yesterday).first()
     today_record = TongGiaTriTrongNgay.query.filter_by(id_nguoi_dung=user.id, time=today).first()
     profit = 0.0
     profit_change = 0.0
     if today_record and yesterday_record:
        profit = today_record.gia_tri_tong_tai_san - yesterday_record.gia_tri_tong_tai_san
        profit_change = (profit / yesterday_record.gia_tri_tong_tai_san * 100) if yesterday_record.gia_tri_tong_tai_san != 0 else 0.0
     elif today_record:
        profit = today_record.gia_tri_tong_tai_san - 100000.0
        profit_change = (profit / 100000.0 * 100)

     transactions = LichSuGD.query.filter_by(id_nguoi_dung=user.id).all()
     total_volume = sum(abs(gd.so_luong) for gd in transactions)
     total_transaction_value = sum(gd.gia_tri for gd in transactions)
     yesterday_transactions = LichSuGD.query.filter_by(id_nguoi_dung=user.id).filter(LichSuGD.time < today).all()
     yesterday_volume = sum(abs(gd.so_luong) for gd in yesterday_transactions)
     volume_change = ((total_volume - yesterday_volume) / yesterday_volume * 100) if yesterday_volume != 0 else 0.0

     search_query = request.form.get('search', '').upper()
     if search_query:
        if search_query in stock_codes:
            return redirect(url_for('stock_search', ma_cp=search_query))
        else:
            flash('Mã cổ phiếu không tồn tại!', 'error')

     page = int(request.args.get('page', 1))
     per_page = 5
     total_holdings = len(portfolio_stocks)
     total_pages = (total_holdings + per_page - 1) // per_page
     start = (page - 1) * per_page
     end = start + per_page
     paginated_holdings = portfolio_stocks[start:end]

     # 1. Biểu đồ tỷ trọng các ngành (Sector Weightings)
     sector_data = db.session.query(
        StockInfo.sector,
        func.sum(StockInfo.market_cap).label('total_market_cap')
     ).filter(
        StockInfo.sector.isnot(None),
        StockInfo.market_cap.isnot(None)
     ).group_by(StockInfo.sector).all()

     sector_labels = []
     sector_values = []
     total_market_cap = sum(record.total_market_cap for record in sector_data if record.total_market_cap)

     if total_market_cap > 0:
        for sector, market_cap in sector_data:
            if sector and market_cap:
                sector_labels.append(sector)
                sector_values.append((market_cap / total_market_cap) * 100)  # Tính phần trăm

     sector_fig = None
     if sector_labels and sector_values:
        sector_fig = {
            'data': [{
                'type': 'pie',
                'labels': sector_labels,
                'values': sector_values,
                'textinfo': 'label+percent',
                'hoverinfo': 'label+percent',
                'marker': {
                    'colors': ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
                               '#FF9F40', '#FFCD56', '#4BC0C0', '#36A2EB', '#9966FF']
                }
            }],
            'layout': {
                'title': {'text': 'Tỷ trọng các ngành trong thị trường Mỹ'},
                'showlegend': True
            }
        }
        sector_chart = json.dumps(sector_fig)
     else:
        sector_chart = json.dumps({'data': [], 'layout': {'title': {'text': 'Không có dữ liệu ngành'}}})

     # 2. Biểu đồ nến của chỉ số S&P 500 (^GSPC)
     sp500_chart = None
     try:
        sp500 = yf.Ticker('^GSPC')
        end_date = today
        start_date = end_date - timedelta(days=90)  # Lấy dữ liệu 90 ngày gần nhất
        sp500_data = sp500.history(start=start_date, end=end_date, interval='1d')

        if not sp500_data.empty:
            candlestick = {
                'x': sp500_data.index.strftime('%Y-%m-%d').tolist(),
                'open': sp500_data['Open'].tolist(),
                'high': sp500_data['High'].tolist(),
                'low': sp500_data['Low'].tolist(),
                'close': sp500_data['Close'].tolist(),
                'type': 'candlestick',
                'name': 'S&P 500'
            }
            sp500_fig = {
                'data': [candlestick],
                'layout': {
                    'title': {'text': ''},
                    'xaxis': {'title': {'text': 'Ngày'}},
                    'yaxis': {'title': {'text': 'Giá'}},
                    'xaxis_rangeslider_visible': False,
                    'hovermode': 'x unified'
                }
            }
            sp500_chart = json.dumps(sp500_fig)
        else:
            flash('Không thể lấy dữ liệu chỉ số S&P 500.', 'warning')
     except Exception as e:
        flash(f'Lỗi khi lấy dữ liệu S&P 500: {str(e)}', 'danger')

     return render_template('dashboard.html',
                          user=user,
                          total_assets=round(total_assets, 2),
                          profit=round(profit, 2),
                          profit_change=round(profit_change, 2),
                          total_volume=total_volume,
                          volume_change=round(volume_change, 2),
                          total_transaction_value=round(total_transaction_value, 2),
                          market_data=market_data,
                          holdings=paginated_holdings,
                          page=page,
                          total_pages=total_pages,
                          sector_chart=sector_chart,
                          sp500_chart=sp500_chart)
    @app.route('/cash', methods=['GET', 'POST'])
    @login_required
    def cash():
        if current_user.vai_tro == 'admin':
            return redirect(url_for('admin_dashboard'))
        user = db.session.get(NguoiDung, current_user.id)
        if request.method == 'POST':
            amount = float(request.form.get('amount', 0))
            action = request.form.get('action')

            if amount <= 0:
                flash('Số tiền phải lớn hơn 0!', 'error')
                return redirect(url_for('cash'))

            if action == 'deposit':
                user.so_tien += amount
                flash(f'Đã nạp ${amount} thành công!', 'success')
            elif action == 'withdraw':
                if user.so_tien >= amount:
                    user.so_tien -= amount
                    flash(f'Đã rút ${amount} thành công!', 'success')
                else:
                    flash('Số dư không đủ để rút!', 'error')
                    return redirect(url_for('cash'))

            giao_dich = LichSuGD(
                id_nguoi_dung=user.id,
                time=datetime.now(),
                ma_cp='CASH',
                so_luong=0,
                gia_tri=amount if action == 'deposit' else -amount
            )
            db.session.add(giao_dich)
            db.session.commit()

            return redirect(url_for('cash'))

        return render_template('cash.html', user=user, cash=round(user.so_tien, 2))

    @app.route('/trading', methods=['GET', 'POST'])
    @login_required
    def trading():
     if current_user.vai_tro == 'admin':
        return redirect(url_for('admin_dashboard'))
     user = db.session.get(NguoiDung, current_user.id)
     today = date.today()

     if request.method == 'POST' and 'finalize_trading' in request.form:
        total_assets = user.so_tien or 0.0
        holdings = DanhMucCP.query.filter_by(id_nguoi_dung=user.id).all()

        for holding in holdings:
            price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=today).first()
            if not price_record:
                price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp).order_by(StockPriceDaily.date.desc()).first()
            if price_record:
                last_price = float(price_record.price)
                total_assets += last_price * holding.so_luong

        existing_record = TongGiaTriTrongNgay.query.filter_by(id_nguoi_dung=user.id, time=today).first()
        if not existing_record:
            daily_record = TongGiaTriTrongNgay(
                id_nguoi_dung=user.id,
                time=today,
                gia_tri_tong_tai_san=total_assets
            )
            db.session.add(daily_record)
        else:
            existing_record.gia_tri_tong_tai_san = total_assets
        db.session.commit()
        flash('Đã chốt kết quả giao dịch và lưu tổng tài sản.')
        return redirect(url_for('trading'))

     stock_codes_records = StockCodes.query.all()
     stock_codes = [record.ma_cp for record in stock_codes_records]

     stocks = []
     missing_data = False
     for symbol in stock_codes[:30]:
        price_record = StockPriceDaily.query.filter_by(ma_cp=symbol, date=today).first()
        if not price_record:
            price_record = StockPriceDaily.query.filter_by(ma_cp=symbol).order_by(StockPriceDaily.date.desc()).first()
            missing_data = True
        if not price_record:
            continue

        last_price = float(price_record.price)
        last_volume = int(price_record.volume)

        # Tìm ngày giao dịch trước đó
        prev_trading_day = get_previous_trading_day(symbol, price_record.date)
        prev_price = last_price
        pct_change = 0.0
        if prev_trading_day:
            prev_price_record = StockPriceDaily.query.filter_by(ma_cp=symbol, date=prev_trading_day).first()
            if prev_price_record:
                prev_price = float(prev_price_record.price)
                pct_change = ((last_price - prev_price) / prev_price * 100) if prev_price != 0 else 0.0

        stocks.append({
            'ma_cp': symbol,
            'gia': round(last_price, 2),
            'volume': last_volume,
            'change': round(pct_change, 2)
        })

     news = []
     try:
        ticker = yf.Ticker('AAPL')
        news_data = ticker.news[:5]
        for item in news_data:
            news.append({
                'title': item.get('title', 'N/A'),
                'link': item.get('link', '#')
            })
     except Exception as e:
        flash(f'Không thể lấy tin tức thị trường: {str(e)}', 'danger')

     return render_template('trading.html', stocks=stocks, news=news)
    @app.route('/trade/<ma_cp>', methods=['GET', 'POST'])
    @login_required
    def trade_stock(ma_cp):
     if current_user.vai_tro == 'admin':
        return redirect(url_for('admin_dashboard'))
     today = date.today()

     stock_codes_records = StockCodes.query.all()
     stock_codes = [record.ma_cp for record in stock_codes_records]
     if ma_cp not in stock_codes:
        flash(f'Mã cổ phiếu {ma_cp} không tồn tại!', 'error')
        return redirect(url_for('trading'))

     price_record = StockPriceDaily.query.filter_by(ma_cp=ma_cp, date=today).first()
     if not price_record:
        price_record = StockPriceDaily.query.filter_by(ma_cp=ma_cp).order_by(StockPriceDaily.date.desc()).first()
     if not price_record:
        flash(f'Không có dữ liệu giá cho {ma_cp}. Vui lòng cập nhật dữ liệu!', 'error')
        return redirect(url_for('trading'))

     last_price = float(price_record.price)
     last_volume = int(price_record.volume)

     # Tìm ngày giao dịch trước đó
     prev_trading_day = get_previous_trading_day(ma_cp, price_record.date)
     prev_price = last_price
     pct_change = 0.0
     if prev_trading_day:
        prev_price_record = StockPriceDaily.query.filter_by(ma_cp=ma_cp, date=prev_trading_day).first()
        if prev_price_record:
            prev_price = float(prev_price_record.price)
            pct_change = ((last_price - prev_price) / prev_price * 100) if prev_price != 0 else 0.0

     stock = {
        'ma_cp': ma_cp,
        'gia': round(last_price, 2),
        'volume': last_volume,
        'change': round(pct_change, 2)
     }

     historical_data = StockPriceHistorical.query.filter_by(ma_cp=ma_cp).order_by(StockPriceHistorical.date.asc()).all()
     if not historical_data:
        flash(f'Không có dữ liệu lịch sử giá cho {ma_cp}. Vui lòng cập nhật dữ liệu!', 'warning')

     chart_data = {
        'candlestick': [
            {
                'x': record.date.strftime('%Y-%m-%d'),
                'y': [
                    float(record.open_price),
                    float(record.high_price),
                    float(record.low_price),
                    float(record.close_price)
                ]
            } for record in historical_data
        ],
        'volumes': [
            {
                'x': record.date.strftime('%Y-%m-%d'),
                'y': int(record.volume)
            } for record in historical_data
        ]
     }

     if request.method == 'POST':
        so_luong = int(request.form['so_luong'])
        action = request.form['action']
        gia_tri = float(stock['gia'] * so_luong)

        user = db.session.get(NguoiDung, current_user.id)
        if action == 'buy':
            if user.so_tien >= gia_tri:
                user.so_tien -= gia_tri
            else:
                flash('Không đủ tiền để mua cổ phiếu!', 'error')
                return redirect(url_for('trade_stock', ma_cp=ma_cp))
        elif action == 'sell':
            holding = DanhMucCP.query.filter_by(id_nguoi_dung=current_user.id, ma_cp=ma_cp).first()
            if not holding or holding.so_luong < so_luong:
                flash('Không đủ cổ phiếu để bán!', 'error')
                return redirect(url_for('trade_stock', ma_cp=ma_cp))
            user.so_tien += gia_tri

        giao_dich = LichSuGD(
            id_nguoi_dung=current_user.id,
            time=datetime.now(),
            ma_cp=ma_cp,
            so_luong=so_luong if action == 'buy' else -so_luong,
            gia_tri=gia_tri
        )
        db.session.add(giao_dich)

        holding = DanhMucCP.query.filter_by(id_nguoi_dung=current_user.id, ma_cp=ma_cp).first()
        if holding:
            if action == 'buy':
                holding.so_luong += so_luong
            elif action == 'sell':
                holding.so_luong -= so_luong
                if holding.so_luong == 0:
                    db.session.delete(holding)
        else:
            if action == 'buy':
                holding = DanhMucCP(id_nguoi_dung=current_user.id, ma_cp=ma_cp, so_luong=so_luong)
                db.session.add(holding)

        db.session.commit()
        flash(f'Đã {action} {so_luong} cổ phiếu {ma_cp} thành công!', 'success')
        return redirect(url_for('trade_stock', ma_cp=ma_cp))

     history = LichSuGD.query.filter_by(id_nguoi_dung=current_user.id, ma_cp=ma_cp).all()
     return render_template('trade_stock.html', stock=stock, history=history, chart_data=chart_data)
    @app.route('/portfolio', methods=['GET', 'POST'])
    @login_required
    def portfolio():
     if current_user.vai_tro == 'admin':
        return redirect(url_for('admin_dashboard'))
     user = db.session.get(NguoiDung, current_user.id)
     holdings = DanhMucCP.query.filter_by(id_nguoi_dung=user.id).all()

     total_assets = user.so_tien or 0.0
     portfolio_stocks = []
     pie_labels = ['Tiền mặt']
     pie_values = [user.so_tien or 0.0]
     current_stock_value = 0.0
     initial_stock_value = 0.0
     today = date.today()
     yesterday = today - timedelta(days=1)

     all_profit_records = DailyProfit.query.filter_by(id_nguoi_dung=user.id).order_by(DailyProfit.date).all()

     available_months = []
     for y in range(2020, today.year + 1):
        start_month = 1 if y != today.year else 1
        end_month = 12 if y != today.year else today.month
        for m in range(start_month, end_month + 1):
            available_months.append((y, m))

     selected_month = request.form.get('month', today.strftime('%Y-%m'))
     if not selected_month or selected_month.strip() == '':
        selected_month = today.strftime('%Y-%m')

     try:
        year, month = map(int, selected_month.split('-'))
        if not (1 <= month <= 12) or year < 1900 or year > 2100:
            raise ValueError("Invalid month or year")
     except (ValueError, AttributeError):
        year, month = today.year, today.month
        selected_month = today.strftime('%Y-%m')

     missing_data = False
     for holding in holdings:
        price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=today).first()
        if not price_record:
            price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp).order_by(StockPriceDaily.date.desc()).first()
            missing_data = True
        if not price_record:
            continue

        last_price = float(price_record.price)
        stock_info = StockInfo.query.filter_by(ma_cp=holding.ma_cp).first()
        ten_cong_ty = stock_info.ten_cong_ty if stock_info else 'N/A'

        gia_tri = last_price * holding.so_luong
        total_assets += gia_tri
        current_stock_value += gia_tri

        buy_transactions = LichSuGD.query.filter(
            LichSuGD.id_nguoi_dung == user.id,
            LichSuGD.ma_cp == holding.ma_cp,
            LichSuGD.so_luong > 0,
            LichSuGD.so_luong.isnot(None)
        ).all()
        initial_value = sum(t.gia_tri for t in buy_transactions)
        initial_stock_value += initial_value

        # Tính lợi nhuận của từng mã cổ phiếu
        profit_per_stock = (last_price * holding.so_luong) - initial_value
        portfolio_stocks.append({
            'ma_cp': holding.ma_cp,
            'ten_cong_ty': ten_cong_ty,
            'so_luong': holding.so_luong,
            'gia': round(last_price, 2),
            'gia_tri': round(gia_tri, 2),
            'profit': round(profit_per_stock, 2)
        })
        pie_labels.append(holding.ma_cp)
        pie_values.append(gia_tri)

     if total_assets > 0:
        pie_percentages = [round((value / total_assets) * 100, 2) for value in pie_values]
     else:
        pie_percentages = [0] * len(pie_values)

     pie_data = {
        'labels': pie_labels,
        'datasets': [{
            'data': pie_values,
            'backgroundColor': ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', "#12C96D", "#B61212", "#864545"],
            'borderColor': '#FFFFFF',
            'borderWidth': 2
        }]
     }

     timeframe = request.form.get('timeframe', 'day')
     trend_labels = []
     total_asset_values = []
     profit_values = []

     if timeframe == 'day':
        total_records = TongGiaTriTrongNgay.query.filter_by(id_nguoi_dung=user.id).order_by(TongGiaTriTrongNgay.time).all()
        profit_dict = {record.date.strftime('%Y-%m-%d'): float(record.profit) for record in all_profit_records if record.profit is not None}

        if total_records:
            for record in total_records:
                if record.gia_tri_tong_tai_san is not None:
                    record_date = record.time.strftime('%Y-%m-%d')
                    trend_labels.append(record_date)
                    total_asset_values.append(record.gia_tri_tong_tai_san)
                    profit = profit_dict.get(record_date, 0.0)
                    profit_values.append(profit)

     elif timeframe == 'week':
        total_records = db.session.query(
            func.date_format(TongGiaTriTrongNgay.time, '%Y-%u').label('week'),
            func.avg(TongGiaTriTrongNgay.gia_tri_tong_tai_san).label('avg_value')
        ).filter_by(id_nguoi_dung=user.id).group_by('week').order_by('week').all()
        profit_dict = {}
        for record in all_profit_records:
            week = record.date.strftime('%Y-%u')
            if week not in profit_dict:
                profit_dict[week] = []
            profit_dict[week].append(float(record.profit) if record.profit is not None else 0.0)
        profit_dict = {week: sum(profits) / len(profits) for week, profits in profit_dict.items()}

        if total_records:
            for record in total_records:
                trend_labels.append(f"Tuần {record.week}")
                total_asset_values.append(record.avg_value)
                profit = profit_dict.get(record.week, 0.0)
                profit_values.append(profit)

     elif timeframe == 'month':
        total_records = db.session.query(
            func.date_format(TongGiaTriTrongNgay.time, '%Y-%m').label('month'),
            func.avg(TongGiaTriTrongNgay.gia_tri_tong_tai_san).label('avg_value')
        ).filter_by(id_nguoi_dung=user.id).group_by('month').order_by('month').all()
        profit_dict = {}
        for record in all_profit_records:
            month_key = record.date.strftime('%Y-%m')
            if month_key not in profit_dict:
                profit_dict[month_key] = []
            profit_dict[month_key].append(float(record.profit) if record.profit is not None else 0.0)
        profit_dict = {month_key: sum(profits) / len(profits) for month_key, profits in profit_dict.items()}

        if total_records:
            for record in total_records:
                trend_labels.append(record.month)
                total_asset_values.append(record.avg_value)
                profit = profit_dict.get(record.month, 0.0)
                profit_values.append(profit)

     cumulative_profits = [0.0]
     for i in range(1, len(profit_values)):
        cumulative_profits.append(cumulative_profits[-1] + profit_values[i])

     asset_trend_data = {
        'labels': trend_labels,
        'datasets': [{
            'label': 'Tổng tài sản',
            'data': total_asset_values,
            'borderColor': '#4682B4',
            'backgroundColor': 'rgba(70, 130, 180, 0.1)',
            'borderWidth': 3,
            'fill': True,
            'tension': 0.4
        }]
     }

     profit_trend_data = {
        'labels': trend_labels,
        'datasets': [{
            'label': 'Lợi nhuận cộng dồn',
            'data': cumulative_profits,
            'borderColor': '#32CD32',
            'backgroundColor': 'rgba(50, 205, 50, 0.1)',
            'borderWidth': 3,
            'fill': True,
            'tension': 0.4
        }]
     }

     bar_data = {
        'labels': trend_labels,
        'datasets': [{
            'label': 'Lợi nhuận',
            'data': profit_values,
            'backgroundColor': ['#28a745' if value >= 0 else '#dc3545' for value in profit_values],
            'borderColor': '#FFFFFF',
            'borderWidth': 1
        }]
     }

     first_day = date(year, month, 1)
     _, days_in_month = calendar.monthrange(year, month)
     last_day = first_day.replace(day=days_in_month)
     profit_dict = {}
     for day in range(1, days_in_month + 1):
        current_date = first_day.replace(day=day)
        profit = next((float(record.profit) for record in all_profit_records if record.date == current_date and record.profit is not None), 0.0)
        profit_dict[day] = profit

     calendar_matrix = calendar.monthcalendar(year, month)
     calendar_profit_data = []
     for week in calendar_matrix:
        week_data = []
        for day in week:
            if day == 0:
                week_data.append({'day': '', 'profit_display': '', 'color': ''})
            else:
                profit = profit_dict.get(day, 0.0)
                profit_display = f"+{profit:.2f}" if profit > 0 else f"{profit:.2f}"
                color = '#28a745' if profit > 0 else '#dc3545' if profit < 0 else '#000000'
                week_data.append({'day': day, 'profit_display': profit_display, 'color': color})
        calendar_profit_data.append(week_data)

     daily_profit_table = DailyProfit.query.filter_by(id_nguoi_dung=user.id).order_by(DailyProfit.date.desc()).limit(1).all()
     if not daily_profit_table:
        daily_profit_table = []

     # Dữ liệu cho biểu đồ cột lợi nhuận của từng mã cổ phiếu
     stock_profit_data = {
        'labels': [stock['ma_cp'] for stock in portfolio_stocks],
        'datasets': [{
            'label': 'Lợi nhuận',
            'data': [stock['profit'] for stock in portfolio_stocks],
            'backgroundColor': ['#28a745' if stock['profit'] >= 0 else '#dc3545' for stock in portfolio_stocks],
            'borderColor': '#FFFFFF',
            'borderWidth': 1
        }]
     }

     return render_template('portfolio.html',
                          portfolio_stocks=portfolio_stocks,
                          cash=round(user.so_tien, 2),
                          total_assets=round(total_assets, 2),
                          pie_data=pie_data,
                          asset_trend_data=asset_trend_data,
                          profit_trend_data=profit_trend_data,
                          bar_data=bar_data,
                          calendar_profit_data=calendar_profit_data,
                          timeframe=timeframe,
                          current_month=first_day.strftime('%B %Y'),
                          selected_month=selected_month,
                          available_months=available_months,
                          daily_profit_table=daily_profit_table,
                          stock_profit_data=stock_profit_data)
    @app.route('/stock/<ma_cp>')
    @login_required
    def stock_detail(ma_cp):
        if current_user.vai_tro == 'admin':
            return redirect(url_for('admin_dashboard'))
        user = db.session.get(NguoiDung, current_user.id)
        holding = DanhMucCP.query.filter_by(id_nguoi_dung=user.id, ma_cp=ma_cp).first()

        if not holding:
            flash(f'Không sở hữu cổ phiếu {ma_cp}')
            return redirect(url_for('portfolio'))

        today = date.today()
        price_record = StockPriceDaily.query.filter_by(ma_cp=ma_cp, date=today).first()
        if not price_record:
            price_record = StockPriceDaily.query.filter_by(ma_cp=ma_cp).order_by(StockPriceDaily.date.desc()).first()

        if not price_record:
            flash(f'Không có dữ liệu giá cho {ma_cp}. Vui lòng cập nhật dữ liệu!', 'danger')
            return redirect(url_for('portfolio'))

        current_price = float(price_record.price)
        stock_info = StockInfo.query.filter_by(ma_cp=ma_cp).first()
        if not stock_info:
            flash(f'Không có thông tin cho {ma_cp}')
            return redirect(url_for('portfolio'))

        start_date = today - timedelta(days=365)
        history_records = StockPriceHistorical.query.filter(
            StockPriceHistorical.ma_cp == ma_cp,
            StockPriceHistorical.date >= start_date,
            StockPriceHistorical.date <= today
        ).order_by(StockPriceHistorical.date).all()

        transactions = LichSuGD.query.filter_by(id_nguoi_dung=user.id, ma_cp=ma_cp).all()
        total_shares_bought = 0
        total_cost = 0
        for gd in transactions:
            if gd.so_luong > 0:
                total_shares_bought += gd.so_luong
                total_cost += gd.gia_tri

        if total_shares_bought == 0:
            flash(f'Chưa có giao dịch mua nào cho {ma_cp}')
            return redirect(url_for('portfolio'))

        average_buy_price = total_cost / total_shares_bought
        profit = (current_price - average_buy_price) * holding.so_luong
        profit_percentage = ((current_price - average_buy_price) / average_buy_price * 100) if average_buy_price != 0 else 0.0

        latest_dividend_record = StockDividends.query.filter_by(ma_cp=ma_cp).order_by(StockDividends.date.desc()).first()
        latest_dividend = {
            'date': latest_dividend_record.date.strftime('%Y-%m-%d'),
            'amount': round(latest_dividend_record.amount, 4)
        } if latest_dividend_record else {}

        high_52w = max([record.high_price for record in history_records], default=0.0) if history_records else 'N/A'
        low_52w = min([record.low_price for record in history_records], default=0.0) if history_records else 'N/A'
        price_change_52w = round(((current_price - history_records[0].close_price) / history_records[0].close_price * 100), 2) if history_records and history_records[0].close_price != 0 else 'N/A'

        latest_financial = StockFinancials.query.filter_by(ma_cp=ma_cp).order_by(StockFinancials.year.desc()).first()
        net_margin = 'N/A'
        if latest_financial and latest_financial.total_revenue and latest_financial.net_income:
            net_margin = round((latest_financial.net_income / latest_financial.total_revenue) * 100, 2)

        latest_balance = StockBalanceSheet.query.filter_by(ma_cp=ma_cp).order_by(StockBalanceSheet.year.desc()).first()
        de_ratio = 'N/A'
        if latest_balance and latest_balance.total_equity and latest_balance.total_equity != 0:
            de_ratio = round(latest_balance.total_liabilities / latest_balance.total_equity, 2)

        latest_cashflow = StockCashFlow.query.filter_by(ma_cp=ma_cp).order_by(StockCashFlow.year.desc()).first()
        free_cash_flow = round(latest_cashflow.free_cash_flow / 1e9, 2) if latest_cashflow and latest_cashflow.free_cash_flow else 'N/A'

        stock_data = {
            'ma_cp': ma_cp,
            'so_luong': holding.so_luong,
            'current_price': round(current_price, 2),
            'average_buy_price': round(average_buy_price, 2),
            'profit': round(profit, 2),
            'profit_percentage': round(profit_percentage, 2),
            'company_name': stock_info.ten_cong_ty,
            'sector': stock_info.sector or 'N/A',
            'market_cap': round(stock_info.market_cap / 1e9, 2) if stock_info.market_cap else 'N/A',
            'pe_ratio': round(stock_info.trailing_pe, 2) if stock_info.trailing_pe else 'N/A',
            'eps': round(stock_info.trailing_eps, 2) if stock_info.trailing_eps else 'N/A',
            'beta': round(stock_info.beta, 2) if stock_info.beta else 'N/A',
            'dividend_yield': round(stock_info.dividend_yield * 100, 2) if stock_info.dividend_yield else 'N/A',
            'latest_dividend': latest_dividend,
            'average_volume_10d': round(stock_info.avg_volume_10d / 1e6, 2) if stock_info.avg_volume_10d else 'N/A',
            'average_volume_30d': round(stock_info.avg_volume_3m / 1e6, 2) if stock_info.avg_volume_3m else 'N/A',
            'revenue': round(latest_financial.total_revenue / 1e9, 2) if latest_financial and latest_financial.total_revenue else 'N/A',
            'net_income': round(latest_financial.net_income / 1e9, 2) if latest_financial and latest_financial.net_income else 'N/A',
            'net_margin': net_margin,
            'de_ratio': de_ratio,
            'free_cash_flow': free_cash_flow,
            'high_52w': round(high_52w, 2) if isinstance(high_52w, (int, float)) else 'N/A',
            'low_52w': round(low_52w, 2) if isinstance(low_52w, (int, float)) else 'N/A',
            'price_change_52w': price_change_52w
        }

        return render_template('stock_detail.html', stock=stock_data)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/history')
    @login_required
    def history():
        if current_user.vai_tro == 'admin':
            return redirect(url_for('admin_dashboard'))
        user = db.session.get(NguoiDung, current_user.id)
        transactions = LichSuGD.query.filter_by(id_nguoi_dung=user.id).order_by(LichSuGD.time.desc()).all()
        transaction_list = []
        for transaction in transactions:
            transaction_type = 'Nạp tiền' if transaction.ma_cp == 'CASH' and transaction.gia_tri > 0 else \
                              'Rút tiền' if transaction.ma_cp == 'CASH' and transaction.gia_tri < 0 else \
                              'Mua' if transaction.so_luong > 0 else 'Bán'
            transaction_list.append({
                'time': transaction.time.strftime('%Y-%m-%d %H:%M:%S'),
                'type': transaction_type,
                'ma_cp': transaction.ma_cp,
                'so_luong': abs(transaction.so_luong),
                'gia_tri': abs(transaction.gia_tri)
            })
        return render_template('history.html', transactions=transaction_list, user=user)

    @app.route('/confirm_trade', methods=['POST'])
    @login_required
    def confirm_trade():
     if current_user.vai_tro == 'admin':
        return redirect(url_for('admin_dashboard'))
     user = db.session.get(NguoiDung, current_user.id)
     holdings = DanhMucCP.query.filter_by(id_nguoi_dung=user.id).all()

     today = date.today()
     yesterday = today - timedelta(days=1)

     # Kiểm tra xem hôm nay có phải là ngày cuối tuần không
     is_weekend = today.weekday() >= 6 or  today.weekday() == 0 # 5 là thứ Bảy, 6 là Chủ nhật

     total_assets_today = user.so_tien or 0.0
     current_stock_value = 0.0
     price_data = {}
     for holding in holdings:
        price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=today).first()
        if not price_record:
            price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=yesterday).first()
            if not price_record:
                price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp).order_by(StockPriceDaily.date.desc()).first()
        if not price_record:
            flash(f'Không có dữ liệu giá cho {holding.ma_cp} trong ngày {today}.', 'warning')
            continue

        last_price = float(price_record.price)
        price_data[holding.ma_cp] = last_price
        gia_tri = last_price * holding.so_luong
        total_assets_today += gia_tri
        current_stock_value += gia_tri

     yesterday_record = TongGiaTriTrongNgay.query.filter_by(id_nguoi_dung=user.id, time=yesterday).first()
     total_assets_yesterday = yesterday_record.gia_tri_tong_tai_san if yesterday_record else 0.0

     assets_unchanged = abs(total_assets_today - total_assets_yesterday) < 0.01

     existing_total = TongGiaTriTrongNgay.query.filter_by(id_nguoi_dung=user.id, time=today).first()
     if existing_total:
        existing_total.gia_tri_tong_tai_san = total_assets_today
        flash(f'Tổng tài sản được cập nhật: {total_assets_today}', 'info')
     else:
        new_total = TongGiaTriTrongNgay(
            id_nguoi_dung=user.id,
            time=today,
            gia_tri_tong_tai_san=total_assets_today
        )
        db.session.add(new_total)
        flash(f'Tổng tài sản được thêm mới: {total_assets_today}', 'info')

     # Điều chỉnh logic tính lợi nhuận
     daily_profit = 0.0
     if is_weekend:
        # Nếu là ngày cuối tuần, ghi nhận lợi nhuận là 0
        daily_profit = 0.0
     else:
        if not assets_unchanged and holdings:
            for holding in holdings:
                price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=today).first()
                if not price_record:
                    price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=yesterday).first()
                    if not price_record:
                        price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp).order_by(StockPriceDaily.date.desc()).first()
                if not price_record:
                    continue

                current_price = float(price_record.price)
                previous_price_record = (StockPriceDaily.query.filter(StockPriceDaily.ma_cp == holding.ma_cp, 
                                                                    StockPriceDaily.date < price_record.date)
                                      .order_by(StockPriceDaily.date.desc()).first())
                if previous_price_record:
                    previous_price = float(previous_price_record.price)
                    profit_contribution = (current_price - previous_price) * holding.so_luong
                    daily_profit += profit_contribution
                else:
                    daily_profit += 0.0

     existing_profit = DailyProfit.query.filter_by(id_nguoi_dung=user.id, date=today).first()
     if existing_profit:
        existing_profit.total_assets = float(current_stock_value)
        existing_profit.profit = float(daily_profit)
        flash(f'Lợi nhuận ngày được cập nhật: {daily_profit}', 'info')
     else:
        new_profit = DailyProfit(
            id_nguoi_dung=user.id,
            date=today,
            total_assets=float(current_stock_value),
            profit=float(daily_profit)
        )
        db.session.add(new_profit)
        flash(f'Lợi nhuận ngày được thêm mới: {daily_profit}', 'info')

     try:
        db.session.commit()
        flash('Dữ liệu đã được lưu vào bảng tong_gia_tri_trong_ngay và daily_profit.', 'success')
     except Exception as e:
        db.session.rollback()
        flash(f'Lỗi khi lưu dữ liệu: {str(e)}', 'danger')

     return redirect(url_for('portfolio'))

    @app.route('/stock_search/<ma_cp>', methods=['GET', 'POST'])
    @login_required
    def stock_search(ma_cp):
     if current_user.vai_tro == 'admin':
        return redirect(url_for('admin_dashboard'))
     ma_cp = ma_cp.upper()
     stock_codes_records = StockCodes.query.all()
     stock_codes = [record.ma_cp for record in stock_codes_records]

     if request.method == 'POST':
        search_query = request.form.get('search', '').upper()
        if search_query and search_query in stock_codes:
            return redirect(url_for('stock_search', ma_cp=search_query))
        else:
            flash('Mã cổ phiếu không tồn tại!', 'error')
            return redirect(url_for('stock_search', ma_cp=ma_cp))

     if ma_cp not in stock_codes:
        flash('Mã cổ phiếu không tồn tại!', 'error')
        return redirect(url_for('dashboard'))

     today = date.today()
     market_data = []
     for symbol in stock_codes:
        if symbol == ma_cp:
            price_record = StockPriceDaily.query.filter_by(ma_cp=symbol, date=today).first()
            if not price_record:
                price_record = StockPriceDaily.query.filter_by(ma_cp=symbol).order_by(StockPriceDaily.date.desc()).first()
            if not price_record:
                market_data.append({
                    'ma_cp': symbol,
                    'gia': 100.0,
                    'change': random.uniform(-5.0, 5.0),
                    'volume': 1000
                })
            else:
                last_price = float(price_record.price)
                last_volume = int(price_record.volume)

                # Tìm ngày giao dịch trước đó
                prev_trading_day = get_previous_trading_day(symbol, price_record.date)
                prev_price = last_price
                pct_change = 0.0
                if prev_trading_day:
                    prev_price_record = StockPriceDaily.query.filter_by(ma_cp=symbol, date=prev_trading_day).first()
                    if prev_price_record:
                        prev_price = float(prev_price_record.price)
                        pct_change = ((last_price - prev_price) / prev_price * 100) if prev_price != 0 else 0.0

                market_data.append({
                    'ma_cp': symbol,
                    'gia': round(last_price, 2),
                    'change': round(pct_change, 2),
                    'volume': last_volume
                })
        else:
            market_data.append({
                'ma_cp': symbol,
                'gia': 0.0,
                'change': 0.0,
                'volume': 0
            })

     historical_data = StockPriceHistorical.query.filter_by(ma_cp=ma_cp).order_by(StockPriceHistorical.date.asc()).all()
     if not historical_data:
        flash(f'Không có dữ liệu lịch sử giá cho {ma_cp}. Vui lòng cập nhật dữ liệu!', 'warning')

     chart_data = {
        'candlestick': [
            {
                'x': record.date.strftime('%Y-%m-%d'),
                'y': [
                    float(record.open_price),
                    float(record.high_price),
                    float(record.low_price),
                    float(record.close_price)
                ]
            } for record in historical_data
        ],
        'volumes': [
            {
                'x': record.date.strftime('%Y-%m-%d'),
                'y': int(record.volume)
            } for record in historical_data
        ]
     }

     stock_info = StockInfo.query.filter_by(ma_cp=ma_cp).first()
     financial_info = {
        'price': market_data[stock_codes.index(ma_cp)]['gia'],
        'market_cap': round(stock_info.market_cap / 1e9, 2) if stock_info and stock_info.market_cap else 'N/A',
        'pe_ratio': round(stock_info.trailing_pe, 2) if stock_info and stock_info.trailing_pe else 'N/A',
        'eps': round(stock_info.trailing_eps, 2) if stock_info and stock_info.trailing_eps else 'N/A',
        'volume': market_data[stock_codes.index(ma_cp)]['volume'],
        'change': market_data[stock_codes.index(ma_cp)]['change'],
        'company_name': stock_info.ten_cong_ty if stock_info else 'N/A',
        'sector': stock_info.sector if stock_info else 'N/A',
        'beta': round(stock_info.beta, 2) if stock_info and stock_info.beta else 'N/A',
        'dividend_yield': round(stock_info.dividend_yield * 100, 2) if stock_info and stock_info.dividend_yield else 'N/A',
        'average_volume_10d': round(stock_info.avg_volume_10d / 1e6, 2) if stock_info and stock_info.avg_volume_10d else 'N/A',
        'average_volume_30d': round(stock_info.avg_volume_3m / 1e6, 2) if stock_info and stock_info.avg_volume_3m else 'N/A'
     }

     return render_template('stock_search.html',
                          ma_cp=ma_cp,
                          market_data=market_data,
                          chart_data=chart_data,
                          financial_info=financial_info)

    @app.route('/profit_calendar_chartjs')
    @login_required
    def profit_calendar_chartjs():
        if current_user.vai_tro == 'admin':
            return redirect(url_for('admin_dashboard'))
        user = db.session.get(NguoiDung, current_user.id)
        today = date.today()
        first_day = today.replace(day=1)

        _, days_in_month = cal.monthrange(today.year, today.month)
        profit_records = DailyProfit.query.filter_by(id_nguoi_dung=user.id).filter(
            DailyProfit.date >= first_day,
            DailyProfit.date <= today
        ).all()
        profit_dict = {record.date.day: float(record.profit) for record in profit_records if record.profit is not None}

        calendar_data = []
        calendar_matrix = cal.monthcalendar(today.year, today.month)
        for week_idx, week in enumerate(calendar_matrix):
            for day_idx, day in enumerate(week):
                if day == 0:
                    continue
                profit = profit_dict.get(day, 0.0)
                profit_display = f"+{profit:.0f}" if profit > 0 else f"{profit:.0f}"
                profit_color = '#28a745' if profit > 0 else '#6c757d' if profit == 0 else '#dc3545'
                calendar_data.append({
                    "x": day_idx,
                    "y": week_idx,
                    "profit": profit,
                    "profit_display": profit_display,
                    "profit_color": profit_color,
                    "day": day
                })

        chart_data = []
        for data in calendar_data:
            chart_data.append({
                "x": data["x"],
                "y": data["y"],
                "v": data["profit"],
                "day": data["day"],
                "profit_display": data["profit_display"],
                "profit_color": data["profit_color"]
            })

        return render_template('profit_calendar_chartjs.html',
                              chart_data=chart_data,
                              today=today,
                              weeks=len(calendar_matrix),
                              days_in_month=days_in_month)

    # Routes dành riêng cho Admin
    @app.route('/admin')
    @login_required
    @admin_required
    def admin_dashboard():
        total_users = NguoiDung.query.filter_by(vai_tro='user').count()
        total_stocks = StockCodes.query.count()
        total_transactions = LichSuGD.query.count()
        total_profit = db.session.query(func.sum(LichSuGD.gia_tri)).filter(LichSuGD.gia_tri.isnot(None)).scalar() or 0.0
        # Lấy top 5 mã cổ phiếu được giao dịch nhiều nhất
        top_5_most_traded = db.session.query(
          LichSuGD.ma_cp,
          func.sum(LichSuGD.so_luong).label('total_volume')
        ).filter(LichSuGD.ma_cp != 'CASH') \
         .group_by(LichSuGD.ma_cp) \
         .order_by(func.sum(LichSuGD.so_luong).desc()) \
         .limit(5) \
         .all()

        # Lấy top 5 mã cổ phiếu được giao dịch ít nhất
        top_5_least_traded = db.session.query(
         LichSuGD.ma_cp,
         func.sum(LichSuGD.so_luong).label('total_volume')
        ).filter(LichSuGD.ma_cp != 'CASH') \
         .group_by(LichSuGD.ma_cp) \
         .order_by(func.sum(LichSuGD.so_luong).asc()) \
         .limit(5) \
         .all()
        return render_template('admin/dashboard.html',
                              total_users=total_users,
                              total_stocks=total_stocks,
                              total_transactions=total_transactions,
                              total_profit=round(total_profit, 2),
                              top_5_most_traded=[{'ma_cp': stock.ma_cp, 'so_luong': stock.total_volume} for stock in top_5_most_traded],
                              top_5_least_traded=[{'ma_cp': stock.ma_cp, 'so_luong': stock.total_volume} for stock in top_5_least_traded])

    @app.route('/admin/users', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_users():
        users = NguoiDung.query.filter_by(vai_tro='user').all()
        if request.method == 'POST':
            user_id = request.form.get('user_id')
            action = request.form.get('action')
            user = NguoiDung.query.get(user_id)

            if not user:
                flash('Người dùng không tồn tại!', 'error')
                return redirect(url_for('admin_users'))

            if action == 'delete':
                db.session.delete(user)
                db.session.commit()
                flash('Đã xóa người dùng thành công!', 'success')
            elif action == 'edit':
                new_ten = request.form.get('ten')
                new_tk = request.form.get('tk')
                new_mk = request.form.get('mk')
                new_so_tien = float(request.form.get('so_tien', 0.0))

                user.ten = new_ten
                user.tk = new_tk
                if new_mk:
                    user.mk = new_mk
                user.so_tien = new_so_tien
                db.session.commit()
                flash('Đã cập nhật thông tin người dùng!', 'success')

        return render_template('admin/users.html', users=users)

    @app.route('/admin/stocks', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_stocks():
        stocks = StockCodes.query.all()
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                ma_cp = request.form.get('ma_cp').upper()
                if StockCodes.query.filter_by(ma_cp=ma_cp).first():
                    flash('Mã cổ phiếu đã tồn tại!', 'error')
                else:
                    new_stock = StockCodes(ma_cp=ma_cp)
                    db.session.add(new_stock)
                    db.session.commit()
                    flash('Đã thêm mã cổ phiếu thành công!', 'success')
            elif action == 'delete':
                stock_id = request.form.get('stock_id')
                stock = StockCodes.query.get(stock_id)
                if stock:
                    db.session.delete(stock)
                    db.session.commit()
                    flash('Đã xóa mã cổ phiếu thành công!', 'success')
                else:
                    flash('Mã cổ phiếu không tồn tại!', 'error')

        return render_template('admin/stocks.html', stocks=stocks)

    @app.route('/admin/transactions', methods=['GET'])
    @login_required
    @admin_required
    def admin_transactions():
        page = request.args.get('page', 1, type=int)
        per_page = 10
        transactions = LichSuGD.query.order_by(LichSuGD.time.desc()).paginate(page=page, per_page=per_page, error_out=False)

        transaction_list = []
        for transaction in transactions.items:
            user = NguoiDung.query.get(transaction.id_nguoi_dung)
            transaction_type = 'Nạp tiền' if transaction.ma_cp == 'CASH' and transaction.gia_tri > 0 else \
                              'Rút tiền' if transaction.ma_cp == 'CASH' and transaction.gia_tri < 0 else \
                              'Mua' if transaction.so_luong > 0 else 'Bán'
            transaction_list.append({
                'time': transaction.time.strftime('%Y-%m-%d %H:%M:%S'),
                'user': user.ten,
                'type': transaction_type,
                'ma_cp': transaction.ma_cp,
                'so_luong': abs(transaction.so_luong),
                'gia_tri': abs(transaction.gia_tri)
            })

        return render_template('admin/transactions.html',
                              transactions=transaction_list,
                              page=page,
                              total_pages=transactions.pages)

    @app.route('/admin/portfolios', methods=['GET'])
    @login_required
    @admin_required
    def admin_portfolios():
        users = NguoiDung.query.filter_by(vai_tro='user').all()
        today = date.today()
        portfolios = []

        for user in users:
            holdings = DanhMucCP.query.filter_by(id_nguoi_dung=user.id).all()
            total_assets = user.so_tien or 0.0
            portfolio_stocks = []

            for holding in holdings:
                price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=today).first()
                if not price_record:
                    price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp).order_by(StockPriceDaily.date.desc()).first()
                if not price_record:
                    continue

                last_price = float(price_record.price)
                gia_tri = last_price * holding.so_luong
                total_assets += gia_tri
                portfolio_stocks.append({
                    'ma_cp': holding.ma_cp,
                    'so_luong': holding.so_luong,
                    'gia': round(last_price, 2),
                    'gia_tri': round(gia_tri, 2)
                })

            portfolios.append({
                'user_id': user.id,
                'user_name': user.ten,
                'total_assets': round(total_assets, 2),
                'stocks': portfolio_stocks
            })

        return render_template('admin/portfolios.html', portfolios=portfolios)

    @app.route('/admin/profits', methods=['GET'])
    @login_required
    @admin_required
    def admin_profits():
        users = NguoiDung.query.filter_by(vai_tro='user').all()
        profit_data = []
        chart_labels = []
        chart_datasets = []

        for user in users:
            profits = DailyProfit.query.filter_by(id_nguoi_dung=user.id).order_by(DailyProfit.date).all()
            user_profits = []
            cumulative_profit = 0.0

            for profit in profits:
                cumulative_profit += profit.profit
                user_profits.append({
                    'date': profit.date.strftime('%Y-%m-%d'),
                    'profit': round(profit.profit, 2),
                    'cumulative_profit': round(cumulative_profit, 2)
                })

            if profits:
                if not chart_labels:
                    chart_labels = [profit.date.strftime('%Y-%m-%d') for profit in profits]
                chart_datasets.append({
                    'label': user.ten,
                    'data': [round(profit.profit, 2) for profit in profits],
                    'borderColor': f'rgb({random.randint(0, 255)}, {random.randint(0, 255)}, {random.randint(0, 255)})',
                    'fill': False
                })

            profit_data.append({
                'user_id': user.id,
                'user_name': user.ten,
                'profits': user_profits
            })

        chart_data = {
            'labels': chart_labels,
            'datasets': chart_datasets
        }

        return render_template('admin/profits.html',
                              profit_data=profit_data,
                              chart_data=chart_data)
    

    from flask import render_template, json

    @app.route('/detailed_dashboard')
    @login_required
    def detailed_dashboard():
     user = db.session.get(NguoiDung, current_user.id)
     holdings = DanhMucCP.query.filter_by(id_nguoi_dung=user.id).all()

     total_assets = user.so_tien or 0.0
     today = date.today()

     colors = [
         '#36A2EB','#FF6384', '#FFCE56', '#4BC0C0', '#9966FF',
        '#FF9F40', '#C9CBCF', '#8E44AD', '#2ECC71', '#E67E22'
     ]

     portfolio_stocks = []
     for i, holding in enumerate(holdings):
        price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp, date=today).first()
        if not price_record:
            price_record = StockPriceDaily.query.filter_by(ma_cp=holding.ma_cp).order_by(StockPriceDaily.date.desc()).first()
        if price_record and price_record.price is not None:
            last_price = float(price_record.price)
            gia_tri = last_price * holding.so_luong
            total_assets += gia_tri
            stock_info = StockInfo.query.filter_by(ma_cp=holding.ma_cp).first()
            financials = StockFinancials.query.filter_by(ma_cp=holding.ma_cp).order_by(StockFinancials.year).all()
            cash_flows = StockCashFlow.query.filter_by(ma_cp=holding.ma_cp).order_by(StockCashFlow.year).all()
            portfolio_stocks.append({
                'ma_cp': holding.ma_cp,
                'color': colors[i % len(colors)],
                'so_luong': holding.so_luong,
                'gia': round(last_price, 2),
                'gia_tri': round(gia_tri, 2),
                'stock_info': stock_info,
                'financials': financials,
                'cash_flows': cash_flows
            })

     # Biểu đồ theo năm
     revenue_data = {'labels': [], 'datasets': []}
     net_income_data = {'labels': [], 'datasets': []}
     cash_flow_data = {'labels': [], 'datasets': []}

     # Biểu đồ theo mã CP
     pe_ratio_data = {'labels': [], 'datasets': []}
     dividend_yield_data = {'labels': [], 'datasets': []}
     eps_data = {'labels': [], 'datasets': []}
     market_cap_data = {'labels': [], 'datasets': []}
     beta_data = {'labels': [], 'datasets': []}

     if portfolio_stocks:
        years = set()
        for stock in portfolio_stocks:
            if stock['financials']:
                years.update(r.year for r in stock['financials'])
            if stock['cash_flows']:
                years.update(cf.year for cf in stock['cash_flows'])

        year_list = sorted(list(years))
        revenue_data['labels'] = year_list
        net_income_data['labels'] = year_list
        cash_flow_data['labels'] = year_list

        for stock in portfolio_stocks:
            ma_cp = stock['ma_cp']
            color = stock['color']

            revenue_data['datasets'].append({
                'label': f"{ma_cp} - Doanh thu",
                'data': [float(next((r.total_revenue for r in stock['financials'] if r.year == y), 0.0) or 0) for y in year_list],
                'borderColor': color,
                'backgroundColor': color,
                'fill': False,
                'tension': 0.1
            })

            net_income_data['datasets'].append({
                'label': f"{ma_cp} - Lợi nhuận",
                'data': [float(next((r.net_income for r in stock['financials'] if r.year == y), 0.0) or 0) for y in year_list],
                'backgroundColor': color,
                'borderColor': color,
                'borderWidth': 1
            })

            cash_flow_data['datasets'].append({
                'label': f"{ma_cp} - FCF",
                'data': [float(next((cf.free_cash_flow for cf in stock['cash_flows'] if cf.year == y), 0.0) or 0) for y in year_list],
                'borderColor': color,
                'backgroundColor': color,
                'fill': False,
                'tension': 0.1
            })

        # Gộp theo mã CP
        pe_ratio_data['labels'] = [s['ma_cp'] for s in portfolio_stocks]
        dividend_yield_data['labels'] = [s['ma_cp'] for s in portfolio_stocks]
        eps_data['labels'] = [s['ma_cp'] for s in portfolio_stocks]
        market_cap_data['labels'] = [s['ma_cp'] for s in portfolio_stocks]
        beta_data['labels'] = [s['ma_cp'] for s in portfolio_stocks]

        pe_ratio_data['datasets'].append({
            'label': 'P/E Ratio',
            'data': [float(s['stock_info'].trailing_pe or 0) if s['stock_info'] else 0 for s in portfolio_stocks],
            'backgroundColor': [s['color'] for s in portfolio_stocks]
        })
        dividend_yield_data['datasets'].append({
            'label': 'Tỷ suất cổ tức',
            'data': [float(s['stock_info'].dividend_yield or 0) if s['stock_info'] else 0 for s in portfolio_stocks],
            'backgroundColor': [s['color'] for s in portfolio_stocks]
        })
        eps_data['datasets'].append({
            'label': 'EPS',
            'data': [float(s['stock_info'].trailing_eps or 0) if s['stock_info'] else 0 for s in portfolio_stocks],
            'backgroundColor': [s['color'] for s in portfolio_stocks]
        })
        market_cap_data = {
        'datasets': [{
        'label': 'Market Cap',
        'data': [
            {
                'x': i + 1,
                'y': float(s['stock_info'].beta or 1) if s['stock_info'] else 1,
                'r': round((float(s['stock_info'].market_cap or 0) / 1e9) ** 0.5, 2),
                'ma_cp': s['ma_cp']  # thêm label mã CP để hiển thị trong tooltip
            }
            for i, s in enumerate(portfolio_stocks)
         ],
         'backgroundColor': [s['color'] for s in portfolio_stocks]
         }]
         }   

        beta_data['datasets'].append({
            'label': 'Beta',
            'data': [float(s['stock_info'].beta or 0) if s['stock_info'] else 0 for s in portfolio_stocks],
            'backgroundColor': [s['color'] for s in portfolio_stocks]
        })

     return render_template('detailed_dashboard.html',
        total_assets=round(total_assets, 2),
        revenue_data=json.dumps(revenue_data),
        net_income_data=json.dumps(net_income_data),
        pe_ratio_data=json.dumps(pe_ratio_data),
        dividend_yield_data=json.dumps(dividend_yield_data),
        cash_flow_data=json.dumps(cash_flow_data),
        eps_data=json.dumps(eps_data),
        market_cap_data=json.dumps(market_cap_data),
        beta_data=json.dumps(beta_data)
    )
    
    @app.route('/edit_profile', methods=['GET', 'POST'])
    @login_required
    def edit_profile():
     user = db.session.get(NguoiDung, current_user.id)
     if request.method == 'POST':
        user.ten = request.form.get('ten', user.ten)
        user.email = request.form.get('email', user.email)  # Thêm các trường khác nếu cần
        db.session.commit()
        flash('Thông tin cá nhân đã được cập nhật thành công.', 'success')
        return redirect(url_for('trading'))
     return render_template('edit_profile.html', user=user)
 
    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
     user = db.session.get(NguoiDung, current_user.id)
     if request.method == 'POST':
        user.ten = request.form.get('ten', user.ten)
        user.tk = request.form.get('tk', user.tk)
        user.mk = request.form.get('mk', user.mk)
        db.session.commit()
        flash('Cập nhật thành công!', 'success')
        return redirect(url_for('profile'))
     return render_template('profile.html', user=user)
