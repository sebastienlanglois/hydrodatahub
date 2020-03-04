from hydrodatahub.database.sources.cehq import get_available_stations_from_cehq, import_cehq_to_sql
from hydrodatahub.database.sources.hydat import get_available_stations_from_hydat, import_hydat_to_sql
from hydrodatahub.database.sources.legacy import get_available_stations_from_legacy, import_legacy_to_sql
from hydrodatahub.database.operations.concatenations import get_available_stations_from_concat_file, \
    import_concatenations_to_sql, Concatenations
from hydrodatahub.database.connectors import SQLAlchemyDBConnection
import multiprocessing
from dask import dataframe as dd
import pandas as pd
import time
from config import Config
from hydrodatahub.database.sources.hydat import StationParserHYDAT
from hydrodatahub.database.elements.bassin import Bassin
from hydrodatahub.models import bassin, concatenations
import os
from sqlalchemy.dialects import postgresql


def update_db():
    NB_THREADS = 8
    pool = multiprocessing.Pool(NB_THREADS)

    # 1. CEHQ
    stations = get_available_stations_from_cehq()
    pool.map(import_cehq_to_sql, stations)

    # 2. HYDAT
    stations = get_available_stations_from_hydat()
    pool.map(import_hydat_to_sql, stations)

    # 3. Legacy
    stations = get_available_stations_from_legacy()
    pool.map(import_legacy_to_sql, stations)

    # 4. Concatenations
    stations = get_available_stations_from_concat_file()
    ddf = dd.from_pandas(stations.iloc[range(0, 59), :], npartitions=16)
    ddf.map_partitions(lambda df: df.apply((lambda row: import_concatenations_to_sql(row)), axis=1)).compute()


if __name__ == '__main__':
    update_db()
    # stations = get_available_stations_from_concat_file()
    # print(stations.T[0])
    # sta = Concatenations(df=stations.T[0])
    # b = Bassin(sta)
    # b.to_sql()
    #
    # with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
    #     connection = db.session.bind.raw_connection()
    #     cursor = connection.cursor()
    #     uid_sources = [i.uid for i in db.session.query(bassin) \
    #         .filter(bassin.numero_station.in_(tuple(sta.concatenation_results[1]))).all()]
    #     uid_conca = db.session.query(bassin) \
    #         .filter_by(numero_station=sta.numero_station).first().uid
    #     df = pd.DataFrame(uid_sources, columns=['bassin_inclus'])
    #     df.insert(0, column='bassin_concatene', value=uid_conca)
    #     print(df)
    #
    #     insrt_stmnt = postgresql.insert(concatenations) \
    #         .values(df.to_dict(orient='records'))
    #     update_dict = {
    #         c.name: c
    #         for c in insrt_stmnt.excluded
    #     }
    #     do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=['bassin_concatene','bassin_inclus'],
    #                                                         set_=update_dict)
    #     db.session.bind.execute(do_nothing_stmt)
    #
    #