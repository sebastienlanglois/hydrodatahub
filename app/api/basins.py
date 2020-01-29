from flask import jsonify, request, url_for, g, abort
from app import db
from app.api import bp
from app.models import basins
import pandas as pd
from config import Config
from sqlalchemy import create_engine


@bp.route('/basins', methods=['GET'])
def basins():
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI,
                           echo=False)
    sql = """
    SELECT * FROM basins
    """
    df = pd.read_sql(sql,con=engine)
    return df.to_json(orient="table")


@bp.route('/meta_ts', methods=['GET'])
def meta_ts():
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI,
                           echo=False)
    sql = """
    SELECT * FROM meta_ts
    """
    df = pd.read_sql(sql, con=engine)
    return df.to_json(orient="table")


# @bp.route('/basins', methods=['GET'])
# def basins():
#     engine = create_engine(Config.SQLALCHEMY_DATABASE_URI,
#                            echo=False)
#     sql = """
#     SELECT * FROM basins
#     """
#     df = pd.read_sql(sql,con=engine)
#     return df.to_json(orient="records")