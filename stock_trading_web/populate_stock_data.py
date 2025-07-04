from flask import Flask
from models import db, StockPriceDaily, StockPriceHistorical, StockInfo, StockFinancials, StockDividends, StockCashFlow, StockBalanceSheet, ApiCallLog, LichSuGD, StockCodes
import yfinance as yf
from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np
from datetime import timezone

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:23082004@localhost/stock_trading_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def populate_stock_data():
    with app.app_context():
        # Lấy danh sách mã cổ phiếu từ LichSuGD và StockCodes
        traded_stocks = db.session.query(LichSuGD.ma_cp).distinct().all()
        stock_codes_records = StockCodes.query.all()
        stock_codes = list(set([stock[0] for stock in traded_stocks] + [record.ma_cp for record in stock_codes_records]))

        # Chỉ lấy dữ liệu từ ngày hôm qua đến hôm nay
        today = date.today()  
        yesterday = today - timedelta(days=1) 
        start_date = yesterday
        end_date = today

        for ma_cp in stock_codes:
            try:
                stock = yf.Ticker(ma_cp)

                # 1. Lưu hoặc cập nhật thông tin công ty vào StockInfo
                info = stock.info
                existing_info = StockInfo.query.filter_by(ma_cp=ma_cp).first()
                if existing_info:
                    existing_info.ten_cong_ty = info.get('longName', 'N/A')
                    existing_info.sector = info.get('sector', 'N/A')
                    existing_info.market_cap = info.get('marketCap', 0)
                    existing_info.trailing_pe = info.get('trailingPE', 0) or None
                    existing_info.trailing_eps = info.get('trailingEps', 0) or None
                    existing_info.beta = info.get('beta', 0) or None
                    existing_info.dividend_yield = info.get('dividendYield', 0) or None
                    existing_info.avg_volume_10d = info.get('averageVolume10days', 0) or None
                    existing_info.avg_volume_3m = info.get('averageDailyVolume3Month', 0) or None
                    existing_info.last_updated = datetime.now(timezone.utc)
                else:
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
                    db.session.add(stock_info)

                # Log API call
                db.session.add(ApiCallLog(
                    ma_cp=ma_cp,
                    api_method='info',
                    response_status='success',
                    timestamp=datetime.now(timezone.utc)
                ))

                # 2. Lưu dữ liệu giá lịch sử vào StockPriceHistorical và StockPriceDaily
                hist = stock.history(start=start_date, end=end_date, interval='1d')
                if not hist.empty:
                    for index, row in hist.iterrows():
                        current_date = index.date()
                        # StockPriceHistorical
                        existing_historical = StockPriceHistorical.query.filter_by(ma_cp=ma_cp, date=current_date).first()
                        if existing_historical:
                            existing_historical.open_price = float(row['Open'])
                            existing_historical.high_price = float(row['High'])
                            existing_historical.low_price = float(row['Low'])
                            existing_historical.close_price = float(row['Close'])
                            existing_historical.volume = int(row['Volume'])
                        else:
                            historical_price = StockPriceHistorical(
                                ma_cp=ma_cp,
                                date=current_date,
                                open_price=float(row['Open']),
                                high_price=float(row['High']),
                                low_price=float(row['Low']),
                                close_price=float(row['Close']),
                                volume=int(row['Volume'])
                            )
                            db.session.add(historical_price)

                        # StockPriceDaily
                        existing_daily = StockPriceDaily.query.filter_by(ma_cp=ma_cp, date=current_date).first()
                        if existing_daily:
                            existing_daily.price = float(row['Close'])
                            existing_daily.volume = int(row['Volume'])
                        else:
                            daily_price = StockPriceDaily(
                                ma_cp=ma_cp,
                                date=current_date,
                                price=float(row['Close']),
                                volume=int(row['Volume'])
                            )
                            db.session.add(daily_price)

                    db.session.add(ApiCallLog(
                        ma_cp=ma_cp,
                        api_method='history_recent',
                        response_status='success',
                        timestamp=datetime.now(timezone.utc)
                    ))

                # 3. Lưu dữ liệu tài chính vào StockFinancials (không thay đổi vì dữ liệu tài chính thường không thay đổi hàng ngày)
                financials = stock.financials
                if not financials.empty and existing_info is None:  # Chỉ thêm nếu chưa có StockInfo
                    for year in financials.columns:
                        year_int = year.year
                        total_revenue = financials[year].loc['Total Revenue'] if 'Total Revenue' in financials[year].index else None
                        net_income = financials[year].loc['Net Income'] if 'Net Income' in financials[year].index else None

                        total_revenue = int(total_revenue) if pd.notna(total_revenue) else None
                        net_income = int(net_income) if pd.notna(net_income) else None

                        existing_financial = StockFinancials.query.filter_by(ma_cp=ma_cp, year=year_int).first()
                        if existing_financial:
                            existing_financial.total_revenue = total_revenue
                            existing_financial.net_income = net_income
                        else:
                            financial_record = StockFinancials(
                                ma_cp=ma_cp,
                                year=year_int,
                                total_revenue=total_revenue,
                                net_income=net_income
                            )
                            db.session.add(financial_record)

                    db.session.add(ApiCallLog(
                        ma_cp=ma_cp,
                        api_method='financials',
                        response_status='success',
                        timestamp=datetime.now(timezone.utc)
                    ))

                # 4. Lưu dữ liệu cổ tức vào StockDividends (không thay đổi hàng ngày)
                dividends = stock.dividends
                if not dividends.empty and existing_info is None:
                    for index, amount in dividends.items():
                        current_date = index.date()
                        existing_dividend = StockDividends.query.filter_by(ma_cp=ma_cp, date=current_date).first()
                        if existing_dividend:
                            existing_dividend.amount = float(amount) if pd.notna(amount) else 0.0
                        else:
                            dividend_record = StockDividends(
                                ma_cp=ma_cp,
                                date=current_date,
                                amount=float(amount) if pd.notna(amount) else 0.0
                            )
                            db.session.add(dividend_record)

                    db.session.add(ApiCallLog(
                        ma_cp=ma_cp,
                        api_method='dividends',
                        response_status='success',
                        timestamp=datetime.now(timezone.utc)
                    ))

                # 5. Lưu dòng tiền vào StockCashFlow (không thay đổi hàng ngày)
                cashflow = stock.cashflow
                if not cashflow.empty and existing_info is None:
                    for year in cashflow.columns:
                        year_int = year.year
                        free_cash_flow = cashflow[year].loc['Free Cash Flow'] if 'Free Cash Flow' in cashflow[year].index else None
                        free_cash_flow = int(free_cash_flow) if pd.notna(free_cash_flow) else None

                        existing_cashflow = StockCashFlow.query.filter_by(ma_cp=ma_cp, year=year_int).first()
                        if existing_cashflow:
                            existing_cashflow.free_cash_flow = free_cash_flow
                        else:
                            cashflow_record = StockCashFlow(
                                ma_cp=ma_cp,
                                year=year_int,
                                free_cash_flow=free_cash_flow
                            )
                            db.session.add(cashflow_record)

                    db.session.add(ApiCallLog(
                        ma_cp=ma_cp,
                        api_method='cashflow',
                        response_status='success',
                        timestamp=datetime.now(timezone.utc)
                    ))

                # 6. Lưu bảng cân đối kế toán vào StockBalanceSheet (không thay đổi hàng ngày)
                balance_sheet = stock.balance_sheet
                if not balance_sheet.empty and existing_info is None:
                    for year in balance_sheet.columns:
                        year_int = year.year
                        total_liabilities = balance_sheet[year].loc['Total Liabilities'] if 'Total Liabilities' in balance_sheet[year].index else None
                        total_equity = balance_sheet[year].loc['Total Stockholder Equity'] if 'Total Stockholder Equity' in balance_sheet[year].index else None

                        total_liabilities = int(total_liabilities) if pd.notna(total_liabilities) else None
                        total_equity = int(total_equity) if pd.notna(total_equity) else None

                        existing_balance = StockBalanceSheet.query.filter_by(ma_cp=ma_cp, year=year_int).first()
                        if existing_balance:
                            existing_balance.total_liabilities = total_liabilities
                            existing_balance.total_equity = total_equity
                        else:
                            balance_record = StockBalanceSheet(
                                ma_cp=ma_cp,
                                year=year_int,
                                total_liabilities=total_liabilities,
                                total_equity=total_equity
                            )
                            db.session.add(balance_record)

                    db.session.add(ApiCallLog(
                        ma_cp=ma_cp,
                        api_method='balance_sheet',
                        response_status='success',
                        timestamp=datetime.now(timezone.utc)
                    ))

                db.session.commit()
                print(f"Đã thêm/cập nhật dữ liệu cho {ma_cp} từ {start_date} đến {end_date}")
            except Exception as e:
                db.session.rollback()
                db.session.add(ApiCallLog(
                    ma_cp=ma_cp,
                    api_method='general',
                    response_status=str(e)[:255],
                    timestamp=datetime.now(timezone.utc)
                ))
                db.session.commit()
                print(f"Lỗi với {ma_cp}: {str(e)}")
                continue

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    populate_stock_data()