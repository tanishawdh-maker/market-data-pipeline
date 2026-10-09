-- =====================================================================
-- Seed the 20 stocks the pipeline will track.
-- ON CONFLICT DO NOTHING makes this script safe to run more than once.
-- =====================================================================
INSERT INTO tickers (symbol, name, sector, exchange) VALUES
    ('AAPL',  'Apple Inc.',                 'Technology',              'NASDAQ'),
    ('MSFT',  'Microsoft Corporation',      'Technology',              'NASDAQ'),
    ('NVDA',  'NVIDIA Corporation',         'Technology',              'NASDAQ'),
    ('GOOGL', 'Alphabet Inc. Class A',      'Communication Services',  'NASDAQ'),
    ('AMZN',  'Amazon.com Inc.',            'Consumer Discretionary',  'NASDAQ'),
    ('META',  'Meta Platforms Inc.',        'Communication Services',  'NASDAQ'),
    ('TSLA',  'Tesla Inc.',                 'Consumer Discretionary',  'NASDAQ'),
    ('JPM',   'JPMorgan Chase & Co.',       'Financials',              'NYSE'),
    ('GS',    'Goldman Sachs Group Inc.',   'Financials',              'NYSE'),
    ('BAC',   'Bank of America Corp.',      'Financials',              'NYSE'),
    ('CME',   'CME Group Inc.',             'Financials',              'NASDAQ'),
    ('XOM',   'Exxon Mobil Corporation',    'Energy',                  'NYSE'),
    ('CVX',   'Chevron Corporation',        'Energy',                  'NYSE'),
    ('JNJ',   'Johnson & Johnson',          'Health Care',             'NYSE'),
    ('UNH',   'UnitedHealth Group Inc.',    'Health Care',             'NYSE'),
    ('PG',    'Procter & Gamble Co.',       'Consumer Staples',        'NYSE'),
    ('KO',    'Coca-Cola Company',          'Consumer Staples',        'NYSE'),
    ('CAT',   'Caterpillar Inc.',           'Industrials',             'NYSE'),
    ('SPY',   'SPDR S&P 500 ETF Trust',     'ETF',                     'NYSE Arca'),
    ('QQQ',   'Invesco QQQ Trust',          'ETF',                     'NASDAQ')
ON CONFLICT (symbol) DO NOTHING;
