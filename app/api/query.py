from flask import jsonify, request, url_for, g, abort
from app import db
from app.api import bp
from app.models import basins
import pandas as pd
from config import Config
from sqlalchemy import create_engine


@bp.route('/basins', methods=['GET'])
def basins():
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI_PUBLIC,
                           echo=False)
    sql = """
    SELECT * FROM basins
    """
    df = pd.read_sql(sql,con=engine)
    return df.to_json(orient="table")


@bp.route('/meta_ts', methods=['GET'])
def meta_ts():
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI_PUBLIC,
                           echo=False)
    sql = """
    SELECT * FROM meta_ts
    """
    df = pd.read_sql(sql, con=engine)
    return df.to_json(orient="table")


@bp.route('/query', methods=['GET', 'POST'])
def query():
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI_PUBLIC,
                           echo=False)
    # sql = """
    # SELECT * FROM basins
    # """
    sql = request.args.get('query', default=1, type=str)
    print(sql)
    try:
        df = pd.read_sql(sql, con=engine)
        output = df.to_json(orient="table")
    except RuntimeError:
        output = f'Query not valid'

    return output